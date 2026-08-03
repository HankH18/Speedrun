// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Per-topic mastery aggregation.
//!
//! Read-only. Two single-pass queries — one over `cards` joined to `notes` for
//! tags, one over `revlog` in card order — then all aggregation happens in
//! Rust. Neither is per-card, so this is O(cards + revlog) rather than N+1.
//! The 50,000-card dashboard target is the reason for that shape.

use std::collections::HashMap;

use anki_proto::speedrun::TopicMastery;
use anki_proto::speedrun::TopicMasteryRequest;
use anki_proto::speedrun::TopicMasteryResponse;
use fsrs::FSRS5_DEFAULT_DECAY;
use rusqlite::Row;

use crate::card::CardType;
use crate::card::FsrsMemoryState;
use crate::prelude::*;
use crate::revlog::RevlogEntry;
use crate::storage::card::data::CardData;
use crate::tags::split_tags;

/// Tags below this prefix name a topic in the USMLE content outline. A card may
/// carry several; it counts once under each.
pub const TOPIC_TAG_PREFIX: &str = "speedrun::topic::";

/// A card is mature at an interval of 21 days or more. Upstream has no shared
/// constant for this — the literal 21 is repeated at
/// `stats/graphs/card_counts.rs`, `stats/graphs/today.rs` and
/// `stats/graphs/buttons.rs`. We match the card-level definition used by
/// `card_counts.rs`: a review card whose interval is at least 21 days.
const MATURE_INTERVAL_DAYS: u32 = 21;

/// One card's contribution, read in a single pass.
struct CardRow {
    id: CardId,
    ctype: CardType,
    interval: u32,
    reps: u32,
    memory_state: Option<FsrsMemoryState>,
    decay: Option<f32>,
    last_review_time: Option<TimestampSecs>,
    topics: Vec<String>,
}

/// Running totals for one topic tag.
#[derive(Default)]
struct Accumulator {
    card_count: u32,
    reviewed_count: u32,
    mature_count: u32,
    fsrs_item_count: u32,
    review_count: u32,
    retrievability_sum: f64,
    stability_sum: f64,
    difficulty_sum: f64,
    /// Cards contributing to the three sums above. Cards without a memory state
    /// are deliberately excluded, so this is not `card_count`.
    with_memory_state: u32,
}

impl Accumulator {
    fn into_proto(self, topic_tag: String) -> TopicMastery {
        let n = self.with_memory_state.max(1) as f64;
        let mean = |sum: f64| {
            if self.with_memory_state == 0 {
                0.0
            } else {
                (sum / n) as f32
            }
        };
        TopicMastery {
            topic_tag,
            card_count: self.card_count,
            reviewed_count: self.reviewed_count,
            mature_count: self.mature_count,
            fsrs_item_count: self.fsrs_item_count,
            mean_retrievability: mean(self.retrievability_sum),
            mean_stability: mean(self.stability_sum),
            mean_difficulty: mean(self.difficulty_sum),
            review_count: self.review_count,
        }
    }
}

/// Whole days between a revlog entry and the collection's next day boundary.
/// Replicates the private helper of the same name in
/// `scheduler/fsrs/params.rs`, which is what defines `delta_t` for item
/// construction.
fn days_elapsed(entry: &RevlogEntry, next_day_at: TimestampSecs) -> u32 {
    (next_day_at.elapsed_secs_since(entry.id.as_secs()) / 86_400).max(0) as u32
}

fn row_to_card_row(row: &Row) -> std::result::Result<CardRow, rusqlite::Error> {
    let data: CardData = row.get(4)?;
    let tags: String = row.get(5)?;
    Ok(CardRow {
        id: row.get(0)?,
        ctype: row.get(1)?,
        interval: row.get(2)?,
        reps: row.get(3)?,
        memory_state: data.memory_state(),
        decay: data.decay,
        last_review_time: data.last_review_time,
        topics: split_tags(&tags)
            .filter(|tag| tag.starts_with(TOPIC_TAG_PREFIX))
            .map(str::to_string)
            .collect(),
    })
}

