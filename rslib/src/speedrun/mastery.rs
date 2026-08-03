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
