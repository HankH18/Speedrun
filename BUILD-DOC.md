# Speedrun — Build Doc

**Exam:** USMLE Step 1 · **Repo:** fork of `ankitects/anki` · **Brainlift:** `BRAINLIFT.md` v1 (§1–§7 complete incl. the AI consensus check; Appendix A pre-registered, not yet run)

This document specifies the build. Every section maps to a numbered requirement in the assignment brief; §16 is the deliverables checklist that proves nothing was dropped.

---

## 1. What is being built, in one paragraph

A fork of Anki that adds a **prediction layer** — the layer stock Anki does not have. Three scores, computed independently, each with a range, each refusing to report when it cannot demonstrate skill against a null model. A Rust-level per-topic mastery query makes the aggregation fast enough to drive a dashboard on 50,000 cards. An Android companion runs the same Rust core and syncs both ways. A pre-registered simulation tests whether allocating study time toward response-congruent practice beats retention-maximizing scheduling.

**The one-sentence thesis feature:** scheduling that allocates study time between retention-maximizing and transfer-maximizing practice, rather than optimizing interval alone.

---

## 2. Architecture

### 2.1 Layer map

```
┌──────────────────────────────────────────────────────────┐
│  Desktop (Qt/aqt)          │  Android (AnkiDroid fork)   │
│  + Speedrun dashboard      │  + Speedrun dashboard        │
└─────────────┬──────────────┴──────────────┬───────────────┘
              │  protobuf                   │  JNI → protobuf
┌─────────────▼─────────────────────────────▼───────────────┐
│  rslib (Rust core)                                        │
│  ├─ scheduler/fsrs      ← unchanged, upstream             │
│  ├─ speedrun/mastery    ← THE RUST CHANGE (new)           │
│  └─ speedrun/scoring    ← score assembly (new)            │
└─────────────┬─────────────────────────────────────────────┘
              │
┌─────────────▼─────────────────────────────────────────────┐
│  SQLite collection — cards, notes, revlog, tags           │
│  + speedrun tables: items, attempts, sources, congruency  │
└───────────────────────────────────────────────────────────┘

  OFFLINE ANALYSIS (Python, not shipped in the app):
  ├─ appendix_a/  simulation harness      → thesis test
  ├─ appendix_b/  calibration             → thresholds, Brier, log loss
  └─ evals/       AI card check, leakage, paraphrase
```

**Design rule:** the app _consumes_ thresholds; the offline analysis _derives_ them. No number in the app is asserted — each one traces to a script in `speedrun-analysis/` that produced it.

### 2.2 Why the prediction layer is the whole product

Stock Anki decomposes into scheduler (FSRS), collection store (SQLite), sync protocol, review UI, and content authoring. The analytics/prediction layer is essentially absent. Commercial tools weld content + analytics + UI and expose no swappable scheduler and no data export. So the layer we add is the one nobody else can be forked for. See `speedrun-docs/architecture.md`.

---

## 3. The Rust change — per-topic mastery query

**Decision: the mastery query, not the points-at-stake queue.** Rationale in `speedrun-docs/rust-change-note.md`; summarized here because the choice is load-bearing.

- It is **read-only**, so the brief's "proof undo works and the collection does not corrupt" is demonstrable rather than perilous.
- All three scores and the coverage map depend on per-topic aggregation.
- The performance target (dashboard first load < 1 s on 50,000 cards) is a genuine reason for it to live in Rust rather than Python — the real justification the one-page note requires.
- The thesis feature is tested in **simulation** (Appendix A), not in the shipped scheduler, so the Rust change does not need to carry it.

### 3.1 Interface

New proto service method. Add to `proto/anki/` — a new `speedrun.proto`, registered in the backend service list.

```proto
message TopicMasteryRequest {
  // Empty = all topics. Otherwise restrict to these topic tags.
  repeated string topic_tags = 1;
  // Cards whose retrievability is computed as of this timestamp.
  int64 as_of_unix_secs = 2;
}

message TopicMastery {
  string topic_tag = 1;
  uint32 card_count = 2;          // cards carrying this topic tag
  uint32 reviewed_count = 3;      // cards with >= 1 review
  uint32 mature_count = 4;        // current interval >= 21 days
  uint32 fsrs_item_count = 5;     // trainable items, per Anki's own definition
  float mean_retrievability = 6;  // FSRS R, cards with memory state only
  float mean_stability = 7;
  float mean_difficulty = 8;
  uint32 review_count = 9;        // revlog entries counted by Anki's own filter
}

message TopicMasteryResponse {
  repeated TopicMastery topics = 1;
  uint32 cards_without_memory_state = 2;  // excluded from the means
}
```

