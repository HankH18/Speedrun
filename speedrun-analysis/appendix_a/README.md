# Appendix A — analytic baseline

**This is the ANALYTIC baseline, not the simulation.** It is a closed-form
evaluation of the pre-registered model in
[`BRAINLIFT.md` Appendix A](../../BRAINLIFT.md). It computes what the algebra
implies. It does not simulate anything.

```
python3 speedrun-analysis/appendix_a/run.py         # the report
python3 speedrun-analysis/appendix_a/test_model.py  # the tamper-check
```

Pure Python 3, standard library only. No dependencies, no virtualenv, no
`pip install`. Both commands exit non-zero on failure.

---

## The pre-registration is frozen

Every constant and every expected result in this directory is pre-registered in
**BRAINLIFT.md, Appendix A**, which carries this notice:

> This design was written before the test was run, and must not be edited
> afterwards to match results.

That freeze is the whole point, so it is enforced mechanically rather than by
good intentions:

- **`model.py`** holds the model and the provenance of every constant — which
  are published (Pan & Rickard 2018, via BRAINLIFT.md §3.1), which are assumed,
  and which are inferred. Three of them are published; the rest are not, and the
  docstrings say so at each one.
- **`test_model.py`** asserts every pre-registered number to 3 decimal places or
  better — the primary, the null case, both falsifiers, all five points of the
  decision boundary, the Δ_a sweep, the whole α\* map, and the corner-break
  thresholds. **If someone edits the model to make a result come out, these
  fail.**
- **`run.py`** prints the report. One command, no arguments, no configuration.

If a test fails, the correct response is **not** to edit the expected value. It
is to establish which of the model or the pre-registration is wrong and record
the correction in BRAINLIFT.md §8 with the original preserved — the same
protocol used for the FSRS precedent error.

---

## Units — d and pp are not interchangeable

| Unit   | Meaning                                                                     |
| ------ | --------------------------------------------------------------------------- |
| **d**  | Effect size. **The pre-registered results live here.**                       |
| **pp** | Percentage points of held-out novel-item accuracy. **A conversion only.**    |

Converting d to pp requires σ, the between-learner SD, and **σ = 13 pp is
assumed, not literature-derived**. It scales the predicted effect and the ceiling
linearly, so a pp-denominated figure silently encodes a guess. Every pp number
printed by `run.py` names σ inline for that reason.

The headline deliverable — the decision boundary Δ_d\*(c) — is **σ-free**: gain
and penalty both scale by σ and it cancels. `test_boundary_is_sigma_free`
asserts this by moving σ and checking the boundary does not budge.

---

## What it computes

| Result                | Value                                                        |
| --------------------- | ------------------------------------------------------------ |
| **Primary**           | **+0.0608 d** (+0.79 pp at σ = 13 pp), at fixed α = 0.5, c = 2.0 |
| **Null case (Δ_d=0)** | **−0.0232 d** (−0.30 pp at σ = 13 pp) — the penalty alone     |
| **Ceiling tripwire**  | **0.30 d** (3.9 pp at σ = 13 pp) — Δ_d itself                 |
| **Boundary at c=2.0** | **Δ_d\* = 0.083 d** — 28% of the published effect             |
| **α\* (secondary)**   | **1.00** — the corner, for every c in [1.5, 3.0]              |

The primary is a **fixed-allocation comparison, not an optimization.** It answers
"does spending half the budget on congruent practice beat spending none?" It does
not answer what the best allocation is; that is α\*, and the two must not be
conflated.

### Void conditions

Checked and reported on every run, whether or not the result is favourable:

1. **Arm 1 winning under the null** (Δ_d = 0) — the harness is rigged and the
   entire result is void, not merely weakened.
2. **Any result above the 0.30 d ceiling** — no cost-bearing design can exceed
   Δ_d itself, so this is a harness bug, not a discovery.
3. **Transfer not going to exactly zero below the retention floor** — the floor
   is unimplemented and the run is void.

The third replaces a **withdrawn** void condition. An earlier draft said a corner
optimum at α = 1.0 meant the harness had failed to implement the floor. That does
not follow — a correctly-gated model corners at these parameters — so the check
now tests the implementation directly instead of inferring it from where the
optimum landed. **Where the optimum lands is a result, not a diagnostic.**

---

## The FSRS simulation is a separate, later deliverable

**Nothing in this directory simulates FSRS.** The analytic model has exactly one
hand-written line standing in for the entire retention consequence of studying
less:

```python
Delta_a = 4.0 * (deficit / 0.25) ** p     # p = 1, pre-registered
```

