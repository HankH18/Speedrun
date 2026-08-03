// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Benchmark for the per-topic mastery query (BUILD-DOC §12, test 8).
//!
//! Run it with `just bench`. It is a `#[ignore]`d test rather than a criterion
//! bench for one reason that is not a preference: the fixture has to set
//! `Card::memory_state`, `Card::interval` and friends, and those fields — along
//! with `Collection::new` and `SqliteStorage::add_card` — are `pub(crate)`. A
//! target under `rslib/benches/` is a separate crate and cannot reach them. The
//! benchmark therefore has to live inside the crate, and criterion also does
//! not report p95 or a pass/fail verdict, both of which §12 demands.
//!
//! Everything is fixed and stated so the run is reproducible:
//!
//! | Parameter                | Value                                       |
//! | ------------------------ | ------------------------------------------- |
//! | Cards                    | 50,000, every one carrying a topic tag      |
//! | Topics                   | 20 (`speedrun::topic::t00` … `t19`)         |
//! | Second topic tag         | every 7th card                              |
//! | Unreviewed cards         | every 5th card (10,000 with no memory state)|
//! | Revlog entries           | 4 per reviewed card = 160,000               |
//! | Timed runs               | 25                                          |
//! | PRNG                     | SplitMix64, seed `SEED` below               |
//! | Budget                   | 1,000 ms (dashboard first load)             |
//!
//! The generator is a hand-rolled SplitMix64 rather than the `rand` crate so
//! that the deck is byte-identical on every machine and every run, independent
//! of what `rand`'s thread RNG or version happens to do.

#![cfg(test)]

use std::time::Instant;

use anki_proto::speedrun::TopicMasteryRequest;
use fsrs::FSRS5_DEFAULT_DECAY;
use tempfile::TempDir;

use crate::card::CardQueue;
use crate::card::CardType;
use crate::card::FsrsMemoryState;
use crate::prelude::*;
use crate::revlog::RevlogEntry;
use crate::revlog::RevlogReviewKind;
use crate::speedrun::mastery::TOPIC_TAG_PREFIX;

/// Fixed so the deck is identical on every run and every machine.
const SEED: u64 = 0x5EED_2024_0A17_C0DE;
/// BUILD-DOC §12 sizes the dashboard target at 50,000 cards.
const CARD_COUNT: usize = 50_000;
/// Roughly the number of top-level USMLE content-outline topics we tag under.
const TOPIC_COUNT: usize = 20;
/// Every Nth card carries a second topic tag, so cards are counted under both.
const MULTI_TOPIC_EVERY: usize = 7;
/// Every Nth card is brand new: no reps, no memory state, no revlog. These are
/// the cards that land in `cards_without_memory_state`.
const UNREVIEWED_EVERY: usize = 5;
/// Reviews recorded for each reviewed card.
const REVIEWS_PER_REVIEWED_CARD: usize = 4;
/// Whole days between consecutive reviews of the same card. Must be >= 1 so
/// that `delta_t > 0` and the FSRS item count is non-trivial.
const REVIEW_SPACING_DAYS: i64 = 3;
/// Timed iterations. §12 wants median / p95 / worst, so this must be >= 20.
const RUNS: usize = 25;
/// BUILD-DOC §12: "Dashboard first load < 1 s".
const BUDGET_MS: f64 = 1000.0;

/// SplitMix64. Deterministic, dependency-free, and good enough to decorrelate
/// the field values — this seeds test data, not cryptography.
struct SplitMix64(u64);

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        SplitMix64(seed)
    }

    fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform-ish in `0..n`. The modulo bias is irrelevant for test data.
    fn below(&mut self, n: u64) -> u64 {
        self.next_u64() % n
    }

    fn range_f32(&mut self, low: f32, high: f32) -> f32 {
        let unit = (self.below(1_000_000) as f32) / 1_000_000.0;
        low + unit * (high - low)
    }
}

fn topic_tag(idx: usize) -> String {
    format!("{TOPIC_TAG_PREFIX}t{idx:02}")
}