**Design notes that matter for honesty:**

- **CORRECTED.** `fsrs_item_count` and `review_count` are **two different numbers produced by two different stages**, and an earlier version of this doc wrongly collapsed them into one definition. Verified against the pinned tree:
  - `review_count` (field 9) = revlog entries surviving `has_rating_and_affects_scheduling()`, the filter applied at `rslib/src/scheduler/fsrs/params.rs:487`.
  - `fsrs_item_count` (field 5) = items built at `params.rs:506` under the guard `idx >= 1 && delta_t > 0`.
    A card with _k_ qualifying reviews therefore yields **at most _k_ − 1** items: the first review yields none, and same-day repeats yield none because `delta_t` must be positive. Do not invent a new denominator, and do not use one filter for both fields. `BRAINLIFT.md` §7 states this correctly; see also `speedrun-docs/source-citations.md`, Finding E.
- `cards_without_memory_state` is returned so the dashboard can say what the means exclude. A mean computed over an unstated subset is the failure this project is about.
- **CORRECTED.** Retrievability is **computed, not stored** — but it is **not** in `rslib/src/scheduler/fsrs/memory_state.rs`, as an earlier version of this doc claimed. It lives in the `fsrs` crate:
  ```rust
  fsrs::current_retrievability(state: MemoryState, days_elapsed: f32, decay: f32) -> f32
  ```
  Call it with the idiom rslib itself uses (`rslib/src/stats/graphs/retrievability.rs`, `rslib/src/stats/card.rs`):
  ```rust
  fsrs::current_retrievability(
      state.into(),
      elapsed_seconds as f32 / 86_400.0,
      card.decay.unwrap_or(FSRS5_DEFAULT_DECAY),
  )
  ```
  What _is_ in `memory_state.rs` is `get_decay_from_params`, which is probably the source of the original confusion. Do not reimplement the FSRS forgetting curve.

### 3.2 Implementation

- New module `rslib/src/speedrun/mastery.rs`, wired into `rslib/src/lib.rs`.
- Single SQL pass over cards joined to notes for tags, aggregating in Rust. Avoid N+1 — the 50,000-card target is the point.
- Topic tag prefix: `speedrun::topic::<outline-path>`. Cards may carry several; a card counts once per topic tag it holds.
- Use `AnkiError`/`Result` and snafu per Anki's conventions.
- Read-only. No writes, no `OpChanges`, no undo entry.

### 3.3 Required proof (brief §8)

| Requirement            | How                                                                                                                                                                                                                                                |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 3 Rust unit tests      | (a) aggregation correctness on a fixture collection with known values; (b) cards without memory state excluded from means but counted in `card_count`; (c) topic filter returns only requested tags, and a card with two topic tags counts in both |
| 1 Python test          | `pylib` test calling the new backend method and asserting the same fixture values                                                                                                                                                                  |
| Undo works             | Test: run the query between an operation and its undo; assert the undo still succeeds and the collection checksum is unchanged                                                                                                                     |
| No corruption          | Run `just check`; run the query 1,000× against a 50k collection, then Anki's DB check                                                                                                                                                              |
| One-page note          | `speedrun-docs/rust-change-note.md` — finalize against the real implementation                                                                                                                                                                     |
| Upstream files touched | `git diff upstream/main --stat` — generated, not asserted                                                                                                                                                                                          |
| Ships to phone         | Verify the JNI path exposes it in the AnkiDroid fork                                                                                                                                                                                               |

---

## 4. Topic taxonomy and the coverage map (brief §8)

- Source of truth: the **USMLE Content Outline** (organ systems × physician tasks). Not vendor tags.
- Each topic becomes a tag `speedrun::topic::<system>::<subtopic>`.
- `speedrun-analysis/outline/outline.json` holds the outline with published weight ranges; a script asserts every topic in the file is either covered by ≥1 card or explicitly marked uncovered.
- Dashboard shows **percent of outline covered**, weighted by the published item weights, not by raw topic count.
- Below the coverage threshold, **Readiness abstains.** Not a warning — no number.