That line is **linear in α by construction** — verified symbolically, second
derivative identically zero. It is calibrated at α = 0.5 and extrapolated to
α = 1.0, which is *exactly where the corner optimum sits*. The prediction is
therefore made at the point furthest from its own calibration.

The FSRS-based simulation does not assert that shape — it **produces** it, from
spacing intervals lengthening or not, forgetting between reviews, lapses
resetting stability rather than pausing it, and per-card gating accumulating over
simulated time. Whatever shape that produces is the shape the model actually
implies, and no algebra here can anticipate it.

### Divergence is a FINDING, not an error

Stated here in advance so it cannot be chosen afterwards:

- **These figures are a pre-registered baseline, not a prediction the simulation
  is expected to reproduce.** They exist to be compared against.
- **If the simulation returns an interior α\*, that is a reportable finding.**
  The correct conclusion is that FSRS's dynamics make the retention penalty
  convex — which is informative about the mechanism and is exactly what the
  simulation was run to discover. It is **not** evidence that the harness is
  broken, and it **must not be "corrected" toward the algebra.** Mild convexity
  is sufficient: the corner breaks at p ≈ 1.55, well short of quadratic, and
  `run.py` reports that threshold precisely so a divergent simulated α\* can be
  read straight off it.
- **α\* = 1.00 is a prediction of the analytic model, not of the system under
  test.** It is the prediction in this appendix least expected to hold.
- **If the simulation merely reproduces the algebra, say so plainly.** That too
  is a result: the closed form was sufficient and the scheduling dynamics added
  nothing the linear approximation missed. A null finding about one's own added
  machinery is still a finding.
- **The primary is a second live question.** It is insulated from the penalty's
  *shape* (p cannot move it — every shape agrees at the calibration point by
  construction) but **not at all from its *level***:

  > net(α = 0.5) = 0.100 − 0.0098 × Δ_a   (in d, at c = 2.0)

  Δ_a = 4 pp is a calibration, not a derivation. In simulation **FSRS determines
  the actual accuracy loss from 25% fewer reviews** — an output of the scheduling
  dynamics, not an input to them. If it lands elsewhere the primary moves with
  it, and **reverses sign beyond Δ_a ≈ 10.204 pp**. A divergent simulated primary
  is a finding about the retention cost of studying less, reported with the
  implied Δ_a back-calculated. Only a divergence that survives back-calculation
  points at a defect.

---

## Determinism and seeds

There is **no stochastic component anywhere in this directory.** Every figure is
a closed-form evaluation, so reruns are bit-for-bit identical and no seed control
is required or offered. The pre-registered seed-control requirement applies to
the FSRS simulation deliverable, which does draw randomly.

---

## Known discrepancies with the printed pre-registration

Tracked in `test_known_discrepancies_in_the_pre_registration` so they cannot
drift further. **Neither is a model defect, and neither may be fixed by editing
the model.**

1. BRAINLIFT.md prints "net at α\*" for p = 1.75 as **0.075 d**; the model gives
   **0.074458 d**, which rounds to 0.074 d. α\* = 0.78 itself matches exactly, so
   this is a reporting-precision artefact, not a divergence.
2. BRAINLIFT.md's σ-sensitivity line reads "at σ = 10 the prediction is +0.77 pp;
   at σ = 16, +1.23 pp". Those are **0.077 d × σ — the pre-gating primary from
   before Revision 3**, not updated when gating moved the primary to +0.0608 d.
   The current conversions are **+0.61 pp** and **+0.97 pp**. Stale figures, not
   a live claim; the d result and the σ-free boundary are unaffected.

---

## Limitations

Repeated here rather than left in BRAINLIFT.md, because burying them would be the
same failure this project keeps recording.

- This tests whether the mechanism **could** work *given* the published effect
  sizes hold in this population. It is not evidence that it works in humans, and
  it cannot become such evidence by being run more times or more carefully.
- A model cannot discover an effect it was not given. Δ_d = 0.30 is an **input**.
  The only honest outputs are conditional and directional: *if* Δ_d is at least
  X, *then* the allocation pays. **That conditional is the deliverable.**
- The published effect sizes come from a meta-analysis of laboratory studies, not
  from medical students preparing for Step 1. Whether they transfer to this
  population is the assumption the sweep exists to expose, and it is not tested
  here.
- **No claim of student efficacy is made anywhere in this directory**, and none
  may be inferred from it.

---

## Files

| File             | Purpose                                                                  |
| ---------------- | ------------------------------------------------------------------------ |
| `model.py`       | The analytic model. Every constant carries its provenance in a docstring. |
| `run.py`         | The single entry point. Prints the full report.                          |
| `test_model.py`  | The tamper-check. Asserts every pre-registered number.                    |
| `README.md`      | This file.                                                               |
