# Appendix B — calibration core

**The machinery is real. The cohort is not.** This directory implements the
measurement, calibration and gating layer specified in
[`BRAINLIFT.md` Appendix B](../../BRAINLIFT.md), and runs it end to end on a
**synthetic cohort it generates deterministically**, because Speedrun has no
real student data yet.

```
python3 speedrun-analysis/appendix_b/run.py              # the report
python3 speedrun-analysis/appendix_b/test_appendix_b.py  # the tests
python3 speedrun-analysis/appendix_b/derive_thresholds.py             # writes thresholds.json
python3 speedrun-analysis/appendix_b/derive_thresholds.py --self-test # the derivations' tamper-check
```

Pure Python 3, standard library only. No dependencies, no virtualenv, no
`pip install`. Both commands exit non-zero on failure. `run.py` takes about 11
seconds and is bit-for-bit reproducible under seed `20260802`.

---

## No number in this directory is a result

Every figure `run.py` prints describes 1,200 imaginary students produced by a
generating process written by hand in `run.py` itself. Where the readiness model
beats the base-rate null, it does so because the signal was put into the data
forty lines above. **No threshold derived here is final** — not the `fsrs_items`
floor, not the coverage floor, not the latency cut, not the shrinkage constant.
`BRAINLIFT.md` §7 stays at TBD until this same code runs against real reviews.

That is the whole reason the synthetic cohort exists: the alternative was a
specification nobody could run, and a stub that looks like a deliverable is
worse than an absent one.

---

## Accuracy is not implemented, and that is enforced

`BRAINLIFT.md` §1 forbids accuracy: at a 91% first-attempt pass rate a constant
"pass" predictor scores ~91% while being a constant function. So `metrics.py`
has no `accuracy`, no `hit_rate`, no `percent_correct`, and
`test_metrics_module_defines_no_accuracy_function` scans the module namespace to
make sure none reappears — plus a second test asserting the written explanation
is still there, so the ban does not decay into folklore.

Everything is **Brier score and log loss against a named comparator**, plus a
reliability curve stratified by predicted-probability band. The bar to beat is
printed in the report: at a 91% base rate the constant predictor scores Brier
**0.0819** and log loss **0.3025** (its binary entropy).

---

## The files

| File                   | What it holds                                                                                                                                        |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `metrics.py`           | Brier, log loss, reliability binning, the base-rate null, skill scores, Murphy decomposition. Every function documents what it does **not** license. |
| `calibration.py`       | Platt scaling and isotonic regression (pool-adjacent-violators), the three-way split with mechanical disjointness enforcement, and shrinkage.        |
| `gates.py`             | Accept-only-if-better at **three layers**, the absolute sanity gate, and the floor / abstention-vs-shrinkage / latency sweeps.                       |
| `run.py`               | One command. Generates the cohort, runs everything, prints the report.                                                                               |
| `test_appendix_b.py`   | 39 tests against hand-computed values, closed forms and structural guarantees.                                                                       |
| `derive_thresholds.py` | One derivation procedure per numeric floor §7 owes, plus the tamper-check that each procedure can recover a crossover planted in synthetic data.     |
| `thresholds.json`      | The machine-readable answer: per threshold, a value or `null`, a status, the script and function that produced it, and the dataset it was read off.  |

---

## Thresholds are outputs, never inputs

This is the standing rule of the whole appendix, and it is the reason
`derive_thresholds.py` exists as a separate entry point.

`BRAINLIFT.md` §8 records the defect it prevents: two numbers were taken from
the assignment brief's illustrative sentence — _"no score below 200 graded
reviews and 50% topic coverage"_ — asserted in §7, and then sent looking for
authority afterwards. **A threshold that constrains the analysis cannot also be
validated by it.** That ordering is circular, and it is the same circularity §4.2
criticises AMBOSS for.

So no procedure in `derive_thresholds.py` reads a threshold from anywhere. The
retired figures appear in exactly one place — each threshold's
`retired_starting_value` field, with its provenance beside it — so that a reader
can see what was **not** used:

