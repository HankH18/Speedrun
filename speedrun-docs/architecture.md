# Architecture overview

**Status: PENDING.** No code exists yet. What follows is the layer analysis the design rests on, which is complete, plus the shape of the intended system.

---

## The stack, decomposed

Comparison writing treats study tools as monolithic products. Anki's stack is not monolithic, and the seams matter:

| Layer                      | Stock Anki                                  | Speedrun's relationship to it                                    |
| -------------------------- | ------------------------------------------- | ---------------------------------------------------------------- |
| Scheduling algorithm       | FSRS (default since 23.10), `fsrs-rs` crate | **Keep.** Exposes per-card difficulty, stability, retrievability |
| Collection store           | SQLite (`collection.anki2`)                 | **Keep.** Portable, inspectable                                  |
| Sync protocol              | Documented; reimplementable                 | **Keep or extend** for bidirectional desktop↔phone               |
| Review UI                  | Qt (desktop) / native (mobile)              | **Extend**                                                       |
| Content authoring          | Decks, note types, tags                     | **Extend** — coverage mapped to the USMLE outline                |
| **Analytics / prediction** | **Essentially absent**                      | **This is the project.**                                         |

The prediction layer being empty in stock Anki is precisely where Speedrun adds value. By contrast, commercial tools (UWorld, AMBOSS) weld content, analytics, and UI together and expose no swappable scheduler and no data export — so they cannot be forked, and do not need to be.

---

## What already exists and does not need building

- **Per-card recall probability.** FSRS stores difficulty and stability per card and computes retrievability on demand. The Memory score's primitive is open source and free.
- **A calibration surface.** Anki's Stats screen displays true retention, which can be compared against the configured desired retention. That comparison is a memory-model calibration check already shipping in the tool being forked.
- **A cross-platform core.** AnkiDroid consumes `rslib` over JNI; `amgi` demonstrates the same core running on iOS through its C FFI.

## What does not exist and must be built

- **Any notion of item difficulty independent of the individual user.** Anki models the _learner_, not the _item_. There is no IRT-style population parameter — unlike AMBOSS's theta estimates or 7Sage's item curves with quartile bounds. A Performance score on novel exam-style questions needs both. This is a known cost, not a surprise.
- **Coverage against the official exam blueprint.** The market-leading deck is tagged by vendor resource, not by the USMLE content outline. Coverage must be built from the outline directly.
- **The bridge from memory state to novel-item performance.** No product observed conditions performance on novel items against that user's own card-level memory state. That is POV 3's structural claim and this system's reason to exist.
- **Abstention over _reporting a score_ — though not over _fitting a model_.** This entry has been wrong twice and the current version is the third attempt, so it is worth stating precisely. Anki's own `rslib` applies no review-count gate: [`compute_params`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L78) computes whatever it can and returns `fsrs_items` for the caller to judge, and the gate that once lived there was removed upstream ([PR #3106](https://github.com/ankitects/anki/pull/3106), [PR #3246](https://github.com/ankitects/anki/pull/3246)), leaving dead code behind. **But the gate did not disappear — it moved into the `fsrs` crate**, where [`training.rs:319`](https://github.com/open-spaced-repetition/fsrs-rs/blob/56a78d971e73c16d2e9a757edfdc3d9e1f0b3695/src/training.rs#L319) returns `DEFAULT_PARAMETERS` untouched below **8** training items, alongside L1 shrinkage toward defaults, Laplace smoothing, and parameter clamping. So refusal-below-a-floor _is_ upstream precedent, at 8 items rather than 200, and it governs whether to **fit a model** — never whether to **show a student a number**. That second decision has no precedent anywhere in the stack and is entirely ours to justify. Full ladder in `speedrun-docs/source-citations.md`, Finding G.

---

## Abstention vs shrinkage — resolved as neither

This section has been rewritten twice, and both earlier versions were wrong in the same way. The first said: refuse to report below a review threshold. The second said: shrink toward a prior where one is informative, abstain where it is not. **Both were answering "do I have enough data?" — a question that can only be settled by asserting a number.** The resolution is a third mechanism that asks a different question.

**Validation-gating.** Fit the model. Then test it against the thing you would otherwise have said. Report it only if it wins. No constant is asserted anywhere, and the test is the thing a threshold was only ever a proxy for.

This is upstream's own resolution, reached after they deleted their review-count gate ([PR #3106](https://github.com/ankitects/anki/pull/3106), [PR #3246](https://github.com/ankitects/anki/pull/3246)). Damien Elmes's proposal — "stop showing an error, and just fall back on the default parameters instead" — shipped as [`params.rs:156`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L156): fitted parameters are evaluated against the incumbent on the same items and discarded unless they win on log loss.

Shrinkage does not disappear; it stops being the gate and becomes an implementation detail of the _fallback_. Where the model loses, what you fall back to may still be a shrunk estimate rather than a raw prior — that is a modelling choice, not an honesty gate.

