# The Rust change — one-page note

**Status: PENDING.** The fork does not yet exist. This file states what the change will be and what this note must contain, so the requirement is visible rather than absent.

---

## Provisional scope

**Per-topic mastery query** — returns per-topic mastery and average recall over a 50,000-card collection, fast enough to drive the dashboard.

### Why this belongs in Rust, not Python

All three scores and the coverage map depend on per-topic aggregation across the full collection. The performance targets are dashboard first load under 1 second and refresh under 500 ms, with nothing blocking the UI for more than 100 ms. Aggregating FSRS memory state across 50,000 cards per dashboard render is not a Python-layer operation — it belongs next to the collection in `rslib`, behind a protobuf message, where both the desktop app and the phone companion consume the same implementation.

This also satisfies a build constraint that is easy to miss: **the change ships to the phone too.** A Python-side implementation would have to be written twice and would drift.

### Alternative still under consideration

**Points-at-stake queue** — ordering due cards by topic weight × weakness, with a new protobuf message. This ties more directly to POV 1 (transfer moderators should influence scheduling, not just interval) and would place the thesis feature inside the scheduler, which makes the Appendix A ablation (assignment brief §9) cleaner. The tradeoff is that it does not address the dashboard-latency requirement, which the mastery query does.

Decision to be recorded here once the fork is building.

---

## What this note must contain before final submission

- [ ] The diff
- [ ] 3 Rust unit tests
- [ ] 1 Python test calling into the change
- [ ] Proof undo works and the collection does not corrupt
- [ ] Why this belongs in Rust (drafted above; to be finalized against the real implementation)
- [ ] The upstream files touched, with commit-pinned permalinks
- [ ] Verification that the change works on the phone build

---

## Citation discipline

Source references in this project are pinned to **commit SHA plus symbol name**, not line number. Line numbers drift with upstream refactors; a commit-pinned permalink does not.

Source citations in `BRAINLIFT.md` were previously marked **UNVERIFIED** because `git clone` was blocked by an egress proxy during research and GitHub's rendered line gutter was unreadable through the fetch layer. No plausible-looking line number was substituted for a real one.

**Status: RESOLVED — and the upgrade is recorded rather than presented as clean.** All four citations have now been checked against a full clone pinned to `d735cd25d076051c6788b5a5acf65b57b9ea7277`. Two survived, two did not. The complete audit is in `speedrun-docs/source-citations.md`; the headline is that the FSRS review-count threshold I cited **does not exist**, and the review-count SQL below was **wrong**.

### Corrected analysis SQL

The Rust helper that decides whether a revlog row counts is
[`has_rating_and_affects_scheduling`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/revlog/mod.rs#L126), which is `has_rating() && !is_cramming()`. In SQL:

```sql
-- Correct. Mirrors RevlogEntry::has_rating_and_affects_scheduling.
--
-- Column-name trap, verified against rslib/src/storage/schema11.sql and the row
-- readers in rslib/src/storage/revlog/mod.rs:
--   `ease`   holds the BUTTON PRESSED (1-4; 0 = no rating)  -> Rust `button_chosen`
--   `factor` holds the EASE FACTOR                          -> Rust `ease_factor`
-- The column called `ease` is not the ease factor. Reading it as one silently
-- changes what the query means.
--
-- `NOT (type = 3 AND factor = 0)` excludes cram reviews: filtered-deck reviews
-- taken with "reschedule cards based on my answers" disabled.
ease > 0 AND NOT (type = 3 AND factor = 0)
```

**Superseded, do not reuse:** `ease > 0 AND type NOT IN (4, 5)`. Two defects. It never excluded cram reviews, so it is **over-inclusive** — and the error runs in the damaging direction, because it *inflates* review counts, which is exactly the quantity every "do I have enough data" decision in this project depends on. **Any review count computed before this correction is inflated for any collection that has used a filtered deck in preview mode, and must be recomputed before it is cited.** The `type NOT IN (4,5)` clause was separately redundant: Manual (4) and Rescheduled (5) rows are written with `ease = 0`, so `ease > 0` had already removed them.

### Verification commands, with outcomes

```bash
# 1. FSRS optimizer minimum-review threshold -> NOT IN rslib. IT IS IN THE CRATE.
#    This grep returns only interval clamping (min_and_max_review_intervals,
#    MINIMUM_EASE_FACTOR), which is unrelated. compute_params does not gate on
#    review count; enforcement was removed from rslib in PR #3106 and PR #3246.
#    BUT: searching rslib alone is what made me report "no threshold exists",
#    which was wrong. compute_params delegates fitting to the fsrs crate, which
#    returns DEFAULT_PARAMETERS untouched below 8 items (training.rs:319) and
#    skips gradient training below 64. Search the crate too, not just rslib:
rg -n 'FSRS|min_.*review|MIN_.*REVIEW' --type rust rslib/ | rg -i 'min|threshold|enough'
#    ...then, against a checkout of the pinned fsrs-rs version:
rg -n 'train_set.len\(\) <|DEFAULT_PARAMETERS' src/training.rs

# 2. Proof of absence for the "400 is dead code" claim -> CONFIRMED dead.
#    10 hits, none of them an active threshold check.
rg -n '\b400\b' --type rust

# 3. The revlog helper -> VERIFIED; approximation above was wrong.
rg -n 'has_rating_and_affects_scheduling' -A 15

# 4. User-facing strings live in Fluent files -> VERIFIED verbatim.
#    deck-config-not-enough-history = Insufficient review history to perform this operation.
rg -n -i 'optimi[sz]|not enough|insufficient' ftl/
```
