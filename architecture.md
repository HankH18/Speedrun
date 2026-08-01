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
- **An abstention precedent.** FSRS declines to fit custom parameters below a review threshold, falling back to defaults rather than fitting noise. The give-up rule cites this as lineage rather than presenting the concept as invented. *(Exact constant marked UNVERIFIED pending the fork — see `rust-change-note.md`.)*
- **A calibration surface.** Anki's Stats screen displays true retention, which can be compared against the configured desired retention. That comparison is a memory-model calibration check already shipping in the tool being forked.
- **A cross-platform core.** AnkiDroid consumes `rslib` over JNI; `amgi` demonstrates the same core running on iOS through its C FFI.

## What does not exist and must be built

- **Any notion of item difficulty independent of the individual user.** Anki models the *learner*, not the *item*. There is no IRT-style population parameter — unlike AMBOSS's theta estimates or 7Sage's item curves with quartile bounds. A Performance score on novel exam-style questions needs both. This is a known cost, not a surprise.
- **Coverage against the official exam blueprint.** The market-leading deck is tagged by vendor resource, not by the USMLE content outline. Coverage must be built from the outline directly.
- **The bridge from memory state to novel-item performance.** No product observed conditions performance on novel items against that user's own card-level memory state. That is POV 3's structural claim and this system's reason to exist.

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