impl Collection {
    /// Aggregate per-topic mastery over cards tagged `speedrun::topic::*`.
    ///
    /// Read-only: no writes, no `OpChanges`, no undo entry.
    pub fn topic_mastery(&mut self, req: TopicMasteryRequest) -> Result<TopicMasteryResponse> {
        // `params.rs` measures delta_t in whole days against the collection's
        // day boundary, so we need the same reference point.
        let next_day_at = self.timing_today()?.next_day_at;
        let as_of = if req.as_of_unix_secs > 0 {
            TimestampSecs(req.as_of_unix_secs)
        } else {
            TimestampSecs::now()
        };
        // Empty = all topics.
        let wanted: Option<Vec<String>> = if req.topic_tags.is_empty() {
            None
        } else {
            Some(req.topic_tags.clone())
        };

        // Pass 1: cards joined to notes for their tags. `notes.tags` is stored
        // space-padded (` a b `) by `tags::join_tags`, so the LIKE below is a
        // cheap prefilter; `split_tags` does the authoritative split.
        let cards: Vec<CardRow> = self
            .storage
            .db
            .prepare_cached(
                "SELECT c.id, c.type, cast(c.ivl AS integer), c.reps, c.data, n.tags
                   FROM cards c
                   INNER JOIN notes n ON c.nid = n.id
                  WHERE n.tags LIKE ?",
            )?
            .query_and_then([format!("%{TOPIC_TAG_PREFIX}%")], row_to_card_row)?
            .collect::<std::result::Result<_, _>>()?;

        // Pass 2: revlog for those cards, in card order, so each card's history
        // can be walked once. Anki's own filter and item-construction rule are
        // applied below rather than re-derived.
        let mut per_card_counts: HashMap<CardId, (u32, u32)> = HashMap::new();
        if !cards.is_empty() {
            let entries: Vec<RevlogEntry> = self.storage.get_all_revlog_entries_in_card_order()?;
            let mut idx_in_card = 0usize;
            let mut previous: Option<&RevlogEntry> = None;
            for entry in &entries {
                let counts = per_card_counts.entry(entry.cid).or_default();
                if previous.map(|p| p.cid) != Some(entry.cid) {
                    idx_in_card = 0;
                    previous = None;
                }
                // Stage 1 — the filter Anki applies before building items.
                if !entry.has_rating_and_affects_scheduling() {
                    continue;
                }
                counts.0 += 1; // review_count
                               // Stage 2 — item construction. An item is emitted from the
                               // second surviving review onwards, and only when a whole day
                               // has elapsed, so k reviews yield at most k-1 items.
                let delta_t = previous
                    .map(|p| days_elapsed(p, next_day_at) - days_elapsed(entry, next_day_at))
                    .unwrap_or(0);
                if idx_in_card >= 1 && delta_t > 0 {
                    counts.1 += 1; // fsrs_item_count
                }
                idx_in_card += 1;
                previous = Some(entry);
            }
        }

        let mut topics: HashMap<String, Accumulator> = HashMap::new();
        let mut cards_without_memory_state = 0u32;

        for card in &cards {
            let relevant: Vec<&String> = card
                .topics
                .iter()
                .filter(|t| wanted.as_ref().map_or(true, |w| w.contains(t)))
                .collect();
            if relevant.is_empty() {
                continue;
            }
            if card.memory_state.is_none() {
                cards_without_memory_state += 1;
            }
            let (review_count, fsrs_item_count) =
                per_card_counts.get(&card.id).copied().unwrap_or_default();

            for topic in relevant {
                let acc = topics.entry(topic.clone()).or_default();
                acc.card_count += 1;
                if card.reps > 0 {
                    acc.reviewed_count += 1;
                }
                if card.ctype == CardType::Review && card.interval >= MATURE_INTERVAL_DAYS {
                    acc.mature_count += 1;
                }
                acc.review_count += review_count;
                acc.fsrs_item_count += fsrs_item_count;

                if let Some(state) = card.memory_state {
                    let elapsed_secs = card
                        .last_review_time
                        .map(|t| as_of.elapsed_secs_since(t).max(0))
                        .unwrap_or(0);
                    // Do not reimplement the forgetting curve — call FSRS's own.
                    let r = fsrs::current_retrievability(
                        state.into(),
                        elapsed_secs as f32 / 86_400.0,
                        card.decay.unwrap_or(FSRS5_DEFAULT_DECAY),
                    );
                    acc.retrievability_sum += r as f64;
                    acc.stability_sum += state.stability as f64;
                    acc.difficulty_sum += state.difficulty as f64;
                    acc.with_memory_state += 1;
                }
            }
        }

        let mut out: Vec<TopicMastery> = topics
            .into_iter()
            .map(|(tag, acc)| acc.into_proto(tag))
            .collect();
        out.sort_by(|a, b| a.topic_tag.cmp(&b.topic_tag));

        Ok(TopicMasteryResponse {
            topics: out,
            cards_without_memory_state,
        })
    }
}