| Threshold                       | Retired figure | Where it came from                                                                    |
| ------------------------------- | -------------- | ------------------------------------------------------------------------------------- |
| `memory_fsrs_items_floor`       | 200            | the brief's example, then a claimed FSRS precedent that was not in the codebase cited |
| `performance_scored_item_floor` | 50             | provenance **UNKNOWN**; not the brief, and not reconstructible                        |
| `readiness_coverage_floor`      | 0.50           | the brief's example, verbatim                                                         |
| `sanity_gate_min_items`         | 300            | Anki `params.rs:182` — real code, different estimator                                 |
| `sanity_gate_log_loss_bound`    | 1.11           | Anki `params.rs:182` — same                                                           |
| `sanity_gate_brier_bound`       | 1.53           | Anki `params.rs:182`, and on a different scale again (adjusted RMSE, not Brier)       |
| `latency_fraction`              | 0.20           | teardown observation, explicitly logged as a starting value                           |
| `shrinkage_constant`            | 50             | fsrs-optimizer #116, where it smooths **median review times** in another estimator    |

**`thresholds.json` currently reports eight thresholds, all `UNKNOWN`, all with
`value: null`.** That is the correct state of the world, not a gap in the code:
there is no real cohort to read them off. Each record carries a `needs` field
naming the data that would let it run.

### What DERIVED means, and why nothing is

A threshold is marked `DERIVED` only when its procedure ran to completion, on a
dataset whose manifest says `"synthetic": false`, with enough held-out units in
every bin it needed, **and** the crossover it searches for actually exists in
that data. Anything else is `UNKNOWN` with a stated reason.

**On synthetic data nothing is ever marked `DERIVED`.** A synthetic run reports
its number under `dry_run.value_not_a_threshold` with the top-level `value` left
null, so a figure produced by a data-generating process this project wrote
cannot be mistaken for one read off students. That invariant is enforced in
`Derivation.to_json`, not merely intended, and `--self-test` asserts it.

---

## The seven things Appendix B owes

`BRAINLIFT.md`'s Appendix B stub lists seven obligations, and says that until
they exist no threshold in §7 has support. Where they stand:

| # | Owed                                                                       | Status                                                                                                                                    |
| - | -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Reliability curves, Brier + log loss vs the base-rate null, never accuracy | **Implemented**, `metrics.py` + `run.py`. Awaits real data for a real curve.                                                              |
| 2 | Accept-only-if-better gate for Memory and Performance, shown to run        | **Implemented**, `gates.py` + `run.py`.                                                                                                   |
| 3 | Readiness model-level test on held-out students                            | **Implemented**, `gates.readiness_model_gate`. POV 2's falsifier (4) can only actually fire on real outcomes.                             |
| 4 | Abstention-vs-shrinkage comparison on the overlap                          | **Implemented**, `gates.abstention_vs_shrinkage`. Also accounted for per-threshold in `thresholds.json` under `evidence.abstention_cost`. |
| 5 | Derived floors — `fsrs_items`, scored items, coverage, sanity-gate bounds  | **Procedures implemented** in `derive_thresholds.py`; **all four return `UNKNOWN`**. Not discharged as numbers.                           |
| 6 | The latency fraction, fitted rather than taken from the teardown           | **Procedure implemented**, `derive_latency_fraction`; returns `UNKNOWN`. Not discharged.                                                  |
| 7 | The fitted shrinkage constant, replacing the borrowed 50                   | **Procedure implemented**, `derive_shrinkage_constant`; returns `UNKNOWN`. Not discharged.                                                |

Items 5–7 are the numeric ones and they are the reason `thresholds.json` exists.
**A procedure being implemented and tested is not the same as an obligation
being discharged**, and this table keeps the two apart on purpose.

---

## How each floor is actually located

Every procedure is a search for a crossover in held-out data. None returns a
constant, and each returns `UNKNOWN` — with a reason — when the crossover is not
in the data it was given.

