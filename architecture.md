# Architecture overview

**Status: PENDING.** No code exists yet. What follows is the layer analysis the design rests on, which is complete, plus the shape of the intended system.

---

## The stack, decomposed

Comparison writing treats study tools as monolithic products. Anki's stack is not monolithic, and the seams matter:

| Layer | Stock Anki | Speedrun's relationship to it |
|---|---|---|
| Scheduling algorithm | FSRS (default since 23.10), `fsrs-rs` crate | **Keep.** Exposes per-card difficulty, stability, retrievability |
| Collection store | SQLite (`collection.anki2`) | **Keep.** Portable, inspectable |
| Sync protocol | Documented; reimplementable | **Keep or extend** for bidirectional desktop↔phone |
| Review UI | Qt (desktop) / native (mobile) | **Extend** |
| Content authoring | Decks, note types, tags | **Extend** — coverage mapped to the USMLE outline |
| **Analytics / prediction** | **Essentially absent** | **This is the project.** |

The prediction layer being empty in stock Anki is precisely where Speedrun adds value. By contrast, commercial tools (UWorld, AMBOSS) weld content, analytics, and UI together and expose no swappable scheduler and no data export — so they cannot be forked, and do not need to be.

---

## What already exists and does not need building

- **Per-card recall probability.** FSRS stores difficulty and stability per card and computes retrievability on demand. The Memory score's primitive is open source and free.
- **A calibration surface.** Anki's Stats screen displays true retention, which can be compared against the configured desired retention. That comparison is a memory-model calibration check already shipping in the tool being forked.
- **A cross-platform core.** AnkiDroid consumes `rslib` over JNI; `amgi` demonstrates the same core running on iOS through its C FFI.

## What does not exist and must be built

- **Any notion of item difficulty independent of the individual user.** Anki models the *learner*, not the *item*. There is no IRT-style population parameter — unlike AMBOSS's theta estimates or 7Sage's item curves with quartile bounds. A Performance score on novel exam-style questions needs both. This is a known cost, not a surprise.
- **Coverage against the official exam blueprint.** The market-leading deck is tagged by vendor resource, not by the USMLE content outline. Coverage must be built from the outline directly.
- **The bridge from memory state to novel-item performance.** No product observed conditions performance on novel items against that user's own card-level memory state. That is POV 3's structural claim and this system's reason to exist.
- **Abstention over *reporting a score* — though not over *fitting a model*.** This entry has been wrong twice and the current version is the third attempt, so it is worth stating precisely. Anki's own `rslib` applies no review-count gate: [`compute_params`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L78) computes whatever it can and returns `fsrs_items` for the caller to judge, and the gate that once lived there was removed upstream ([PR #3106](https://github.com/ankitects/anki/pull/3106), [PR #3246](https://github.com/ankitects/anki/pull/3246)), leaving dead code behind. **But the gate did not disappear — it moved into the `fsrs` crate**, where [`training.rs:319`](https://github.com/open-spaced-repetition/fsrs-rs/blob/56a78d971e73c16d2e9a757edfdc3d9e1f0b3695/src/training.rs#L319) returns `DEFAULT_PARAMETERS` untouched below **8** training items, alongside L1 shrinkage toward defaults, Laplace smoothing, and parameter clamping. So refusal-below-a-floor *is* upstream precedent, at 8 items rather than 200, and it governs whether to **fit a model** — never whether to **show a student a number**. That second decision has no precedent anywhere in the stack and is entirely ours to justify. Full ladder in `speedrun-docs/source-citations.md`, Finding G.

---

## Abstention vs shrinkage

The first version of this design applied one rule to all three scores: refuse to report below a review threshold. That was wrong, and the reason it was wrong is architectural rather than cosmetic — **the right mechanism for thin data depends on whether an informative prior exists, and the three scores do not have the same answer.**

Refusing and shrinking are both responses to "I do not have enough data to say." They differ in what they do with the prior:

- **Abstention** discards the estimate entirely. It is correct when any prior you could fall back on would itself mislead.
- **Shrinkage** reports `w · x̂_user + (1 − w) · x̂_prior`, with `w` rising as data accumulates. It is correct when the prior encodes real information the user's own data has not yet earned.

Upstream reached the same conclusion by a different route. Anki once gated FSRS optimization on a review count and removed enforcement in two steps ([PR #3106](https://github.com/ankitects/anki/pull/3106), [PR #3246](https://github.com/ankitects/anki/pull/3246)), leaving the error variant and its string as dead code. The replacement reasoning is Damien Elmes's: "stop showing an error, and just fall back on the default parameters instead."

| Score | Prior available | Informative? | Mechanism |
|---|---|---|---|
| **Memory** | FSRS default parameters, fitted across ~20k collections | **Yes** — upstream's benchmark has fitting beating defaults only from ~16 items, so defaults are a strong fallback below that | Shrinkage, weight `n / (50 + n)` |
| **Performance** | Topic-level performance across other students | **Partly** — informative, but no validated population model underneath it | Shrinkage, plus a floor where the prior is itself unmeasured |
| **Readiness** | First-attempt pass rate: 91% US MD, 86% US DO, 73% IMG | **No — degenerate** | **Abstention** |

**Why Readiness is the exception.** Its only population prior is the pass rate, which is a near-constant clustered high. Shrinking toward it means every data-poor student is told they will pass at roughly the base rate — a constant function wearing a probability's clothing, and the exact degenerate classifier that `BRAINLIFT.md` §1 forbids by banning accuracy as a metric. A prior that already encodes the answer is not a prior. Abstention is the only honest mechanism there, and it is the one place in this system where refusing to answer is a feature rather than a fallback.

**Two things this section is careful not to claim.** First, `n / (50 + n)` is borrowed as a *functional form* from [fsrs-optimizer#116](https://github.com/open-spaced-repetition/fsrs-optimizer/issues/116), where it smooths **median review times** — not FSRS parameters. No upstream code shrinks FSRS parameters, and the Anki-side implementation of #116 (which shrank first-rating probabilities) was deleted in PR #3298; it is not present at commit `d735cd25`. Second, the constant 50 was tuned for review-time medians in a different estimator and carries no authority here — it is a starting value to be fitted, not a result to be cited. Both points are documented in `source-citations.md`.

**What this forces into the build.** The give-up rule is no longer one predicate. Memory and Performance need a shrinkage estimator with the prior as a first-class input, which means the per-topic mastery query has to return the *count* backing each estimate alongside the estimate itself — a shrunk score is uninterpretable without its `n`. Readiness needs a genuine refusal path through the UI. And `n` is measured in **`fsrs_items`** — the count Anki computes and returns to callers — not graded reviews: a card's first review yields nothing, `delta_t > 0` excludes same-day repeats, and cram reviews are dropped before item construction, so a card with *k* qualifying reviews yields up to *k* − 1 items and the naive denominator overcounts.

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