> **Note:** the market-leading deck is tagged by vendor resource (`#B&B`, `#AMBOSS`), not by the outline, so a student using it cannot answer "what percent of the exam have I covered?" That gap is why this exists (BRAINLIFT §4.2).

---

## 5. The three scores (brief §5)

Never blended. Each ships with: estimate, range, percent of exam covered, confidence indicator, last-updated time, main reasons, and the give-up rule.

### 5.1 Memory — DOK 1

- **Estimate:** mean FSRS retrievability across cards in scope, from the Rust mastery query.
- **Range:** bootstrap over cards (1,000 resamples, fixed seed) → 2.5/97.5 percentiles.
- **Gate:** per-student accept-only-if-better. Fit on the student's reviews, evaluate on held-out recent reviews, and report only if log loss beats the FSRS default-parameter model. Mirrors `params.rs:156`.

### 5.2 Performance — DOK 2/3

- **Estimate:** P(correct) on a novel exam-style item, from a model over topic mastery, item difficulty, response latency, and coverage.
- **Model:** logistic regression. Deliberately simple — the brief requires beating a simpler method, and a simple model that is calibrated beats a complex one that is not.
- **Range:** CI from held-out item predictions.
- **Gate:** accept-only-if-better against a topic-base-rate model, plus a minimum scored-item count derived in Appendix B.

### 5.3 Readiness — DOK 4

- **Estimate:** P(pass Step 1). **No three-digit score** — Step 1 has had no numeric scale since 26 Jan 2022.
- **Range:** calibrated interval, never narrower than the model's own held-out calibration error.
- **Gate:** model-level accept-only-if-better against the **base-rate null**, plus per-student abstention because an individual's Step 1 outcome cannot be held out.
- **Accuracy is forbidden.** At a ~91% base rate a constant "pass" predictor scores 91%. Report Brier and log loss, stratified by predicted-probability band.

### 5.4 Display contract

```
Readiness: 0.72 probability of passing
Likely range 0.61 – 0.81
Coverage: 38% of the outline · Confidence: LOW
Updated 2 minutes ago
Why: strong pharm and micro; no data on renal or repro
Gate: reporting because held-out log loss (0.54) beats the
      base-rate null (0.61). Below that, this score is withheld.
```

The gate line is shown **always**, including when it passes. A student should be able to see the instrument's reasoning, not just its output.

---

## 6. Give-up rule (brief §5, non-negotiable "the app refuses to score when it lacks data")

Primary mechanism is **validation-gating**, not a threshold. Full statement in BRAINLIFT §7. Implementation:

| Score       | Gate                                                             | Fallback when it fails                            |
| ----------- | ---------------------------------------------------------------- | ------------------------------------------------- |
| Memory      | per-student, fitted vs default params on held-out reviews        | show FSRS default-based estimate, labeled as such |
| Performance | per-student, model vs topic base rate on held-out items          | withhold                                          |
| Readiness   | model-level vs base-rate null, plus per-student data sufficiency | withhold entirely                                 |

**Plus a latency plausibility filter.** Sessions whose median response latency is below 20% of the item's target time are flagged and excluded from scoring inputs. This exists because that exact probe was run against three commercial tools and all three responded with a number (`speedrun-docs/teardown-observation-log.md`).

All numeric thresholds are **outputs of Appendix B**, not inputs. Nothing hardcoded.

---

## 7. AI subsystem (brief §3, §8)

Four non-negotiables: every output traces to a named source, passes an eval, beats a simpler method, and both apps run fully with AI off.

### 7.1 Card generation

- Input: one real source document. Store `source_id` + character span on every generated note.
- A card with no traceable span is a **build error**, not a warning.
- `speedrun::ai::generated` tag on every AI note so they can be excluded wholesale.

### 7.2 Item rewording (feeds the paraphrase test)

Generate 2 reworded exam-style items per card, preserving the key learning point and varying surface context — the same manipulation Price et al. used, which is why it is the right operationalization (BRAINLIFT §3.3).

### 7.3 Retrieval must beat a simpler method