| Threshold                       | The question it asks                                                                                                                                      |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `memory_fsrs_items_floor`       | Binned by `fsrs_items`: at what count does the personal model stop losing, on the student's own held-out reviews, to the incumbent it would fall back to? |
| `performance_scored_item_floor` | The same shape, comparator changed to the topic prior — the impersonal answer.                                                                            |
| `readiness_coverage_floor`      | Sweeping coverage: where does the readiness model start beating the base-rate null on held-out **students**?                                              |
| `sanity_gate_min_items`         | Split-half: at what count is the **absolute** log-loss estimate precise enough, relative to the bound, to be worth acting on?                             |
| `sanity_gate_log_loss_bound`    | The base-rate null's own held-out log loss. A model worse than knowing nothing is not fit to show, whatever it beat on the way in.                        |
| `sanity_gate_brier_bound`       | The same, in Brier, reported beside the log-loss decision and never overturning it.                                                                       |
| `latency_fraction`              | Stratified by latency ratio: below which stratum do outcomes stop tracking the model's forecast at all?                                                   |
| `shrinkage_constant`            | Grid-fit `k` in `w = n/(k+n)` on a fitting split, scored on a **disjoint** evaluation split, with the borrowed 50's loss printed beside it.               |

Two of these searches were rewritten after the tamper-check caught them
returning confidently wrong answers, and both failures are worth recording
because both are the same mistake:

- **The latency cut was first tested on cumulative pools** — "is everything
  below _f_ uninformative?" — and overshot the planted cut by 68%, because a
  pool below _f_ mixes noise sessions with real ones and stays indistinguishable
  from noise by **dilution** long past the true boundary. A filter derived that
  way discards real student data. It now tests **marginal strata**.
- **The coverage floor had the same flaw** and landed a grid step low: the
  cumulative population above the floor beat the null on average while the band
  _at_ the floor was actively worse than a constant predictor. The floor now
  requires **both** the cumulative population and the marginal band to win —
  because the band at the boundary is exactly where every student the gate newly
  admits sits, and an average that carries them is licensing harm.

A third was rewritten for being unanswerable rather than wrong:
`sanity_gate_min_items` first measured split-half **decision agreement**, which
never converges — a model sitting genuinely on the bound flips at any sample
size — so the floor came back `UNKNOWN` for a reason that was about the bound's
neighbourhood, not about sample size. It now measures the **precision of the
estimate**, which is what upstream's stated rationale for `> 300` actually
describes.

### The tamper-check

`--self-test` builds a deterministic synthetic fixture with known crossovers
planted in it — a memory floor at 32, a performance floor at 64, a coverage floor
at 0.40, a latency cut at 0.25, a shrinkage constant of 12 — and asks each search
to find them. It runs 12 checks in about 8 seconds and exits non-zero on any
failure.

**Those recoveries say the searches work. They say nothing about students.** The
planted values are properties of a data-generating process written in this file;
they are not thresholds, no threshold may be read off them, and the run they come
from reports `DERIVED=0` like every other synthetic run. Two of the checks exist
specifically to hold that line: one asserts the synthetic run marks nothing
`DERIVED`, and one asserts that a manifest with no data blocks in it produces no
numbers at all.

### Feeding the derived bounds back into the gate

`gates.sanity_gate` requires a `bound_provenance` argument precisely so that no
bound can be used without recording where it came from. Once real data exists,
`thresholds.json` is what fills it:

```python
gates.sanity_gate(
    probs, outcomes,
    min_items=<sanity_gate_min_items.value>,
    log_loss_bound=<sanity_gate_log_loss_bound.value>,
    bound_provenance="derived: derive_thresholds.py::derive_sanity_gate_log_loss_bound",
)
```

Until then the honest provenance string is the borrowed one, and `run.py` says
so in its output.

### Where the two implementations overlap

`gates.py` carries its own sweeps (`sweep_items_floor`, `sweep_coverage_floor`,
`fit_latency_cut`) used by `run.py`'s end-to-end report, and
`derive_thresholds.py` implements the same three searches independently against
a stricter criterion — a bootstrap interval that must exclude zero, and a floor
that must hold at itself **and every non-empty bin above it**. This duplication
is deliberate and is stated rather than tidied away: the two answer slightly
different questions (one policy-level, one floor-level), and **where they
disagree on the same data, the disagreement is a finding to report, not a bug to
reconcile by deleting one of them.**