/// Build the synthetic deck described in the module docs.
///
/// Rows go in through the storage layer inside one transaction. Going through
/// `add_note`/`add_card` (rather than hand-written SQL) means the tags are
/// space-padded and the card `data` JSON is encoded by exactly the code the
/// query reads back, so the benchmark cannot pass by measuring a shape the real
/// dashboard never sees.
///
/// The collection is a real on-disk SQLite file, not `:memory:`, because the
/// dashboard reads a real one. That is the conservative choice.
fn build_deck() -> (Collection, TempDir, BuildStats) {
    let (mut col, tempdir) = crate::tests::open_fs_test_collection("speedrun_bench");
    let nt = col
        .get_notetype_by_name("Basic")
        .unwrap()
        .expect("Basic notetype");
    let mut rng = SplitMix64::new(SEED);
    let tags: Vec<String> = (0..TOPIC_COUNT).map(topic_tag).collect();
    let now = TimestampSecs::now();

    let mut stats = BuildStats::default();

    assert!(
        col.storage.db.is_autocommit(),
        "collection should not already be inside a transaction"
    );
    col.storage.begin_trx().unwrap();

    for i in 0..CARD_COUNT {
        let primary = i % TOPIC_COUNT;
        let mut note_tags = vec![tags[primary].clone()];
        if i % MULTI_TOPIC_EVERY == 0 {
            // +1 guarantees the offset is non-zero, so the second tag always
            // differs from the first.
            let secondary =
                (primary + 1 + rng.below(TOPIC_COUNT as u64 - 1) as usize) % TOPIC_COUNT;
            note_tags.push(tags[secondary].clone());
            stats.multi_topic_cards += 1;
        }
        stats.topic_memberships += note_tags.len();

        let mut note = nt.new_note();
        note.set_field(0, format!("question {i}")).unwrap();
        note.set_field(1, format!("answer {i}")).unwrap();
        note.tags = note_tags;
        note.prepare_for_update(&nt, true).unwrap();
        note.set_modified(Usn(-1));
        col.storage.add_note(&mut note).unwrap();

        let mut card = Card::new(note.id, 0, DeckId(1), i as i32);
        card.mtime = now;
        card.usn = Usn(-1);

        let reviewed = i % UNREVIEWED_EVERY != 0;
        if reviewed {
            card.ctype = CardType::Review;
            card.queue = CardQueue::Review;
            card.reps = 1 + rng.below(20) as u32;
            card.interval = 1 + rng.below(400) as u32;
            card.ease_factor = 2500;
            card.memory_state = Some(FsrsMemoryState {
                stability: rng.range_f32(1.0, 200.0),
                difficulty: rng.range_f32(1.0, 10.0),
            });
            card.decay = Some(FSRS5_DEFAULT_DECAY);
            card.last_review_time = Some(now.adding_secs(-(rng.below(60) as i64) * 86_400));
            stats.reviewed_cards += 1;
        } else {
            stats.unreviewed_cards += 1;
        }
        col.storage.add_card(&mut card).unwrap();

        if !reviewed {
            continue;
        }

        // Per-card jitter so not every card shares a review calendar.
        let jitter_days = rng.below(30) as i64;
        for j in 0..REVIEWS_PER_REVIEWED_CARD {
            let days_ago =
                jitter_days + (REVIEWS_PER_REVIEWED_CARD - j) as i64 * REVIEW_SPACING_DAYS;
            // revlog.id is the review time in milliseconds and is the primary
            // key; `add.sql` is INSERT OR IGNORE, so a collision would silently
            // drop the row. Adding the card index (< 50,000 ms) keeps every id
            // distinct without moving the entry across a day boundary, since
            // consecutive reviews of one card are REVIEW_SPACING_DAYS apart.
            let id = RevlogId(now.adding_secs(-days_ago * 86_400).0 * 1000 + i as i64);
            let entry = RevlogEntry {
                id,
                cid: card.id,
                usn: Usn(-1),
                button_chosen: 1 + rng.below(4) as u8,
                interval: 1 + rng.below(400) as i32,
                last_interval: 1 + rng.below(200) as i32,
                ease_factor: 2500,
                taken_millis: 1000 + rng.below(20_000) as u32,
                review_kind: RevlogReviewKind::Review,
            };
            col.storage.add_revlog_entry(&entry, false).unwrap();
            stats.revlog_entries += 1;
        }
    }

    col.storage.commit_trx().unwrap();

    // INSERT OR IGNORE would have hidden a duplicate id, which would quietly
    // shrink the workload. Prove it did not happen.
    let stored_revlog: usize = col
        .storage
        .db
        .query_row("select count() from revlog", [], |r| r.get(0))
        .unwrap();
    assert_eq!(
        stored_revlog, stats.revlog_entries,
        "revlog ids collided; the benchmark would be measuring a smaller deck"
    );

    (col, tempdir, stats)
}