impl crate::services::SpeedrunService for Collection {
    fn topic_mastery(&mut self, req: TopicMasteryRequest) -> Result<TopicMasteryResponse> {
        Collection::topic_mastery(self, req)
    }
}

#[cfg(test)]
mod test {
    use super::*;
    use crate::revlog::RevlogEntry;
    use crate::revlog::RevlogReviewKind;

    /// revlog.id is the review timestamp in milliseconds.
    fn revlog_id_days_ago(days_ago: i64) -> RevlogId {
        RevlogId(TimestampSecs::now().adding_secs(-days_ago * 86_400).0 * 1000)
    }

    fn add_card(col: &mut Collection, front: &str, tags: &[&str]) -> Card {
        let nt = col.get_notetype_by_name("Basic").unwrap().unwrap();
        let mut note = nt.new_note();
        note.set_field(0, front).unwrap();
        note.set_field(1, "back").unwrap();
        note.tags = tags.iter().map(|t| t.to_string()).collect();
        col.add_note(&mut note, DeckId(1)).unwrap();
        col.storage
            .all_cards_of_note(note.id)
            .unwrap()
            .pop()
            .unwrap()
    }

    fn counted_review(cid: CardId, days_ago: i64) -> RevlogEntry {
        RevlogEntry {
            id: revlog_id_days_ago(days_ago),
            cid,
            usn: Usn(-1),
            button_chosen: 3,
            interval: 30,
            last_interval: 10,
            ease_factor: 2500,
            taken_millis: 3000,
            review_kind: RevlogReviewKind::Review,
        }
    }

    /// Fixture with values chosen so every aggregate is hand-checkable.
    ///
    /// card A  cardio          mature (ivl 30), reps 3, memory state, 3 reviews
    /// card B  cardio + renal  young  (ivl 5),  reps 1, memory state
    /// card C  renal           new,               reps 0, NO memory state
    fn fixture() -> Collection {
        let mut col = Collection::new();

        let mut a = add_card(&mut col, "a", &["speedrun::topic::cardio"]);
        a.ctype = CardType::Review;
        a.interval = 30;
        a.reps = 3;
        a.memory_state = Some(FsrsMemoryState {
            stability: 40.0,
            difficulty: 5.0,
        });
        a.decay = Some(FSRS5_DEFAULT_DECAY);
        a.last_review_time = Some(TimestampSecs::now().adding_secs(-10 * 86_400));
        col.storage.update_card(&a).unwrap();
        // 3 counted reviews => 3 review_count, and 2 items (first yields none).
        for days in [30i64, 20, 10] {
            col.storage
                .add_revlog_entry(&counted_review(a.id, days), false)
                .unwrap();
        }

        let mut b = add_card(
            &mut col,
            "b",
            &["speedrun::topic::cardio", "speedrun::topic::renal"],
        );
        b.ctype = CardType::Review;
        b.interval = 5;
        b.reps = 1;
        b.memory_state = Some(FsrsMemoryState {
            stability: 10.0,
            difficulty: 7.0,
        });
        b.decay = Some(FSRS5_DEFAULT_DECAY);
        b.last_review_time = Some(TimestampSecs::now().adding_secs(-2 * 86_400));
        col.storage.update_card(&b).unwrap();

        let c = add_card(&mut col, "c", &["speedrun::topic::renal"]);
        assert!(c.memory_state.is_none(), "card C must have no memory state");

        col
    }