`derive_thresholds.py` binds `metrics.py` at import, probe-validating each
function against a closed form before use, so a signature change surfaces as a
refusal to bind rather than as a wrong number. It does **not** reach into
`gates._beats_on_log_loss`, which that module keeps private on purpose; it
applies the identical strict-log-loss rule locally and records that it did.
`calibration.py` is declared but not consumed: the coverage floor and the
shrinkage constant must be **re-derived on post-hoc-calibrated probabilities**
once its entry point is fixed, and both carry a `pending_integration` field
saying so.

---

## The three gates do not collapse into one function

`BRAINLIFT.md` §7 says collapsing its gate table is the error the table exists
to prevent. The mechanism is identical in all three cases — fit freely, then
discard the fit unless it beats the incumbent on log loss, exactly as upstream
does at `rslib/src/scheduler/fsrs/params.rs:156`. What differs is **what the
model is validated against** and **at which layer**:

| Score           | Layer                    | Comparator                            | Held-out unit                    |
| --------------- | ------------------------ | ------------------------------------- | -------------------------------- |
| **Memory**      | per-student              | incumbent memory model                | that student's own later reviews |
| **Performance** | per-student              | topic prior                           | that student's own later items   |
| **Readiness**   | **model-level**          | base-rate null                        | **held-out students**            |
|                 | + per-student abstention | coverage floor + both component gates | —                                |

So `memory_gate` and `performance_gate` take one student's held-out outcomes,
`readiness_gate` takes a cohort **plus** that student's coverage and component
decisions, and **Readiness returns a different type** (`ReadinessDecision`, not
`GateResult`). A model-level result has no `student_id` and cannot be used as if
it did. `test_the_three_gates_do_not_collapse_into_one` and
`test_readiness_abstains_per_student_even_when_the_model_passes` assert this
structurally and behaviourally.

---

## Things this run got wrong, kept in the output

The report prints several results that are inconvenient, because deleting them
would make the harness a demo rather than a test:

- **Both calibrators made the readiness forecast worse** out of sample (raw
  0.25807, Platt 0.27135, isotonic 0.26970 in nats). A logistic fitted by
  minimising log loss is already close to calibrated, so a second monotone
  rescaling on 300 students mostly adds noise. The gate still scores the
  **pre-committed** Platt forecast, because picking the best of three on the
  evaluation set is selection on the evaluation set.
- **The derived `fsrs_items` floor is 0.** The accept-only-if-better gate is
  already doing the refusing, and no additional floor improved held-out log
  loss. That is a legitimate outcome and the opposite of the retracted 200.
- **Neither abstention nor shrinkage won outright.** Shrinkage wins the overlap
  at the lowest floor and loses it at higher ones, so POV 2's falsifier (3)
  neither fires nor clears.
- **The latency filter's catch costs real data**: at the fitted cut it removes
  1,479 of 1,523 contaminated sessions and 834 genuine ones, because the two
  latency populations overlap by construction.

There is also a **required control**: the whole readiness pipeline is refitted
on features permuted against the outcomes, and the model-level gate must
withhold. If it reported, the harness would be rigged and every number above it
void.

---

## Known gaps, stated rather than hidden

- **Choosing among calibrators needs a fourth split.** This harness has three,
  so the calibrator is pre-committed rather than selected. Admitted, not solved.
- **The sanity gate's bound is still borrowed at runtime**, not derived: `run.py`
  passes `1.11` and `> 300` from Anki's `params.rs:182`, where they were chosen
  for FSRS card-level recall on Anki's benchmark corpus. The derivations that
  would replace them now exist and are tested
  (`derive_thresholds.py::derive_sanity_gate_min_items` and the two bound
  functions), but they return `UNKNOWN` without real data — so **Appendix B item
  5 remains not discharged**. An implemented procedure is not a delivered number.
- **No threshold in `thresholds.json` has a value.** All eight are `UNKNOWN`.
  This is the honest state, and it is why `BRAINLIFT.md` §7 still reads TBD.
- **Per-student held-out slices are fixed at 40 reviews** for every student,
  which gives every gate equal statistical power. Real data would not.
- **On perfectly separable data the Platt fit does not fully converge** at the
  fixed 4,000-step budget; seeds then agree to ~4 decimals instead of bit for
  bit. Measured and documented in `calibration.py`, not glossed.
