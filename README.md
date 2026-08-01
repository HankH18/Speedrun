# Speedrun

## Exam: USMLE Step 1

A desktop and mobile study app built on a fork of [Anki](https://apps.ankiweb.net/), targeting **USMLE Step 1** — pass/fail since 26 January 2022, minimum passing standard 196.

Speedrun reports **three separately-derived scores**, each with an explicit range, each refusing to report when the data underneath it is insufficient:

| Score | Question it answers | DOK level |
|---|---|---|
| **Memory** | Can you recall this fact right now? | 1 |
| **Performance** | Can you answer a novel exam-style question that uses it? | 2–3 |
| **Readiness** | What is your probability of passing today, and how sure are we? | 4 |

They are never blended into one number.

---

## Status

**Early submission.** The research layer is complete; the build has not started.

- ✅ [`BRAINLIFT.md`](BRAINLIFT.md) — DOK ladder, three Spiky POVs with falsifiers, traceability table
- ✅ [`docs/teardown-observation-log.md`](docs/teardown-observation-log.md) — competitive teardown, hands-on
- ⬜ Anki fork and Rust change — see [`docs/rust-change-note.md`](docs/rust-change-note.md)
- ⬜ Architecture — see [`docs/architecture.md`](docs/architecture.md)
- ⬜ AI consensus check transcripts — harness designed, not run
- ⬜ Calibration, ablation, and evidence layer — Sunday deliverable

`BRAINLIFT.md` §0 carries a full status disclosure. Nothing in this repo is presented as more finished than it is.

---

## Why pass/fail matters, and the trap it creates

Every alternative exam (MCAT, LSAT, GMAT Focus) requires inventing a mapping from question performance to a scaled score that cannot be validated against ground truth in one week. Step 1's binary outcome makes readiness a **classifier**, where Brier score, log loss, and reliability curves fall out natively.

The cost: 2024 first-attempt pass rates were 91% (US MD), 86% (US DO), 73% (IMG). **A classifier that always outputs "pass" scores ~91% accuracy while being a constant function.** Accuracy is therefore a forbidden metric in this project. Calibration is reported via Brier score and log loss, stratified by predicted-probability band.

---

## The give-up rule

The app refuses to report a score when:

- **Memory** — fewer than 200 graded reviews
- **Performance** — fewer than 50 scored novel items
- **Readiness** — both of the above, **and** ≥50% coverage of the official USMLE content outline
- **Any score** — if a session's median response latency falls below 20% of the item's target time, that session is flagged and excluded from scoring inputs

The latency clause exists because that exact adversarial probe was run against three commercial tools during the teardown and all three responded with a number. See `docs/teardown-observation-log.md`.

---

## Setup

### License file

The canonical AGPL-3.0 text is fetched rather than vendored, so it is byte-exact:

```bash
./scripts/fetch-license.sh
```

### Build

⬜ **Pending.** Build instructions for the desktop app and the phone companion land with the fork.

Planned:
- **Desktop** — fork of [ankitects/anki](https://github.com/ankitects/anki); Rust core (`rslib`), protobuf bridge, Qt frontend
- **Android** — built on AnkiDroid's JNI bridge to the shared `rslib` core
- **iOS** — Rust backend through its C interface, following the approach demonstrated by [amgi](https://github.com/antigluten/amgi)

The scheduler is not reimplemented in JavaScript or Swift. Both platforms run the same Rust engine.

---

## Architecture overview

⬜ **Pending** — see [`docs/architecture.md`](docs/architecture.md).

Summary of intent: Anki's stack decomposes into scheduler (FSRS), collection store (SQLite), sync protocol, review UI, and an **analytics/prediction layer that is essentially absent in stock Anki**. That absent layer is where Speedrun lives. FSRS already exposes per-card difficulty, stability, and retrievability — the Memory score's primitive exists, open source, and does not need inventing.

---

## The Rust change

⬜ **Pending** — see [`docs/rust-change-note.md`](docs/rust-change-note.md).

Provisionally scoped to a **per-topic mastery query** returning mastery and average recall fast enough to drive the dashboard on a 50,000-card collection. All three scores plus the coverage map depend on per-topic aggregation, and dashboard-latency targets are a genuine reason for it to live in Rust rather than Python.

## Upstream files touched

⬜ **Pending** — populated when the fork exists.

---

## Credits and license

Speedrun is a fork of **Anki**, created by **Damien Elmes** and the Anki contributors.

Anki is licensed **AGPL-3.0-or-later**, with portions contributed by Anki users under **BSD-3-Clause**. This fork is public and remains under **AGPL-3.0-or-later**. Where BSD-3-Clause components are reused, the original copyright notice and disclaimer are preserved.

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
