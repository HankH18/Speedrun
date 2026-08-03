# Speedrun

## Exam: USMLE Step 1

A desktop and mobile study app built on a fork of **[Anki](https://github.com/ankitects/anki)**, targeting **USMLE Step 1** — pass/fail since 26 January 2022, minimum passing standard 196.

> ### Built on Anki
>
> Speedrun is a fork of **[Anki](https://github.com/ankitects/anki)**, created by **Damien Elmes** and the Anki contributors. Anki is licensed **AGPL-3.0-or-later**, with portions contributed by Anki users under **BSD-3-Clause**; this fork is public and remains under AGPL-3.0-or-later. Everything that makes the scheduler work — `rslib`, the protobuf bridge, FSRS integration, the collection format — is their work, not ours. Speedrun adds an analytics and prediction layer on top of it.
>
> Scheduling is provided by **FSRS** (Free Spaced Repetition Scheduler), created by **Jarrett Ye** and the [Open Spaced Repetition](https://github.com/open-spaced-repetition) community, building on the two-component model of memory developed by **Piotr Woźniak** in SuperMemo.
>
> Full licence text and attribution: [`LICENSE`](LICENSE) and [Credits and licence](#credits-and-licence) below.

Speedrun reports **three separately-derived scores**, each with an explicit range, each refusing to report when the data underneath it is insufficient:

| Score           | Question it answers                                             | DOK level |
| --------------- | --------------------------------------------------------------- | --------- |
| **Memory**      | Can you recall this fact right now?                             | 1         |
| **Performance** | Can you answer a novel exam-style question that uses it?        | 2–3       |
| **Readiness**   | What is your probability of passing today, and how sure are we? | 4         |

They are never blended into one number.

---

## Status

**Early submission.** The research layer is complete; the build has not started.

- ✅ [`BRAINLIFT.md`](BRAINLIFT.md) — DOK ladder, three Spiky POVs with falsifiers, traceability table
- ✅ [`speedrun-docs/teardown-observation-log.md`](speedrun-docs/teardown-observation-log.md) — competitive teardown, hands-on
- ✅ [`speedrun-docs/source-citations.md`](speedrun-docs/source-citations.md) — every source-code claim resolved against a pinned upstream commit, including the ones that turned out to be wrong
- ⬜ Rust change — see [`speedrun-docs/rust-change-note.md`](speedrun-docs/rust-change-note.md)
- ⬜ Architecture — see [`speedrun-docs/architecture.md`](speedrun-docs/architecture.md)
- ⬜ AI consensus check transcripts — harness designed, not run
- ⬜ Calibration and ablation — `BRAINLIFT.md` Appendices A and B

`BRAINLIFT.md` §0 carries a full status disclosure, and [`speedrun-docs/KNOWN-DEFECTS.md`](speedrun-docs/KNOWN-DEFECTS.md) lists the defects we found in our own work — third-party deck text left in history, no clean-machine install recording, the unbuilt phone companion, and eight calibration thresholds still UNKNOWN. Nothing in this repo is presented as more finished than it is.

**Repository layout.** The root of this repository _is_ the Anki fork — upstream's tree, with full history. Speedrun's own writing lives in [`speedrun-docs/`](speedrun-docs/) and `BRAINLIFT.md`, kept deliberately separate from upstream's `docs/` so that `git diff upstream/main` shows exactly what this fork adds and nothing else.

---

## Why pass/fail matters, and the trap it creates

Every alternative exam (MCAT, LSAT, GMAT Focus) requires inventing a mapping from question performance to a scaled score that cannot be validated against ground truth in one week. Step 1's binary outcome makes readiness a **classifier**, where Brier score, log loss, and reliability curves fall out natively.

The cost: 2024 first-attempt pass rates were 91% (US MD), 86% (US DO), 73% (IMG). **A classifier that always outputs "pass" scores ~91% accuracy while being a constant function.** Accuracy is therefore a forbidden metric in this project. Calibration is reported via Brier score and log loss against the base-rate null, stratified by predicted-probability band.

---

## The give-up rule

The app refuses to report a score when the data underneath it cannot support one. The rule is **not** a single threshold — it differs per score, because the three scores have different priors available to them and different things to validate against.

**See [`BRAINLIFT.md` §7](BRAINLIFT.md) for the current rule, its reasoning, and its provenance.** It is stated in exactly one place deliberately: an earlier version of this README restated the rule independently, and when the rule changed the two drifted out of sync — which is the failure the traceability table exists to prevent.

---

## Setup

### Build

⬜ **Pending.** Build instructions for the desktop app and the phone companion land with the first Speedrun change. Upstream Anki's own build documentation applies in the meantime — see [`docs/`](docs/).

Planned:

- **Desktop** — Rust core (`rslib`), protobuf bridge, Qt frontend, as upstream
- **Android** — built on AnkiDroid's JNI bridge to the shared `rslib` core
- **iOS** — Rust backend through its C interface, following the approach demonstrated by [amgi](https://github.com/antigluten/amgi)

The scheduler is not reimplemented in JavaScript or Swift. Both platforms run the same Rust engine.

---

## Architecture overview

⬜ **Pending** — see [`speedrun-docs/architecture.md`](speedrun-docs/architecture.md).

Summary of intent: Anki's stack decomposes into scheduler (FSRS), collection store (SQLite), sync protocol, review UI, and an **analytics/prediction layer that is essentially absent in stock Anki**. That absent layer is where Speedrun lives. FSRS already exposes per-card difficulty, stability, and retrievability — the Memory score's primitive exists, open source, and does not need inventing.

---

## The Rust change

⬜ **Pending** — see [`speedrun-docs/rust-change-note.md`](speedrun-docs/rust-change-note.md).

Provisionally scoped to a **per-topic mastery query** returning mastery and average recall fast enough to drive the dashboard on a 50,000-card collection. All three scores plus the coverage map depend on per-topic aggregation, and dashboard-latency targets are a genuine reason for it to live in Rust rather than Python.

### Upstream files touched

⬜ **Pending** — populated when the first change lands. `git diff upstream/main --stat` is the authoritative answer at any commit.

---

## Credits and licence

Speedrun is a fork of **Anki**, created by **Damien Elmes** and the Anki contributors — see [ankitects/anki](https://github.com/ankitects/anki) and [`CONTRIBUTORS`](CONTRIBUTORS).

Anki is licensed **AGPL-3.0-or-later**, with portions contributed by Anki users under **BSD-3-Clause**. This fork is public and remains under **AGPL-3.0-or-later**. Where BSD-3-Clause components are reused, the original copyright notice and disclaimer are preserved. The canonical licence text is upstream's [`LICENSE`](LICENSE), carried into this fork unmodified.

Scheduling is provided by **FSRS** (Free Spaced Repetition Scheduler), created by **Jarrett Ye** and the [Open Spaced Repetition](https://github.com/open-spaced-repetition) community, which builds on the two-component model of memory developed by **Piotr Woźniak** in SuperMemo.

    Copyright (C) 2026 Hank Holcomb

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