| Score           | Gate                                                                  | Validated against                                                         | Held-out unit                        | Layer           |
| --------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------ | --------------- |
| **Memory**      | Accept-only-if-better                                                 | The incumbent memory model (current FSRS parameters, or shipped defaults) | The student's own later reviews      | **Per-student** |
| **Performance** | Accept-only-if-better                                                 | The topic prior — what we would say knowing nothing about this student    | The student's own later scored items | **Per-student** |
| **Readiness**   | Accept-only-if-better **at model level**, plus per-student abstention | The base-rate null — a constant at the cohort pass rate (91% / 86% / 73%) | Held-out **students**                | **Model-level** |

**Why Readiness sits at a different layer.** Memory and Performance are validated inside a single student: their future reviews and items are a real held-out set, plentiful and continuously arriving. Readiness has no such set. **A student sits Step 1 once, the outcome is one bit, and it arrives after the app has stopped mattering to them.** You cannot hold out an individual's exam result and test against it in time to decide whether to show that individual a number. So validation moves up to the population — does the model beat a constant base-rate predictor across students whose outcomes are known? — and that licenses a claim about the _model_, never about _this student_. Abstention survives at the individual layer for exactly one reason: the validation that replaced it everywhere else cannot reach there.

**Two things this section is careful not to claim.** First, `n / (50 + n)` is borrowed as a _functional form_ from [fsrs-optimizer#116](https://github.com/open-spaced-repetition/fsrs-optimizer/issues/116), where it smooths **median review times** — not FSRS parameters. No upstream code shrinks FSRS parameters, and the Anki-side implementation of #116 (which shrank first-rating probabilities) was deleted in PR #3298; it is not present at commit `d735cd25`. Second, the constant 50 was tuned for review-time medians in a different estimator and carries no authority here — it is a starting value to be fitted, not a result to be cited. Both points are documented in `source-citations.md`.

**What this forces into the build, and it is more than the previous design demanded.** A gated score is uninterpretable without the evidence that it passed its gate, so the per-topic mastery query cannot return an estimate alone. **Every estimate must carry two companions: the `fsrs_items` count backing it, and the held-out log loss of the model against its comparator.** The first says how much evidence there is; the second says whether that evidence bought anything. A score without the count cannot be shrunk or interpreted; a score without the loss cannot be gated at all, because "better than the incumbent" is not a property of the estimate — it is a property of the comparison, and it has to be computed and carried, not recovered later.

Three consequences follow:

- **The query returns a triple, not a number.** `(estimate, n, held_out_log_loss_vs_comparator)` per topic. This is a wider protobuf message and a heavier query than a bare mastery figure, and it is the reason the change belongs in Rust rather than being assembled in Python per dashboard render.
- **The comparator must be materialized.** Accept-only-if-better needs the incumbent model kept and evaluable, not discarded on each refit. For Memory that is the student's previous FSRS parameters; for Performance, the topic prior. Both must be storable and scoreable on the same held-out set as the challenger.
- **Readiness needs a genuine refusal path through the UI**, distinct from "no data yet" and distinct from a low score. Refusing is a first-class output here, not an error state.

`n` is measured in **`fsrs_items`** — the count Anki computes and returns to callers — not graded reviews: a card's first review yields nothing, `delta_t > 0` excludes same-day repeats, and cram reviews are dropped before item construction, so a card with _k_ qualifying reviews yields up to _k_ − 1 items and the naive denominator overcounts.

**A second gate, separate from the first.** Accept-only-if-better is relative and a model can win it while remaining badly calibrated. Upstream pairs it with an absolute check at [`params.rs:182`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L182), evaluated with time-series splits against fixed bounds and gated at > 300 items. Speedrun needs the same pairing: a **skill gate** deciding whether to prefer the model, and a **sanity gate** deciding whether it is fit to display at all.

---

## Three scores, three pipelines

They share the collection and the FSRS memory state, and nothing else. Blending is what the honesty rule forbids.

```
           ┌─────────────────────────────┐
           │  Anki collection (SQLite)   │
           │  cards · notes · revlog     │
           └──────────────┬──────────────┘
                          │
           ┌──────────────▼──────────────┐
           │  rslib (Rust)               │
           │  FSRS · scheduler v3        │
           │  + per-topic mastery query  │  ← the Rust change
           └──────────────┬──────────────┘
                          │  protobuf
     ┌────────────────────┼────────────────────┐
     │                    │                    │
┌────▼─────┐        ┌─────▼──────┐      ┌──────▼──────┐
│ MEMORY   │        │PERFORMANCE │      │  READINESS  │
│ DOK 1    │        │ DOK 2–3    │      │  DOK 4      │
│ FSRS R   │        │ novel item │      │ P(pass)     │
│ + range  │        │ + range    │      │ + range     │
└──────────┘        └────────────┘      └─────────────┘
     │                    │                    │
     └────────────────────┴────────────────────┘
                          │
                ┌─────────▼──────────┐
                │  Give-up rule      │
                │  abstain if thin   │
                └────────────────────┘
```

---

## To be documented before final submission

- [ ] Desktop build, clean-machine verified
- [ ] Phone build and the shared-engine path
- [ ] Sync design and the conflict rule, written down
- [ ] Where AI runs, and how both apps score with AI switched off
- [ ] Benchmark harness (`make bench`) reporting p50, p95, and worst case