- Baselines: BM25 keyword search, and embedding vector search.
- Task: given a topic, retrieve the source passages that support it.
- Report precision@k for all three on a held-out query set. **If the AI method does not win, report that and use the baseline.**

### 7.4 AI card check (brief §8)

- Gold set: 50 Q&A pairs. Generate 50 cards from one real source.
- Report: correct-and-useful / wrong / correct-but-bad-teaching.
- **Set the cutoff before looking.** Write it into `speedrun-analysis/evals/ai_card_cutoff.json` and commit that file before running.

### 7.5 Leakage check (brief §8)

Script flagging any held-out test item or near-copy present in training/generation inputs. Near-copy via normalized n-gram overlap, threshold stated. Must show clean. **Leaked test data zeroes that score.**

### 7.6 AI off

Feature flag. With AI disabled: no generation, no AI retrieval, all three scores still computed and displayed. This is a **required test**, not a config nicety.

---

## 8. Two apps, one engine (brief §4)

- **Desktop:** the fork. Primary tool.
- **Android:** AnkiDroid fork consuming the shared `rslib` over its existing JNI bridge. Cheapest correct path past the 70% cap.
- **iOS:** out of scope; `amgi` demonstrates the C-FFI path exists if it returns later.
- **Scheduler is not reimplemented** in JS or Swift. Both platforms run the same Rust engine.

### 8.1 Sync test (brief §8)

1. 10 cards reviewed on phone offline, 10 different on desktop, reconnect → **all 20 land exactly once**.
2. Same card reviewed on both while offline → conflict rule picks correctly.

**Conflict rule, written down:** last-review-wins by review timestamp; on tie, device ID lexicographic order. Both reviews are retained in revlog; only scheduling state is resolved. Documented in `speedrun-docs/sync-conflict-rule.md`.

Clock-skew case from brief §10: reject review timestamps more than 24h in the future relative to server time, quarantine them, and surface a warning rather than silently accepting.

---

## 9. Appendix A — thesis test (brief §9)

Design is **pre-registered and frozen** in BRAINLIFT Appendix A. This section is implementation only.

- `speedrun-analysis/appendix_a/` — Python, fixed seeds, one command to run.
- Three arms: congruency-aware allocation ON / OFF / stock FSRS.
- Primary: fixed α = 0.5 comparison, pre-registered at **+0.061 d**.
- Secondary: optimal α, predicted at the corner under the analytic model.
- Controls: null case (Δd = 0 → expect ≈ −0.023 d), 2D sweep over Δd × cost multiplier, third axis over Δa.
- **Void conditions:** arm 1 winning under the null; any result above the 0.30 d ceiling.
- Report simulated vs analytic. **Divergence in α\* is a finding**; divergence in the primary means back-calculate the implied Δa before diagnosing a defect.

---

## 10. Appendix B — calibration (brief §10)

- `speedrun-analysis/appendix_b/` — one command, fixed seeds.
- **Required 1:** memory model calibrated — reliability curve plus Brier and log loss on held-back reviews, with a stated temporal cutoff.
- **Required 2:** predict held-back exam-style items from topic mastery, difficulty, timing, coverage.
- **Required 3:** score mapping method written down, with a range. For Step 1 this maps question performance to **pass probability**, not to an invented number.
- Derives every threshold §6 consumes.
- Post-hoc calibration via Platt scaling or isotonic regression, fit on a set disjoint from both training and evaluation.

"We calibrated memory but cannot yet prove the projected score" scores higher than a polished number you cannot back up — so if Required 3 does not validate, say so plainly.

---

## 11. Required tests (brief §8) — complete list

| # | Test            | Where                                 | Pass condition                                                                                              |
| - | --------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 1 | Rust change     | `rslib/src/speedrun/`                 | 3 Rust + 1 Python test green; undo intact; no corruption                                                    |
| 2 | Sync            | `speedrun-analysis/tests/sync/`       | 20 reviews land once; conflict rule correct                                                                 |
| 3 | Coverage map    | dashboard + script                    | every outline topic marked; percent shown; abstains below line                                              |
| 4 | Paraphrase      | `speedrun-analysis/evals/paraphrase/` | 30 cards × 2 rewordings; **report the gap** between card recall and rewording accuracy                      |
| 5 | Leakage         | `speedrun-analysis/evals/leakage.py`  | shows clean                                                                                                 |
| 6 | AI card check   | `speedrun-analysis/evals/ai_cards.py` | cutoff pre-committed; three-way breakdown reported                                                          |
| 7 | Crash + offline | `speedrun-analysis/tests/crash/`      | kill mid-review 20× per app, zero corrupted collections; AI offline degrades cleanly, both apps still score |
| 8 | Benchmark       | `just bench`                          | 50k deck; median, p95, worst case for every §12 target                                                      |

