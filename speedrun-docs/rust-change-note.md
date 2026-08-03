# The Rust change — one-page note

**Status: IMPLEMENTED AND GREEN**, with one item outstanding, named in "What is not done" below.

Fork base: `ankitects/anki` @ [`d735cd25d076051c6788b5a5acf65b57b9ea7277`](https://github.com/ankitects/anki/tree/d735cd25d076051c6788b5a5acf65b57b9ea7277).

---

## 1. What was built

`Collection::topic_mastery` — a read-only per-topic aggregation over cards tagged `speedrun::topic::*`, exposed as a new protobuf service method so desktop and phone consume one implementation.

It returns, per topic tag: `card_count`, `reviewed_count`, `mature_count`, `fsrs_item_count`, `review_count`, and the means of FSRS retrievability, stability and difficulty. The response also carries `cards_without_memory_state`, so a caller can state what the means exclude rather than quietly averaging over an unstated subset.

**Decision recorded:** the mastery query, **not** the points-at-stake queue. The queue would have mutated queue construction; the mastery query is read-only, which is what makes the brief's "prove undo works and the collection does not corrupt" demonstrable instead of perilous. See §6.

### Why this belongs in Rust, not Python

Three reasons, in order of how much weight they actually carry:

1. **It is on the dashboard's critical path at collection scale.** Every score and the coverage map depend on per-topic aggregation over the whole collection; the target is first load under 1 s at 50,000 cards. Doing it in `pylib` means moving every card row and every revlog row across the protobuf boundary on each refresh — 210,000 rows for the benchmark deck below — so Python can reduce them to 20 numbers. In `rslib` the reduction happens where the rows already are, and only the 20 numbers cross. That is a structural argument about where the aggregation sits, not a benchmarked comparison against a Python version — see the caveat under the measurement below.
2. **It ships to the phone.** Written in `pylib`, it would have to be written a second time for the Android app and would drift. Written in `rslib`, both consume the same code by construction.
3. **It reuses Anki's own definitions rather than re-deriving them.** `has_rating_and_affects_scheduling`, the `idx >= 1 && delta_t > 0` item rule, and `fsrs::current_retrievability` are all in-crate. A Python implementation would have had to reimplement the FSRS forgetting curve, which is exactly the error this project exists to avoid.

The performance claim is **measured, not asserted**: `rslib/src/speedrun/bench.rs`, run with `just bench`, builds a fixed-seed 50,000-card / 160,000-revlog deck and fails the run if the worst of 25 timed calls exceeds the 1,000 ms budget.

Verbatim stdout of `just bench`, not a summary of it:

```
=== speedrun mastery benchmark (BUILD-DOC §12) ===
seed                  0x5EED20240A17C0DE
cards                 50000
  reviewed            40000
  unreviewed          10000
  two topic tags      7143
topics                20
topic memberships     57143
revlog entries        160000
deck build time       644 ms (not part of the measurement)
timed runs            25
first (cold) call     99.4 ms

--- topic_mastery, all 20 topics, budget 1000 ms ---
best                      98.1 ms
median                   100.8 ms   PASS
p95 (nearest-rank)       103.5 ms   PASS
worst case               105.9 ms   PASS

OVERALL: PASS — dashboard first load < 1000 ms, judged on the worst case
```

One run, release profile, on an Apple Silicon laptop — a single machine, not a claim about all hardware. The deck shape is checked by the benchmark itself rather than trusted: it asserts all 20 topics come back, that summed `card_count` equals the 57,143 memberships it built, that `cards_without_memory_state` equals the 10,000 it left unreviewed, and that no revlog id collided (`add.sql` is `INSERT OR IGNORE`, so a collision would silently shrink the workload and make the timing flattering). The headroom is roughly 10× on the budget, and the spread between best and worst is under 8 ms, which is what a walk with no per-card query should look like. Nothing here is a claim about a **Python** implementation's speed: no Python version was written, so the comparison is unmeasured and is not made.

---

## 2. The diff

Generated, not asserted:

```console
$ git diff upstream/main --stat -- . ':!speedrun-docs' ':!speedrun-analysis' ':!BUILD-DOC.md' ':!BRAINLIFT.md'
 .gitignore                    |  17 +
 CONTRIBUTORS                  |   1 +
 README.md                     | 122 ++++++--
 justfile                      |   4 +
 proto/anki/speedrun.proto     |  54 ++++
 pylib/tests/test_speedrun.py  |  94 ++++++
 rslib/proto/src/lib.rs        |   1 +
 rslib/src/lib.rs              |   1 +
 rslib/src/speedrun/mastery.rs | 705 ++++++++++++++++++++++++++++++++++++++++++
 rslib/src/speedrun/mod.rs     |  19 ++
 10 files changed, 1000 insertions(+), 18 deletions(-)
```

`rslib/src/speedrun/bench.rs` (§1) is absent from that listing only because it is still untracked at the time of writing; `git diff` cannot see it. Re-run the command rather than trusting these numbers — they drift with every commit, and an earlier revision of this note carried a stale copy (`justfile | 6 +`, 925 insertions) that no longer matched the tree.

The entire edit to upstream Rust is two lines:

```diff
--- a/rslib/proto/src/lib.rs
+++ b/rslib/proto/src/lib.rs
@@ -33,6 +33,7 @@ protobuf!(search, "search");
+protobuf!(speedrun, "speedrun");
 protobuf!(stats, "stats");

--- a/rslib/src/lib.rs
+++ b/rslib/src/lib.rs
@@ -38,6 +38,7 @@ pub mod services;
+pub mod speedrun;
 mod stats;
```

Everything else is new files under `rslib/src/speedrun/`, `proto/anki/speedrun.proto` and `pylib/tests/`. The proto is as specified in BUILD-DOC §3.1, with the field comments tightened to state the two corrections in §3 below at the point of use.

---

## 3. Two corrections to the spec, both found by reading source

Both were written into BUILD-DOC before the code existed, and both were wrong. They are recorded here because a doc that silently self-corrects is not evidence of anything.

**(a) Retrievability is not in `memory_state.rs`.** It is `fsrs::current_retrievability`, in the `fsrs` crate. `memory_state.rs` contains `get_decay_from_params`, which is probably the source of the confusion. The implementation calls it with the same three-argument idiom rslib itself uses in [`stats/graphs/retrievability.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/stats/graphs/retrievability.rs) and [`stats/card.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/stats/card.rs) — `state.into()`, elapsed seconds ÷ 86,400, `card.decay.unwrap_or(FSRS5_DEFAULT_DECAY)`. The forgetting curve is **not** reimplemented here.

**(b) `review_count` and `fsrs_item_count` are two stages, not one definition.** They come from two different points in [`scheduler/fsrs/params.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs):

| Field                 | Stage                                                                      | Where (pinned tree)                                      |
| --------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------- |
| `review_count` (9)    | the filter — `entries.retain(\|e\| e.has_rating_and_affects_scheduling())` | `params.rs:487`, inside `pub(crate) fn reviews_for_fsrs` |
| `fsrs_item_count` (5) | item construction — the guard `idx >= 1 && delta_t > 0`                    | `params.rs:506`, same function                           |

A card with _k_ qualifying reviews therefore yields **at most _k_ − 1** items: the first review yields none, and same-day repeats yield none because `delta_t` must be positive. The implementation applies both stages in the order Anki does, and the Rust fixture asserts the relationship directly — card A has 3 counted reviews and 2 items.

`delta_t` is measured in whole days against the collection's day boundary, so `mastery.rs` takes its reference point from `Collection::timing_today().next_day_at` and replicates `RevlogEntry::days_elapsed` (`params.rs:544`) — private to that module, so it cannot be called from here.

---

## 4. One deviation from the spec, stated plainly

BUILD-DOC §3.2 says **"single SQL pass over cards joined to notes for tags."** The implementation uses **two** single-pass queries:

1. `cards c INNER JOIN notes n ON c.nid = n.id WHERE n.tags LIKE '%speedrun::topic::%'` — one row per card, carrying `data` (memory state, decay, last review time) and the note's tag string. The `LIKE` is only a prefilter; `tags::split_tags` does the authoritative split, because `notes.tags` is stored space-padded by `tags::join_tags`.
2. `get_all_revlog_entries_in_card_order()` — every revlog row once, in card order.

**Why:** `fsrs_item_count` cannot be computed from a row count. The `idx >= 1 && delta_t > 0` guard needs each card's reviews walked **in order**, with the previous entry in hand to compute `delta_t`. That is not expressible in the card query, and doing it per card would be exactly the N+1 the spec was written to prevent.

**Why this is not a regression against the intent:** neither query is per-card. The cost is **O(cards + revlog)** with two prepared statements (`prepare_cached` in both cases — the second inside `get_all_revlog_entries_in_card_order`), not O(cards) statements. The spec's target — no N+1 at 50,000 cards — is met; the literal wording "single SQL pass" is not. BUILD-DOC should be read as one pass _per table_, and this note is the correction.

Two precisions, so "two queries" is not read as more than it says. **(i)** These are the two _table scans_. `timing_today()` reads config besides them, so the count of SQL statements issued per call is higher than two; the claim is about the passes over card and revlog data. **(ii)** The revlog query is **not** restricted to the tagged cards — `get_all_revlog_entries_in_card_order` takes no predicate and returns the whole table. The per-card totals it builds are only ever read back for cards that survived query 1, so the answer is right, but on a collection where few cards are tagged this reads more rows than it needs to. It is the shape the benchmark measures (every card in the 50,000-card deck is tagged, so it is also the worst case for that ratio) and it is O(revlog) either way, not N+1 — but it is a scan, not a lookup, and the code comment now says so.

---

## 5. One judgement call: card maturity has no shared constant upstream

There is no crate-level maturity constant in rslib. `rg -n '\b21\b' rslib/src/stats/graphs/` returns **five** hits, and they do not all mean the same thing:

- [`stats/graphs/card_counts.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/stats/graphs/card_counts.rs) — `if card.interval < 21` — the **card's current** interval.
- [`stats/graphs/today.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/stats/graphs/today.rs) — `if review.last_interval >= 21` — the interval **at review time**.
- [`stats/graphs/buttons.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/stats/graphs/buttons.rs) — `if review.last_interval < 21` — likewise, at review time.
- [`stats/graphs/reviews.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/stats/graphs/reviews.rs) — `if review.last_interval < 21` — likewise.
- [`stats/graphs/retention.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/stats/graphs/retention.rs) — `const MATURE_IVL: i32 = 21; // mature interval is 21 days`, then `review.last_interval < MATURE_IVL` — also at review time.

**Correction, recorded rather than quietly fixed.** An earlier draft of this section said "the literal 21 is duplicated in three places" and "there is no `MATURE_INTERVAL` in rslib". Both were sloppy. The count is five, not three — `reviews.rs` and `retention.rs` were missed — and `retention.rs` does have a _named_ constant, `MATURE_IVL`. It is declared inside a closure body, so it is not reachable from another module and is not a shared constant; the substantive claim survives, the arithmetic did not. Same undercount was in the `MATURE_INTERVAL_DAYS` doc comment in `mastery.rs` and has been fixed there too.

`mature_count` is a property of the collection now, not of its history, and four of the five hits above are properties of a _review_. So we matched the one that is not: **`card_counts.rs`** — a card of type `Review` whose current interval is ≥ 21 days. The constant is named `MATURE_INTERVAL_DAYS` in `mastery.rs` with that provenance in its doc comment, so the choice is visible rather than a bare `21`.

---

## 6. Tests

All green under `just check`. Rust: `cargo test -p anki --lib speedrun`.

### Rust — 3 aggregation tests (the brief's requirement)

Against a fixture whose every aggregate is hand-checkable: card A `cardio`, mature (ivl 30), 3 reviews, memory state (S 40, D 5); card B `cardio` + `renal`, young (ivl 5), memory state (S 10, D 7); card C `renal`, new, **no** memory state.

| # | Test                                                             | What it pins                                                                                                                                          |
| - | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| a | `aggregation_matches_known_values`                               | Every count and mean against hand-computed values, including `review_count` 3 vs `fsrs_item_count` 2 — the _k_ − 1 relation of §3b                    |
| b | `cards_without_memory_state_are_excluded_from_means_but_counted` | Card C is in `card_count` but not in the means: `renal` mean stability must be B's 10.0, **not** a diluted 5.0; and `cards_without_memory_state` is 1 |
| c | `topic_filter_and_multi_tagged_cards`                            | Filtering returns only requested tags; card B counts under both of its topics — 3 cards, 4 memberships                                                |

Tests live in an in-crate `#[cfg(test)] mod test`, not `rslib/tests/`, because `Card::memory_state`, `Card::interval` and `Collection::new` are `pub(crate)` and unreachable from an integration-test crate.

### Python — 4 tests through the generated backend method

`pylib/tests/test_speedrun.py` calls `col._backend.topic_mastery(...)` and mirrors the Rust fixture's topology: `test_empty_collection_returns_no_topics`, `test_aggregates_match_the_rust_fixture_topology`, `test_topic_filter_restricts_results`, `test_untagged_cards_are_ignored`. FSRS memory state cannot be set from pylib, so the means are asserted on the Rust side and the counts and filter on this one.

One non-obvious line, kept with a comment: `import anki.speedrun_pb2` is load-bearing. Without it the generated method raises `AttributeError: module 'anki' has no attribute 'speedrun_pb2'`.

### Undo works, and the collection does not corrupt

The argument is structural — `topic_mastery` opens no transaction, issues only `SELECT`s, and produces no `OpChanges` — but the argument is not the proof. Four further Rust tests are:

- `the_only_writes_are_ankis_one_time_scheduler_backfill` — pins the one honest complication. `topic_mastery` calls `timing_today()` for the day boundary, which on a collection that has never had them lazily persists two config keys, `rollover` and `localOffset`. Both are written **outside** any transaction, so neither takes an undo entry; both are one-time. The test asserts exactly two rows, both in `config`, the undo stack unchanged either side — and then that 100 further queries write **zero** rows.
- `topic_mastery_itself_triggers_the_backfill_on_a_cold_collection` — closes an attribution gap in the test above, which calls `timing_today()` explicitly and so would still have passed if `topic_mastery` had never called it. This one calls **only** `topic_mastery` on a cold collection and asserts that the very first call is what writes those two rows, and that it still takes no undo entry. Without it the caveat in the bullet above was asserted about `topic_mastery` but only ever demonstrated about `timing_today`.
- `query_between_operation_and_undo_is_inert` — runs the query between a real `add_note` (which goes through `transact(Op::AddNote, ..)`) and its undo. Asserts `undo_status()` is identical in all three components either side of the query, that a full snapshot of cards + notes + revlog + collection mtime + `changes_since_open()` is byte-identical, that the undo then reverts `Op::AddNote` (not the query), and that the same query afterwards answers 2 instead of 3 — so the mid-operation call demonstrably read the live collection rather than a stale copy.
- `repeated_queries_leave_the_collection_identical` — 100 consecutive queries with `as_of` pinned so the wall clock cannot move the answer; identical response every time, identical snapshot at the end, `quick_check_corrupt()` still clean, undo stack still empty of our doing.

**Where these tests are weak, stated plainly.** No test that asserts _"calling X changed nothing"_ can be made to fail by deleting the call to X. Delete the `topic_mastery` call from the middle of `query_between_operation_and_undo_is_inert` and the surviving assertions are all trivially true. That is structural, not a defect in this particular test, and it means a green run is not by itself evidence the query ran.

What the tests are worth was therefore established by **mutation**, not by their passing:

| Sabotage injected into `topic_mastery`                                               | Result                                                                                                              |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| One stray non-transactional row write (`update cards set mod = mod where id = …`)    | 3 of 4 failed — every test that watches rows                                                                        |
| `self.transact(Op::UpdateCard, \|_\| Ok(()))` — an undo step that writes **no** rows | 2 of 4 failed — **only** the two that read `undo_status()`; the snapshot and row-count assertions both stayed green |

The second row is the load-bearing one. An empty transaction commits **zero** rows, so `changes_since_open()` does not move and the cards/notes/revlog/mtime snapshot is byte-identical — the corruption test and the 100-query test see nothing at all. `undo_status()` is the only observable that changes. Any future edit that reaches for `transact` here is caught by exactly two assertions in the module and nothing else, which is why they are worth keeping and why this is recorded in the tests' own doc comments rather than left to be rediscovered.

The read-only claim is also checkable mechanically. The test module starts at `#[cfg(test)]` on line 268, so:

```bash
awk 'NR<268' rslib/src/speedrun/mastery.rs \
  | grep -nE 'update_|add_|set_|transact|OpChanges|INSERT|UPDATE|DELETE'
```

returns two hits, both inside the same doc comment — `no`OpChanges`` and `outside any transaction` — and no executable line at all. (An earlier revision of this note said "exactly one hit"; that was true of a shorter doc comment and stopped being true when the caveat above was written into it. The number is a property of the prose, not of the code, which is why the command is given rather than just its output.)

---

## 7. Upstream files touched, with commit-pinned permalinks

Pinned to the fork base, `d735cd25d076051c6788b5a5acf65b57b9ea7277`.

| Upstream file                                                                                                                                                                                                        | Change            | Why                                                                              |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------- |
| [`rslib/proto/src/lib.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/proto/src/lib.rs)                                                                                   | +1                | `protobuf!(speedrun, "speedrun");` — registers the new proto                     |
| [`rslib/src/lib.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/lib.rs)                                                                                               | +1                | `pub mod speedrun;`                                                              |
| [`justfile`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/justfile)                                                                                                               | +4                | `just bench` recipe; excluded from `just check`                                  |
| [`CONTRIBUTORS`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/CONTRIBUTORS)                                                                                                       | +1                | `check:minilints` fails the build without the author listed                      |
| [`README.md`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/README.md), [`.gitignore`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/.gitignore) | fork housekeeping | Not part of the change; listed so the diffstat is not read as smaller than it is |

New files, owned entirely by this fork: `proto/anki/speedrun.proto`, `rslib/src/speedrun/{mod.rs,mastery.rs,bench.rs}`, `pylib/tests/test_speedrun.py`.

Upstream symbols consumed without modification: `RevlogEntry::has_rating_and_affects_scheduling` ([`rslib/src/revlog/mod.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/revlog/mod.rs)), `SqliteStorage::get_all_revlog_entries_in_card_order` ([`rslib/src/storage/revlog/mod.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/storage/revlog/mod.rs)), `CardData::memory_state` ([`rslib/src/storage/card/data.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/storage/card/data.rs)), `tags::split_tags` ([`rslib/src/tags/mod.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/tags/mod.rs)), `Collection::timing_today` ([`rslib/src/scheduler/mod.rs`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/mod.rs)).

---

## 8. What is not done: the phone

**The change has not been built for or run on Android.** It is not verified on the phone, and this note does not claim it is.

What _is_ true: the method is on the collection service, so the generated `Backend` forwarder exists and the Android backend would reach it through the same dispatch as every other method — no special wiring was needed, and rslib already carries `rslib/src/ankidroid/` for that consumer.

What makes this more than a formality, and the reason it is called out rather than assumed: **adding `speedrun.proto` renumbers services.** Service indices come from the descriptor pool in sorted-file order, and `speedrun` sorts between `search` and `stats`. Verified by removing `proto/anki/speedrun.proto` and regenerating:

| Service    | Upstream index | This fork |
| ---------- | -------------- | --------- |
| `search`   | 28             | 28        |
| `media`    | 40             | 40        |
| `speedrun` | —              | **42**    |
| `stats`    | 42             | **44**    |
| `tags`     | 44             | **46**    |

Any client generated against a _different_ proto set — which is exactly what a separately-built Android backend is — will address the wrong service by number. So the remaining phone work is: build rslib from this fork into the Android backend's JNI library, regenerate the Kotlin protobuf stubs **from this fork's protos** so the indices agree, and call `topic_mastery` on a real device against a real collection.

Until that has run, the phone row of BUILD-DOC §3.3 is open.

---

## 9. Citation discipline

Source references in this project are pinned to **commit SHA plus symbol name**, not line number. Line numbers drift with upstream refactors; a commit-pinned permalink does not. Where a line number appears above (`params.rs:487`, `params.rs:506`) it is given _in addition to_ the symbol name and labelled as being in the pinned tree.

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

**Superseded, do not reuse:** `ease > 0 AND type NOT IN (4, 5)`. Two defects. It never excluded cram reviews, so it is **over-inclusive** — and the error runs in the damaging direction, because it _inflates_ review counts, which is exactly the quantity every "do I have enough data" decision in this project depends on. **Any review count computed before this correction is inflated for any collection that has used a filtered deck in preview mode, and must be recomputed before it is cited.** The `type NOT IN (4,5)` clause was separately redundant: Manual (4) and Rescheduled (5) rows are written with `ease = 0`, so `ease > 0` had already removed them.

The Rust implementation does not carry this SQL. It calls `has_rating_and_affects_scheduling` directly, so it cannot drift from the definition — the SQL above exists for the offline analysis scripts, which query the collection file without linking rslib.

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

# 5. Card maturity has no shared constant -> CONFIRMED, but the count was wrong.
#    FIVE hits, not the three an earlier draft claimed: card_counts.rs, today.rs,
#    buttons.rs, reviews.rs, and a closure-local `const MATURE_IVL` in
#    retention.rs. None is reachable from another module, so "no shared constant"
#    holds; "three" did not. See section 5.
rg -n '\b21\b' rslib/src/stats/graphs/

# 6. Service renumbering (section 8) -> CONFIRMED by removing the proto and
#    regenerating; stats moves 42 -> 44, tags 44 -> 46.
rg -n 'run_(speedrun|stats|tags)_service_method' target/debug/build/anki-*/out/backend.rs
```