    fn topic<'a>(resp: &'a TopicMasteryResponse, tag: &str) -> &'a TopicMastery {
        resp.topics
            .iter()
            .find(|t| t.topic_tag == tag)
            .unwrap_or_else(|| panic!("topic {tag} missing"))
    }

    /// (a) Aggregation is correct against a fixture with known values.
    #[test]
    fn aggregation_matches_known_values() {
        let mut col = fixture();
        let resp = col.topic_mastery(TopicMasteryRequest::default()).unwrap();

        // Topics are returned sorted, and only tagged cards appear.
        assert_eq!(
            resp.topics.iter().map(|t| &t.topic_tag).collect::<Vec<_>>(),
            vec!["speedrun::topic::cardio", "speedrun::topic::renal"]
        );

        let cardio = topic(&resp, "speedrun::topic::cardio");
        assert_eq!(cardio.card_count, 2, "A and B carry cardio");
        assert_eq!(cardio.reviewed_count, 2, "both have reps > 0");
        assert_eq!(cardio.mature_count, 1, "only A has interval >= 21");
        // Only A has revlog: 3 surviving entries, yielding 3 - 1 = 2 items.
        assert_eq!(cardio.review_count, 3);
        assert_eq!(cardio.fsrs_item_count, 2);
        // Stability mean over A (40) and B (10).
        assert!((cardio.mean_stability - 25.0).abs() < 1e-4);
        // Difficulty mean over A (5) and B (7).
        assert!((cardio.mean_difficulty - 6.0).abs() < 1e-4);
        assert!(cardio.mean_retrievability > 0.0 && cardio.mean_retrievability <= 1.0);

        let renal = topic(&resp, "speedrun::topic::renal");
        assert_eq!(renal.card_count, 2, "B and C carry renal");
        assert_eq!(renal.reviewed_count, 1, "only B has reps > 0");
        assert_eq!(renal.mature_count, 0);
        assert_eq!(renal.review_count, 0, "neither B nor C has revlog");
        assert_eq!(renal.fsrs_item_count, 0);
    }

    /// (b) Cards with no memory state are excluded from the means, still
    /// counted in card_count, and reported in cards_without_memory_state.
    #[test]
    fn cards_without_memory_state_are_excluded_from_means_but_counted() {
        let mut col = fixture();
        let resp = col.topic_mastery(TopicMasteryRequest::default()).unwrap();

        assert_eq!(
            resp.cards_without_memory_state, 1,
            "card C only, counted once"
        );

        let renal = topic(&resp, "speedrun::topic::renal");
        // C is in card_count...
        assert_eq!(renal.card_count, 2);
        // ...but the means are over B alone, not (B + 0)/2.
        assert!(
            (renal.mean_stability - 10.0).abs() < 1e-4,
            "mean must be B's 10.0, not 5.0 — C must not dilute it"
        );
        assert!((renal.mean_difficulty - 7.0).abs() < 1e-4);
        assert!(renal.mean_retrievability > 0.0);
    }

    /// (c) The topic filter returns only requested tags, and a card carrying
    /// two topic tags is counted under both.
    #[test]
    fn topic_filter_and_multi_tagged_cards() {
        let mut col = fixture();

        let resp = col
            .topic_mastery(TopicMasteryRequest {
                topic_tags: vec!["speedrun::topic::renal".to_string()],
                as_of_unix_secs: 0,
            })
            .unwrap();
        assert_eq!(resp.topics.len(), 1, "only the requested topic");
        assert_eq!(resp.topics[0].topic_tag, "speedrun::topic::renal");
        assert_eq!(resp.topics[0].card_count, 2);

        // B carries both tags and must be counted under each.
        let all = col.topic_mastery(TopicMasteryRequest::default()).unwrap();
        assert_eq!(topic(&all, "speedrun::topic::cardio").card_count, 2);
        assert_eq!(topic(&all, "speedrun::topic::renal").card_count, 2);
        // 3 distinct cards, but 4 topic memberships.
        let memberships: u32 = all.topics.iter().map(|t| t.card_count).sum();
        assert_eq!(memberships, 4);
    }
}