**Test 4 is the thesis instrument.** If card recall and rewording accuracy match, the performance model is copying the memory model. That is a DOK 1 vs DOK 2 test run directly, and reporting the gap is the deliverable — including if the gap is zero.

---

## 12. Performance targets (brief §10)

One command, `just bench`, printing median / p95 / worst case:

| Target                    | Budget                                                 |
| ------------------------- | ------------------------------------------------------ |
| Button press acknowledged | p95 < 50 ms, both platforms                            |
| Next card after grading   | p95 < 100 ms                                           |
| Dashboard first load      | < 1 s; refresh < 500 ms; no frozen screen              |
| Normal session sync       | < 5 s                                                  |
| Memory on 50,000 cards    | under a stated limit, desktop and midrange phone       |
| Cold start                | < 5 s desktop, < 4 s phone; nothing blocks UI > 100 ms |
| Crash test                | zero corrupted collections                             |

One self-chosen number does not count. All three statistics, every target.

---

## 13. Adversarial cases (brief §10)

They will try to break it. Each gets an explicit behavior and a test:

| Case                                            | Required behavior                                                                    |
| ----------------------------------------------- | ------------------------------------------------------------------------------------ |
| Memorizes wording, fails rewordings             | Performance score diverges from Memory; the gap is the headline                      |
| Huge deck missing a heavily weighted topic      | Coverage-weighted percent drops; Readiness abstains                                  |
| Two cards stating opposite facts                | Flagged as contradiction; excluded from mastery until resolved                       |
| Source with hidden text attacking the generator | Generated content is data, not instructions; injection test in the eval set          |
| Tapping Good without reading                    | Latency filter excludes the session (§6)                                             |
| Topic with no history                           | Abstain for that topic; excluded from means, counted in `cards_without_memory_state` |
| Accurate but too slow                           | Reported separately; latency is a feature of the Performance model                   |
| AI cards correct but useless                    | Third category in the AI card check (§7.4)                                           |
| Score rose only from leakage                    | Leakage check must show clean before any score is reported                           |
| AI offline or returning garbage                 | Degrade cleanly; both apps keep working and still score                              |
| Same card on two devices offline                | Conflict rule (§8.1)                                                                 |
| Phone with wrong clock, offline mid-sync        | Reject >24h future timestamps; quarantine; warn                                      |
| Crash mid-review                                | Zero corruption across 20 kills per app                                              |
| Corrupt deck / broken images                    | Import fails loudly with a specific error; no partial state                          |

---

## 14. Build order

Order is chosen so that each stage produces something verifiable and nothing later depends on something unbuilt.

| Stage | Work                               | Done when                                                              |
| ----- | ---------------------------------- | ---------------------------------------------------------------------- |
| **0** | Fork builds clean                  | `just check` passes on a clean checkout                                |
| **1** | Rust change                        | proto compiles, query returns, 3 Rust + 1 Python test green, committed |
| **2** | Topic taxonomy + a real deck       | outline JSON loaded; ≥1 organ system tagged; coverage script runs      |
| **3** | Review loop + three scores + gates | scores render with ranges; gates enforced; abstains when thin          |
| **4** | Appendix B calibration             | thresholds derived, not asserted; reliability curve produced           |
| **5** | Appendix A simulation              | pre-registered run executed; null case and sweep reported              |
| **6** | AI subsystem + evals               | traceability enforced; card check, leakage, retrieval comparison       |
| **7** | Android companion + sync           | 20-review test passes; conflict rule verified                          |
| **8** | Packaging + benchmark + crash      | installers built; `just bench` reports; 20 kills per app               |
| **9** | Demo video                         | 3–5 min, opens with the POV in one sentence                            |

