# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tests for the Appendix B calibration core.

    python3 speedrun-analysis/appendix_b/test_appendix_b.py

Standard library only; no pytest required. Exits non-zero on failure.

WHAT THESE TESTS ARE FOR
------------------------
Not coverage. Each one asserts a specific claim BRAINLIFT.md Appendix B makes,
against a value computed independently of the implementation -- by hand, from a
closed form, or from a structural property that must hold whatever the code
does:

  * the scoring rules agree with arithmetic done on paper (`test_brier_*`,
    `test_log_loss_*`), so a rewrite of metrics.py cannot silently change what
    "Brier score" means here;
  * the base-rate null scores its ENTROPY and its base*(1-base), which is the
    bar section 1 says a readiness model must clear;
  * isotonic regression is monotone, which is a guarantee rather than an
    observation and therefore testable at any input;
  * the gate WITHHOLDS when the candidate loses -- a gate that cannot refuse is
    not a gate;
  * accuracy is absent from metrics.py, asserted by scanning the module's own
    namespace and source, because the ban is only worth as much as its
    enforcement.

If one of these fails, do not edit the expected value. Establish which of the
code or the claim is wrong, and if the claim is wrong, record it in BRAINLIFT.md
section 8 with the original preserved -- the protocol used for the FSRS
precedent error.
"""

from __future__ import annotations

import math
import sys
import traceback
import types
from pathlib import Path

# Compile from source text; never trust a .pyc. Same reasoning as
# appendix_a/test_model.py: Python invalidates a source .pyc on (mtime seconds,
# size), so a same-length edit inside one mtime second is served stale and the
# test then passes on code that is not on disk.
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent


def _load(name: str) -> types.ModuleType:
    path = HERE / f"{name}.py"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


metrics = _load("metrics")
calibration = _load("calibration")
gates = _load("gates")


def close(actual: float, expected: float, places: int = 9) -> bool:
    return abs(actual - expected) < 0.5 * 10.0 ** (-places)


def eq(actual: float, expected: float, label: str, places: int = 9) -> None:
    if not close(actual, expected, places):
        raise AssertionError(
            f"{label}: expected {expected!r}, got {actual!r} (disagreement at {places} dp)"
        )


# ---------------------------------------------------------------------------
# 1. THE SCORING RULES, AGAINST VALUES COMPUTED BY HAND
# ---------------------------------------------------------------------------

HAND_PROBS = [0.9, 0.8, 0.1, 0.4]
HAND_OUTCOMES = [1, 1, 0, 1]
"""One deliberately awkward vector: three forecasts roughly right, one (0.4 on
an event that happened) badly wrong, so both rules have something to charge."""


def test_brier_of_a_known_vector() -> None:
    """Brier of [0.9, 0.8, 0.1, 0.4] against [1, 1, 0, 1], computed by hand.

        (0.9-1)^2 = 0.01
        (0.8-1)^2 = 0.04
        (0.1-0)^2 = 0.01
        (0.4-1)^2 = 0.36
        sum 0.42, over 4 -> 0.105
    """
    eq(metrics.brier_score(HAND_PROBS, HAND_OUTCOMES), 0.105, "Brier of the hand vector", 12)


def test_log_loss_of_a_known_vector() -> None:
    """Log loss of the same vector, in nats, computed by hand from natural logs.

        -ln(0.9) = 0.105360515657826
        -ln(0.8) = 0.223143551314210
        -ln(0.9) = 0.105360515657826   (the 0.1 forecast on a 0 outcome)
        -ln(0.4) = 0.916290731874155
        sum 1.350155314504017, over 4 -> 0.337538828626004
    """
    value, clamped = metrics.log_loss(HAND_PROBS, HAND_OUTCOMES)
    eq(value, 0.337538828626004, "log loss of the hand vector", 12)
    assert clamped == 0, f"nothing in this vector should clamp, got {clamped}"


def test_brier_is_perfect_and_worst_at_the_extremes() -> None:
    """A perfect forecaster scores 0; a perfectly wrong one scores 1."""
    eq(metrics.brier_score([1.0, 0.0, 1.0], [1, 0, 1]), 0.0, "Brier of a perfect forecast", 12)
    eq(metrics.brier_score([0.0, 1.0, 0.0], [1, 0, 1]), 1.0, "Brier of a perfectly wrong one", 12)


def test_log_loss_clamps_and_reports_that_it_clamped() -> None:
    """A confident wrong forecast is charged the clamp, and the clamp is COUNTED.

    The reported value is therefore a lower bound on an unbounded quantity, and
    the count is what lets a report say so instead of quietly rounding infinity
    down to 34.5 nats.
    """
    value, clamped = metrics.log_loss([0.0, 1.0], [1, 1])
    assert clamped == 2, f"both extreme forecasts should be clamped, got {clamped}"
    eq(value, -math.log(metrics.EPS) / 2.0, "clamped log loss", 6)


def test_validation_refuses_malformed_input() -> None:
    """Length mismatch, empty input, out-of-range probabilities and non-binary
    outcomes must RAISE, not return a plausible number."""
    for bad in (
        lambda: metrics.brier_score([0.5, 0.5], [1]),
        lambda: metrics.brier_score([], []),
        lambda: metrics.brier_score([1.5], [1]),
        lambda: metrics.brier_score([0.5], [2]),
    ):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("malformed input was accepted instead of raising")


# ---------------------------------------------------------------------------
# 2. THE BASE-RATE NULL SCORES WHAT IT SHOULD
# ---------------------------------------------------------------------------


def test_base_rate_null_scores_its_closed_form() -> None:
    """A constant predictor at the base rate scores base*(1-base) on Brier and
    the binary ENTROPY of the base rate on log loss.

    At the 91% US MD first-attempt pass rate (BRAINLIFT.md section 1):
        Brier    = 0.91 * 0.09                     = 0.0819
        log loss = -(0.91*ln 0.91 + 0.09*ln 0.09)  = 0.302538...

    These two numbers are the bar. A readiness model that does not beat them has
    not been shown to do anything a coin weighted to 91% does not do.
    """
    n, rate = 10000, 0.91
    outcomes = [1] * 9100 + [0] * 900
    preds = metrics.base_rate_null(rate, n)
    eq(metrics.brier_score(preds, outcomes), 0.0819, "null Brier at 91%", 12)
    eq(metrics.brier_score(preds, outcomes), rate * (1 - rate), "null Brier == base*(1-base)", 12)
    entropy = -(rate * math.log(rate) + (1 - rate) * math.log(1 - rate))
    eq(metrics.log_loss(preds, outcomes)[0], entropy, "null log loss == entropy", 12)
    eq(entropy, 0.30253782309749805, "the entropy value itself", 12)


def test_closed_forms_match_the_empirical_implementation() -> None:
    """`constant_predictor_*` must agree with scoring an actual vector, at
    rates that are NOT the base rate as well as at it."""
    outcomes = [1] * 730 + [0] * 270  # a 73% IMG-like base rate
    base = 0.73
    for rate in (0.5, 0.73, 0.91, 0.99):
        preds = metrics.base_rate_null(rate, len(outcomes))
        eq(
            metrics.brier_score(preds, outcomes),
            metrics.constant_predictor_brier(rate, base),
            f"closed-form Brier at rate {rate}",
            10,
        )
        eq(
            metrics.log_loss(preds, outcomes)[0],
            metrics.constant_predictor_log_loss(rate, base),
            f"closed-form log loss at rate {rate}",
            10,
        )


def test_a_constant_predictor_has_zero_resolution() -> None:
    """The Murphy decomposition must expose a constant predictor as one.

    This is the diagnostic BRAINLIFT.md section 1 needs: resolution is how much
    the model separates anybody, and for a constant it is exactly zero however
    good its Brier score looks.
    """
    outcomes = [1] * 91 + [0] * 9
    parts = metrics.brier_decomposition(metrics.base_rate_null(0.91, 100), outcomes)
    eq(parts.resolution, 0.0, "resolution of a constant predictor", 12)
    eq(parts.uncertainty, 0.91 * 0.09, "uncertainty is a property of the outcomes", 12)
    eq(parts.residual, 0.0, "residual is zero when forecasts are constant in a bin", 12)


def test_skill_is_zero_against_itself_and_positive_for_a_better_model() -> None:
    outcomes = [1] * 91 + [0] * 9
    flat = metrics.skill_vs_null(metrics.base_rate_null(0.91, 100), outcomes, 0.91)
    eq(flat.brier_skill, 0.0, "a constant has zero Brier skill against itself", 12)
    eq(flat.log_loss_skill, 0.0, "a constant has zero log-loss skill against itself", 12)
    assert not flat.beats_null, "a constant must not be recorded as beating itself"
    informed = metrics.skill_vs_null([0.99] * 91 + [0.2] * 9, outcomes, 0.91)
    assert informed.beats_null, "a model that separates the outcomes must beat the null"
    assert informed.brier_skill > 0.5, f"expected large skill, got {informed.brier_skill}"


# ---------------------------------------------------------------------------
# 3. RELIABILITY BINNING
# ---------------------------------------------------------------------------


def test_reliability_bins_are_exhaustive_and_keep_empty_bins() -> None:
    curve = metrics.reliability_curve([0.05, 0.95, 0.95], [0, 1, 0], n_bins=10)
    assert len(curve) == 10, f"expected 10 bins, got {len(curve)}"
    assert sum(b.count for b in curve) == 3, "every forecast must land in exactly one bin"
    assert curve[0].count == 1 and curve[9].count == 2
    assert curve[5].count == 0, "empty bins must be present, not dropped"
    eq(curve[9].observed, 0.5, "observed frequency in the top bin", 12)
    eq(curve[9].mean_predicted, 0.95, "mean forecast in the top bin", 12)


def test_a_forecast_of_exactly_one_lands_in_the_last_bin() -> None:
    """p = 1.0 would index out of range under naive binning. It must not."""
    curve = metrics.reliability_curve([1.0], [1], n_bins=10)
    assert curve[9].count == 1, "p = 1.0 must fall in the last bin"


# ---------------------------------------------------------------------------
# 4. ACCURACY IS ABSENT, AND THAT IS ENFORCED
# ---------------------------------------------------------------------------


def test_metrics_module_defines_no_accuracy_function() -> None:
    """BRAINLIFT.md section 1 forbids accuracy. This asserts the ban mechanically.

    Scans the module namespace for any callable whose name suggests a
    threshold-and-count metric. At a 91% base rate a constant "pass" predictor
    scores ~91% accuracy, so the metric cannot distinguish this project's model
    from the degenerate classifier it exists to avoid being.
    """
    banned = ("accuracy", "acc", "hit_rate", "percent_correct", "pct_correct",
              "error_rate", "correct_rate", "misclassification")
    for name, obj in vars(metrics).items():
        lowered = name.lower()
        for token in banned:
            if token in lowered and callable(obj):
                raise AssertionError(
                    f"metrics.py defines a callable named {name!r}, which looks like the "
                    "forbidden accuracy metric (BRAINLIFT.md section 1)"
                )


def test_metrics_source_contains_the_stated_reason_for_the_ban() -> None:
    """The refusal has to be documented where a reader will find it, not just
    obeyed. If the explanation is deleted, the ban becomes folklore."""
    source = (HERE / "metrics.py").read_text(encoding="utf-8")
    for needle in ("WHY THERE IS NO accuracy()", "91%", "constant function"):
        assert needle in source, f"metrics.py no longer explains the accuracy ban: {needle!r}"


# ---------------------------------------------------------------------------
# 5. CALIBRATION -- ISOTONIC IS MONOTONE, PLATT IS SEED-INVARIANT
# ---------------------------------------------------------------------------


def test_isotonic_is_monotone() -> None:
    """PAV output must be non-decreasing everywhere, on deliberately non-monotone
    input. This is a GUARANTEE of the algorithm, so it is testable at any point,
    not just at the fitted ones."""
    scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    outcomes = [0, 1, 0, 1, 1, 0, 1, 0, 1]  # zig-zag: a monotone fit must smooth it
    iso = calibration.IsotonicCalibrator().fit(scores, outcomes)
    previous = -1.0
    for i in range(0, 1201):
        x = -0.1 + i / 1000.0
        value = iso.predict(x)
        assert value >= previous - 1e-12, (
            f"isotonic output decreased at x = {x}: {value} < {previous}"
        )
        assert 0.0 <= value <= 1.0, f"isotonic output {value} left [0, 1] at x = {x}"
        previous = value


def test_isotonic_recovers_an_already_monotone_pattern_exactly() -> None:
    """With no violations to pool, PAV must leave the data alone: the fitted
    blocks are the input, and the fit is exact."""
    scores = [0.1, 0.2, 0.3, 0.4]
    outcomes = [0, 0, 1, 1]
    iso = calibration.IsotonicCalibrator().fit(scores, outcomes)
    eq(iso.predict(0.1), 0.0, "isotonic at the first point", 12)
    eq(iso.predict(0.4), 1.0, "isotonic at the last point", 12)


def test_isotonic_pools_a_pure_violation_to_the_mean() -> None:
    """Perfectly reversed data has no monotone structure at all, so PAV must
    collapse it to a single block at the overall mean."""
    iso = calibration.IsotonicCalibrator().fit([0.1, 0.2, 0.3, 0.4], [1, 1, 0, 0])
    for x in (0.1, 0.25, 0.4, 5.0):
        eq(iso.predict(x), 0.5, f"pooled isotonic value at {x}", 12)
    assert len(iso.ys) == 1, f"a pure violation must pool to one block, got {len(iso.ys)}"


def test_isotonic_clamps_outside_the_fitted_range() -> None:
    iso = calibration.IsotonicCalibrator().fit([0.2, 0.4, 0.6], [0, 0, 1])
    eq(iso.predict(-99.0), iso.ys[0], "below the fitted range", 12)
    eq(iso.predict(99.0), iso.ys[-1], "above the fitted range", 12)


def test_platt_recovers_a_known_logistic_relationship() -> None:
    """Fit Platt on data generated FROM a logistic and check it lands near the
    truth. Deterministic data, so this is a real convergence check rather than a
    lucky draw: p = sigmoid(2s - 1) evaluated on a fixed grid, with outcome
    counts proportional to that probability."""
    scores, outcomes = [], []
    for i in range(201):
        s = -5.0 + i * 0.05
        p = calibration.sigmoid(2.0 * s - 1.0)
        ones = int(round(p * 20))
        scores.extend([s] * 20)
        outcomes.extend([1] * ones + [0] * (20 - ones))
    platt = calibration.PlattCalibrator().fit(scores, outcomes)
    eq(platt.a, 2.0, "Platt slope A", 1)
    eq(platt.b, -1.0, "Platt intercept B", 1)


def test_platt_is_seed_invariant() -> None:
    """The objective is convex, so the seeded initialisation must not change the
    answer. If this fails, the fit has not converged and PLATT_ITERATIONS is
    misdocumented -- which would make every calibrated number in the report a
    function of a random draw."""
    scores = [i / 100.0 for i in range(100)]
    outcomes = [1 if i > 40 else 0 for i in range(100)]
    fits = [
        calibration.PlattCalibrator().fit(scores, outcomes, seed=seed)
        for seed in (1, 7, 20260802, 999999)
    ]
    for other in fits[1:]:
        eq(other.a, fits[0].a, "Platt slope across seeds", 4)
        eq(other.b, fits[0].b, "Platt intercept across seeds", 4)


def test_platt_reduces_log_loss_on_a_miscalibrated_forecast() -> None:
    """Platt must actually help when there is something to fix: take a set of
    scores whose sigmoid is systematically overconfident and check the fitted
    calibrator lowers log loss on the SAME data it was fitted on. (In-sample on
    purpose -- this tests the optimiser, not generalisation. `run.py` does the
    out-of-sample version and reports that it did NOT help there.)"""
    scores, outcomes = [], []
    for i in range(400):
        s = -4.0 + i * 0.02
        p = calibration.sigmoid(0.4 * s)  # true relationship is much flatter
        scores.append(s)
        outcomes.append(1 if (i * 7919) % 1000 < p * 1000 else 0)
    raw = [calibration.sigmoid(s) for s in scores]
    platt = calibration.PlattCalibrator().fit(scores, outcomes)
    fitted = platt.predict_all(scores)
    before = metrics.log_loss_value(raw, outcomes)
    after = metrics.log_loss_value(fitted, outcomes)
    assert after < before, f"Platt failed to improve an overconfident forecast: {after} >= {before}"


# ---------------------------------------------------------------------------
# 6. SPLITS AND SHRINKAGE
# ---------------------------------------------------------------------------


def test_three_way_split_is_disjoint_exhaustive_and_deterministic() -> None:
    fit, calib, ev = calibration.three_way_split(1000, seed=20260802)
    assert len(fit) + len(calib) + len(ev) == 1000, "the split must be exhaustive"
    assert sorted(fit + calib + ev) == list(range(1000)), "every index exactly once"
    assert not (set(fit) & set(calib)) and not (set(fit) & set(ev))
    assert not (set(calib) & set(ev))
    again = calibration.three_way_split(1000, seed=20260802)
    assert (fit, calib, ev) == again, "the same seed must give the same split"
    other = calibration.three_way_split(1000, seed=1)
    assert other != (fit, calib, ev), "a different seed must give a different split"


def test_assert_disjoint_actually_raises() -> None:
    """The guard has to fail loudly, or it is decoration. A leak between fit and
    eval would make every figure in Appendix B optimistic in a way no reader
    could detect from the output."""
    try:
        calibration.assert_disjoint(("fit", [1, 2, 3]), ("eval", [3, 4]))
    except AssertionError as exc:
        assert "3" in str(exc), f"the message should name the leaked index: {exc}"
        return
    raise AssertionError("assert_disjoint accepted overlapping groups")


def test_shrinkage_endpoints_and_direction() -> None:
    """k = 0 is the raw estimate, k -> large is the prior, and n rising moves
    the blend toward the estimate monotonically."""
    eq(calibration.shrink_toward_prior(0.4, 0.85, n=10, k=0), 0.4, "k = 0 is the estimate", 12)
    eq(calibration.shrink_toward_prior(0.4, 0.85, n=0, k=50), 0.85, "n = 0 is the prior", 12)
    eq(calibration.shrink_toward_prior(0.4, 0.85, n=50, k=50), 0.625, "n = k is the midpoint", 12)
    previous = calibration.shrink_toward_prior(0.4, 0.85, n=0, k=50)
    for n in (1, 5, 20, 100, 1000):
        value = calibration.shrink_toward_prior(0.4, 0.85, n=n, k=50)
        assert value < previous, f"more data must move the blend toward the estimate at n = {n}"
        previous = value


def test_fit_shrinkage_constant_prefers_the_prior_when_estimates_are_noise() -> None:
    """If per-student estimates carry no information, the fitted k must be large
    -- i.e. the machinery must be able to say 'trust the prior'. Built from a
    deterministic pattern so the test is not a draw."""
    prior = 0.85
    records = []
    for i in range(200):
        estimate = 0.05 if i % 2 else 0.95  # wild, and unrelated to the outcomes
        outcomes = [1 if (i * 31 + j * 7) % 100 < 85 else 0 for j in range(20)]
        records.append((estimate, 4, outcomes))
    best, curve = calibration.fit_shrinkage_constant(records, prior=prior)
    assert best >= 50, f"noise estimates should shrink hard toward the prior, got k = {best}"
    assert curve[0][1] > curve[-1][1], "k = 0 must be worse than heavy shrinkage here"


# ---------------------------------------------------------------------------
# 7. THE GATES -- THEY MUST REFUSE, AND THEY MUST NOT COLLAPSE
# ---------------------------------------------------------------------------

WINNING_OUTCOMES = [1] * 18 + [0] * 2  # 90% recall


def test_memory_gate_withholds_when_the_candidate_loses() -> None:
    """The load-bearing test. A candidate that predicts worse than the incumbent
    on the student's later reviews must be discarded -- upstream's rule, at
    `params.rs:156`: keep what you had unless the new fit wins."""
    result = gates.memory_gate(
        "s0001",
        candidate_probs=[0.50] * 20,   # far from the truth
        incumbent_probs=[0.88] * 20,   # close to the truth
        later_review_outcomes=WINNING_OUTCOMES,
    )
    assert result.decision == gates.WITHHOLD, f"expected WITHHOLD, got {result.decision}"
    assert not result.reports
    assert result.margin < 0, f"a losing candidate must have a negative margin: {result.margin}"
    assert "did not beat" in result.reason


def test_memory_gate_reports_when_the_candidate_wins() -> None:
    result = gates.memory_gate(
        "s0002",
        candidate_probs=[0.90] * 20,
        incumbent_probs=[0.60] * 20,
        later_review_outcomes=WINNING_OUTCOMES,
    )
    assert result.decision == gates.REPORT, f"expected REPORT, got {result.decision}"
    assert result.margin > 0


def test_a_tie_goes_to_the_incumbent() -> None:
    """Upstream's comparison is `if current <= optimized { keep current }`, so
    equal evidence keeps the incumbent. Inherited asymmetry, not invented: a new
    model must EARN its place."""
    result = gates.memory_gate(
        "s0003",
        candidate_probs=[0.80] * 20,
        incumbent_probs=[0.80] * 20,
        later_review_outcomes=WINNING_OUTCOMES,
    )
    assert result.decision == gates.WITHHOLD, "an exact tie must keep the incumbent"


def test_performance_gate_withholds_against_the_topic_prior() -> None:
    """Same mechanism, different comparator -- and it must refuse just as hard."""
    outcomes = [1] * 12 + [0] * 8  # 60% -- almost exactly the topic prior
    result = gates.performance_gate(
        "s0004",
        candidate_probs=[0.95] * 20,
        topic_prior_probs=[0.62] * 20,
        later_item_outcomes=outcomes,
    )
    assert result.decision == gates.WITHHOLD
    assert result.comparator == gates.COMPARATOR_TOPIC_PRIOR


def test_gates_refuse_to_run_on_an_empty_held_out_set() -> None:
    try:
        gates.memory_gate("s0005", [], [], [])
    except ValueError:
        return
    raise AssertionError("the gate scored an empty held-out set instead of raising")


def test_readiness_model_gate_withholds_against_the_base_rate_null() -> None:
    """POV 2's falsifier (4). A readiness model that cannot beat a constant at
    the cohort pass rate must withhold, and BRAINLIFT.md pre-commits to what that
    means: ship two scores."""
    outcomes = [1] * 91 + [0] * 9
    useless = [0.91] * 100  # a constant wearing a model's clothes
    result = gates.readiness_model_gate(useless, outcomes, null_rate=0.91)
    assert result.decision == gates.WITHHOLD, f"expected WITHHOLD, got {result.decision}"
    assert "falsifier (4)" in result.reason
    assert result.layer == gates.LAYER_MODEL
    informative = [0.99] * 91 + [0.30] * 9
    assert gates.readiness_model_gate(informative, outcomes, 0.91).decision == gates.REPORT


def test_the_three_gates_do_not_collapse_into_one() -> None:
    """The layer difference is the content of BRAINLIFT.md section 7, so it is
    asserted structurally: three distinct layers/comparators/units, and Readiness
    returning a DIFFERENT TYPE from the per-student gates."""
    rows = gates.layer_table()
    assert len({r[1] for r in rows}) == 2, "Memory and Performance share a layer; Readiness must not"
    assert len({r[2] for r in rows}) == 3, "all three comparators must differ"
    assert len({r[3] for r in rows}) == 3, "all three held-out units must differ"
    mem = gates.memory_gate("s1", [0.9] * 20, [0.6] * 20, WINNING_OUTCOMES)
    perf = gates.performance_gate("s1", [0.9] * 20, [0.6] * 20, WINNING_OUTCOMES)
    assert type(mem) is type(perf), "the two per-student gates should share a result type"
    ready = gates.readiness_model_gate([0.99] * 91 + [0.3] * 9, [1] * 91 + [0] * 9, 0.91)
    assert not isinstance(ready, gates.GateResult), (
        "Readiness must NOT return a GateResult -- a model-level result carries no "
        "student and must not be usable as if it did"
    )
    assert not hasattr(ready, "student_id"), "a model-level result cannot name a student"


def test_readiness_abstains_per_student_even_when_the_model_passes() -> None:
    """The two readiness layers are independent, and this is the case that proves
    it: a cohort-level pass does NOT entitle a student below the coverage floor
    to a number. The identical component log losses REPORT under the Memory
    gate, which is the same numbers reaching a different decision at a different
    layer -- the non-collapse, demonstrated behaviourally rather than asserted."""
    outcomes = [1] * 91 + [0] * 9
    good_cohort = [0.99] * 91 + [0.30] * 9
    mem = gates.memory_gate("s9", [0.90] * 20, [0.60] * 20, WINNING_OUTCOMES)
    perf = gates.performance_gate("s9", [0.90] * 20, [0.60] * 20, WINNING_OUTCOMES)
    assert mem.reports and perf.reports, "both components should report in this fixture"
    decision = gates.readiness_gate(
        "s9", good_cohort, outcomes, 0.91,
        coverage=0.20, coverage_floor=0.50,
        memory_result=mem, performance_result=perf,
    )
    assert decision.model_level.decision == gates.REPORT, "the model-level test should pass"
    assert decision.decision == gates.WITHHOLD, "a student below the coverage floor gets nothing"
    assert "coverage" in decision.reason
    ok = gates.readiness_gate(
        "s9", good_cohort, outcomes, 0.91,
        coverage=0.80, coverage_floor=0.50,
        memory_result=mem, performance_result=perf,
    )
    assert ok.decision == gates.REPORT, "clearing every condition must produce a report"


def test_a_failed_model_level_test_withholds_from_a_perfect_student() -> None:
    """The asymmetry that makes the layers matter: a cohort-level failure refuses
    EVERYONE, including a student whose own data is excellent."""
    outcomes = [1] * 91 + [0] * 9
    mem = gates.memory_gate("s9", [0.90] * 20, [0.60] * 20, WINNING_OUTCOMES)
    perf = gates.performance_gate("s9", [0.90] * 20, [0.60] * 20, WINNING_OUTCOMES)
    decision = gates.readiness_gate(
        "s9", [0.91] * 100, outcomes, 0.91,
        coverage=1.00, coverage_floor=0.50,
        memory_result=mem, performance_result=perf,
    )
    assert decision.student.decision == gates.REPORT, "the student clears every personal condition"
    assert decision.decision == gates.WITHHOLD, "and is still refused, because the model failed"
    assert decision.reason.startswith("model-level")


def test_sanity_gate_reports_not_run_as_withhold() -> None:
    """A check that could not be evaluated must not read as a pass. This is the
    failure mode that makes a green dashboard mean nothing."""
    result = gates.sanity_gate([0.9] * 10, [1] * 10, min_items=300, log_loss_bound=1.11,
                               bound_provenance="test")
    assert result.decision == gates.WITHHOLD
    assert "did NOT run" in result.reason
    assert math.isnan(result.log_loss), "no log loss should be reported when the check did not run"


def test_sanity_gate_can_fail_a_model_that_beat_its_incumbent() -> None:
    """The whole reason the absolute gate exists: relative and absolute quality
    are different questions, and only this gate asks the second."""
    outcomes = [1 if i % 2 else 0 for i in range(400)]
    hopeless = [0.99 if i % 3 else 0.01 for i in range(400)]  # confidently wrong, often
    result = gates.sanity_gate(hopeless, outcomes, min_items=300, log_loss_bound=1.11,
                               bound_provenance="test")
    assert result.decision == gates.WITHHOLD, "a badly calibrated model must fail the absolute gate"
    assert result.log_loss > 1.11


# ---------------------------------------------------------------------------
# 8. THE SWEEPS
# ---------------------------------------------------------------------------


def test_floor_sweep_scores_every_floor_on_identical_data() -> None:
    """Each candidate floor must emit a forecast for every student, or the
    floors are being compared on different data and the argmin is meaningless."""
    records = [
        {
            "n_items": n,
            "candidate_probs": [0.9] * 10,
            "incumbent_probs": [0.85] * 10,
            "gate_wins": True,
            "outcomes": [1] * 9 + [0],
        }
        for n in (0, 5, 50, 500)
    ]
    best, rows = gates.sweep_items_floor(records, [0, 10, 100, 1000])
    assert len(rows) == 4
    for row in rows:
        assert row.n_students_reporting + row.n_students_gated_out == 4
    assert rows[0].policy_log_loss <= rows[-1].policy_log_loss
    assert best.floor == 0, "with a uniformly better candidate the argmin floor must be 0"


def test_abstention_comparison_separates_the_overlap_from_the_refused() -> None:
    """The comparison must only score the region where BOTH mechanisms emit, and
    must report the refused region separately -- the asymmetry BRAINLIFT.md POV 2
    insists on, because abstention cannot be Brier-scored where it fires."""
    records = [
        {"n": 2, "estimate": 0.30, "outcomes": [1] * 8 + [0] * 2},
        {"n": 400, "estimate": 0.85, "outcomes": [1] * 8 + [0] * 2},
    ]
    cmp_ = gates.abstention_vs_shrinkage(records, prior=0.85, k=50, floor=100, null_rate=0.85)
    assert cmp_.overlap_students == 1, "only the data-rich student is in the overlap"
    assert cmp_.abstained_students == 1
    assert cmp_.abstained_forecasts == 10, "the refused region must be counted in FORECASTS"
    assert not math.isnan(cmp_.abstained_shrinkage_log_loss)
    assert cmp_.overlap_winner in ("shrinkage", "abstention (raw estimate)", "tie")


def test_latency_cut_finds_a_planted_threshold() -> None:
    """Give the sweep a fitting set where sessions below 0.3 are pure noise and
    check it excludes them. Deterministic construction: no draws."""
    fractions = [0.05] * 50 + [0.9] * 50

    def evaluate(keep):
        # Log loss falls as fewer of the first 50 (noise) sessions are kept.
        kept_noise = sum(1 for i, k in enumerate(keep) if k and i < 50)
        return 0.5 + 0.01 * kept_noise

    best, curve = gates.fit_latency_cut(fractions, evaluate)
    assert 0.05 < best <= 0.9, f"the cut should land between the two populations, got {best}"
    assert len(curve) > 10


def test_coverage_sweep_skips_subsets_too_small_to_speak() -> None:
    coverages = [i / 100.0 for i in range(100)]
    probs = [0.9] * 100
    outcomes = [1 if i % 10 else 0 for i in range(100)]
    rows = gates.sweep_coverage_floor(coverages, probs, outcomes, 0.9, [0.0, 0.5, 0.9, 0.99])
    floors = [r.floor for r in rows]
    assert 0.99 not in floors, "a subset of one student must be skipped, not reported"
    assert all(r.n_students >= 20 for r in rows)


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


def main() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print("=" * 78)
    print("APPENDIX B TESTS -- metrics, calibration, gates")
    print("=" * 78)
    failures = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append((name, str(exc)))
            print(f"FAIL  {name}")
        except Exception:  # noqa: BLE001 -- report, do not mask
            failures.append((name, traceback.format_exc()))
            print(f"ERROR {name}")
        else:
            print(f"ok    {name}")
    print("-" * 78)
    if failures:
        print(f"{len(failures)} of {len(tests)} FAILED.")
        print("Do NOT edit an expected value to make one green. Establish which of the")
        print("code or the claim is wrong, and record the correction in BRAINLIFT.md 8.")
        for name, detail in failures:
            print()
            print(f"  {name}:")
            print(f"    {detail}")
        return 1
    print(f"{len(tests)} of {len(tests)} passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