#[derive(Default)]
struct BuildStats {
    reviewed_cards: usize,
    unreviewed_cards: usize,
    multi_topic_cards: usize,
    topic_memberships: usize,
    revlog_entries: usize,
}

/// Nearest-rank percentile: the smallest sample at or above the given rank.
/// Stated explicitly because percentile definitions differ and 25 samples is
/// few enough for the choice to matter.
fn percentile(sorted_ms: &[f64], p: f64) -> f64 {
    let rank = (p * sorted_ms.len() as f64).ceil() as usize;
    sorted_ms[rank.clamp(1, sorted_ms.len()) - 1]
}

fn median(sorted_ms: &[f64]) -> f64 {
    let n = sorted_ms.len();
    if n % 2 == 1 {
        sorted_ms[n / 2]
    } else {
        (sorted_ms[n / 2 - 1] + sorted_ms[n / 2]) / 2.0
    }
}

/// BUILD-DOC §12, test 8: 50k deck, median / p95 / worst case for the dashboard
/// first-load target.
///
/// `#[ignore]`d so `just check` stays fast; `just bench` runs it. It asserts on
/// the budget, so a regression fails the command rather than merely printing a
/// larger number.
#[test]
#[ignore = "benchmark; run with `just bench`"]
fn mastery_benchmark_50k() {
    let build_started = Instant::now();
    let (mut col, _tempdir, stats) = build_deck();
    let build_ms = build_started.elapsed().as_secs_f64() * 1000.0;

    println!("\n=== speedrun mastery benchmark (BUILD-DOC §12) ===");
    println!("seed                  0x{SEED:016X}");
    println!("cards                 {CARD_COUNT}");
    println!("  reviewed            {}", stats.reviewed_cards);
    println!("  unreviewed          {}", stats.unreviewed_cards);
    println!("  two topic tags      {}", stats.multi_topic_cards);
    println!("topics                {TOPIC_COUNT}");
    println!("topic memberships     {}", stats.topic_memberships);
    println!("revlog entries        {}", stats.revlog_entries);
    println!("deck build time       {build_ms:.0} ms (not part of the measurement)");
    println!("timed runs            {RUNS}");

    let mut samples_ms: Vec<f64> = Vec::with_capacity(RUNS);
    for run in 0..RUNS {
        let started = Instant::now();
        let resp = col.topic_mastery(TopicMasteryRequest::default()).unwrap();
        let elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
        // Guard against measuring an empty query: if the fixture were wrong the
        // timings would be fast and meaningless.
        assert_eq!(
            resp.topics.len(),
            TOPIC_COUNT,
            "every topic must come back, or the timing means nothing"
        );
        let counted: u32 = resp.topics.iter().map(|t| t.card_count).sum();
        assert_eq!(
            counted as usize, stats.topic_memberships,
            "card memberships must match the deck that was built"
        );
        assert_eq!(
            resp.cards_without_memory_state as usize, stats.unreviewed_cards,
            "unreviewed cards must be reported, not silently dropped"
        );
        std::hint::black_box(&resp);
        if run == 0 {
            println!("first (cold) call     {elapsed_ms:.1} ms");
        }
        samples_ms.push(elapsed_ms);
    }

    let mut sorted = samples_ms.clone();
    sorted.sort_by(|a, b| a.total_cmp(b));
    let best = sorted[0];
    let med = median(&sorted);
    let p95 = percentile(&sorted, 0.95);
    let worst = sorted[sorted.len() - 1];

    let verdict = |ms: f64| if ms < BUDGET_MS { "PASS" } else { "FAIL" };

    println!("\n--- topic_mastery, all {TOPIC_COUNT} topics, budget {BUDGET_MS:.0} ms ---");
    println!("best                  {best:8.1} ms");
    println!("median                {:8.1} ms   {}", med, verdict(med));
    println!("p95 (nearest-rank)    {:8.1} ms   {}", p95, verdict(p95));
    println!(
        "worst case            {:8.1} ms   {}",
        worst,
        verdict(worst)
    );
    println!(
        "\nOVERALL: {} — dashboard first load < {BUDGET_MS:.0} ms, judged on the worst case\n",
        verdict(worst)
    );

    assert!(
        worst < BUDGET_MS,
        "worst case {worst:.1} ms exceeds the {BUDGET_MS:.0} ms dashboard budget"
    );
}