**Stage 1 is tonight's target.** It lifts the hard cap from 50% and everything downstream consumes it.

---

## 15. Repo conventions

- Speedrun code lives in `rslib/src/speedrun/`, `speedrun-analysis/`, `speedrun-docs/`. Upstream trees stay clean so `git diff upstream/main --stat` remains a truthful file list.
- **`CONTRIBUTORS` is a legitimate exception to that rule, not a violation of it.** The file exists precisely so downstream contributors can add themselves, and upstream's own `check:minilints` **fails the build** unless every commit author appears in it — the error is `Author <you> NOT found in list`. Adding your name is therefore required to satisfy `just check`, not an incursion into upstream's tree. It is one line, and it is the only upstream file this fork modifies.
- Two further edits are required for a green `just check` on a fresh clone and are not code changes: initialise the installer submodules (`git submodule update --init`), or `qt/tests/test_installer.py` fails with `Unable to clone application template`; and run `just fix-fmt` before committing, because `dprint` formats Markdown too and will reject prose written with `*emphasis*` instead of `_emphasis_`.
- Speedrun-specific agent instructions go in `.claude/user.md` (referenced by upstream's `CLAUDE.md`) — **do not edit upstream's `CLAUDE.md`**.
- Every derived number in a doc cites the script that produced it.
- Source citations pin **commit SHA + symbol**, never line number alone.
- `.gitignore` already excludes `*.anki2` and `data/holdout/`. Held-out data never enters the repo.

---

## 16. Deliverables checklist (brief §7, §12)

**Repo**

- [x] Public fork under AGPL-3.0-or-later, credit to Anki
- [x] Exam stated up front in README
- [x] Brainlift v1 — §1–§7 complete, consensus check run twice with verbatim transcripts, Appendix A pre-registered
- [ ] Build instructions for both apps
- [x] Architecture overview (`speedrun-docs/architecture.md`)
- [ ] Rust note, finalized against the implementation
- [ ] Files touched (`git diff upstream/main --stat`)

**Build**

- [ ] Anki forked **and building**
- [ ] Rust change end to end: diff, 3 Rust tests, 1 Python test
- [ ] Review loop on the exam deck
- [ ] Three scores with ranges, give-up rule enforced
- [ ] Desktop installer, clean machine
- [ ] Phone app on shared engine, bidirectional sync, offline
- [ ] AI: traced to source, eval on held-back data with stated cutoff, beats keyword/vector, app scores with AI off

**Evidence**

- [ ] Memory model calibrated: reliability curve + Brier/log loss on held-back reviews
- [ ] Performance model accuracy on held-back items
- [ ] Score mapping method written down, with a range
- [ ] Appendix A run: three arms, equal study time
- [ ] Paraphrase test, leakage check, crash tests, benchmark
- [ ] Packaged desktop installer and phone build; conflict handling documented
- [ ] Brainlift §8 updated with what the build taught

**Proof**

- [ ] Commit hash · clean build recording · test results · install recording · phone review appearing on desktop after sync · eval numbers
- [ ] Demo video 3–5 min: POV in one sentence, the feature it produced, review session, Rust change in action, phone→desktop sync, three scores with ranges, AI features, results

---

## 17. Grading map

| Criterion                           | Weight | Where it lives                          |
| ----------------------------------- | ------ | --------------------------------------- |
| Brainlift                           | 25%    | `BRAINLIFT.md` v1 — §1–§7 complete      |
| Rust change and fit                 | 15%    | §3                                      |
| Score accuracy + honest uncertainty | 15%    | §5, §10                                 |
| Testing the thesis                  | 15%    | §9                                      |
| AI checking and safety              | 10%    | §7                                      |
| Fair tests others can rerun         | 8%     | §9, §10, §11 — fixed seeds, one command |
| Two apps, one engine, sync          | 7%     | §8                                      |
| Useful product, clean UX            | 5%     | §5.4                                    |

**Hard limits to stay clear of:** no real Rust change → 50% max. No phone companion → 70% max. Either app fails on a clean device → 50% max. No rerunnable setup or no held-back testing → 60% max. Invented or misleading readiness numbers → automatic fail. Leaked test data → that score is zero. AI claims with no traceable source → AI section zero.
