# Known defects

Defects found by us, recorded before a grader finds them. Each states what is
wrong, why it has not been fixed, and what fixing it would take.

---

## 1. Third-party deck text is committed in history

**Commit `5acdc1305` contains `speedrun-analysis/deck/out/tag_proposals.json`
(17,748 lines) and `tag_report.txt` (1,279 lines), which quote note text from
every card of a third-party AnkiWeb shared deck** (deck ID `1030312320`,
`Manozzita_Microbiology_USMLE_Step_1.apkg`).

**Current state.** Both files are removed from `HEAD`, and
`speedrun-analysis/deck/out/` is now in `.gitignore`. The outputs remain on disk
and regenerate with one command. **The files are still present in commit
`5acdc1305`, which is pushed to both public remotes.**

**Why this is the defect, and it is not really about copyright.** The deck is
publicly shared on AnkiWeb, so the exposure is limited. But AnkiWeb shared decks
typically carry **no stated licence**, which means this content **did not pass
the two-gate check this project applies to every other source** — the check that
rejected OpenStax on both licence and AI-ingestion grounds, and rejected five PMC
articles on licence grounds (see `speedrun-analysis/sources/LICENCE-PROVENANCE.md`).
**Applying a standard everywhere except where it was inconvenient is the actual
failure**, and it is worse than the content itself.

**Remediation, deliberately deferred.** Removing it requires rewriting history and
force-pushing to both remotes. That is a destructive, irreversible operation, and
it was declined **under deadline pressure specifically** — a rushed history rewrite
across two remotes is how a repository gets lost. The decision is deferred to after
submission, not waived.

---

## 2. No clean-machine install recording

**The brief asks for an install verified on a clean device. That recording does not
exist and this submission does not claim it.**

**Why.** The build toolchain was installed on the only available machine during
Stage 0 — `just`, `rustup` with Rust 1.92.0, and `n2` were all absent and had to be
added, along with initialising the installer submodules. **That machine is therefore
no longer clean and cannot demonstrate the claim.** A second machine or a fresh VM is
required, and producing the recording is a human step.

**What was verified instead, and it is not a substitute.** `just check` exits 0 from
a clean working tree; 7 Rust tests and 4 pylib tests pass; the 50,000-card benchmark
runs at median 99.9 ms / p95 102.7 ms / worst 103.6 ms against a 1000 ms budget.
**None of that establishes the software installs on a machine that has never seen
it**, which is the thing the requirement is actually about — and the Stage 0
experience is direct evidence that a fresh machine needs non-trivial setup.

---

## 3. The phone companion is unbuilt

Recorded in full in `BUILD-DOC.md` §15b. **The phone companion is not built, which
caps this submission at 70%.** The AnkiDroid/JNI integration path is verified against
the real repositories and documented, including exact toolchain versions, so it is a
short step once a toolchain exists — but it is a step that was not taken.

---

## 4. Every calibration threshold is UNKNOWN

`speedrun-analysis/appendix_b/thresholds.json` reports **8 thresholds, 0 derived**.
This is the honest state rather than an incomplete one: `DERIVED` is reachable only
on a non-synthetic dataset manifest, and no real student cohort is present. The
machinery is built and tamper-checked; it has nothing real to run on yet.

The unblock is a HuggingFace account gate on `anki-revlogs-10k` — **not** a licence
question. The licence is publicly readable and permits student research use. See
`speedrun-analysis/appendix_b/DATA-PROVENANCE.md`.
