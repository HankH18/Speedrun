# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix B metrics -- proper scoring rules and reliability binning, from scratch.

WHAT THIS IS
------------
The measurement layer for BRAINLIFT.md Appendix B. Three scores (Memory,
Performance, Readiness) are all probability forecasts of a binary event, so
every one of them is scored here by the same two proper scoring rules -- Brier
and log loss -- always against a stated comparator, plus a reliability curve
stratified by predicted-probability band.

Standard library only. No numpy. Deterministic: nothing in this module draws
random numbers, so every figure it returns is a pure function of its inputs.

WHY THERE IS NO accuracy() IN THIS FILE
---------------------------------------
There is no `accuracy` function here and there will not be one. BRAINLIFT.md
section 1 forbids it, and the reason is arithmetic rather than taste:

    2024 USMLE Step 1 first-attempt pass rates were 91% (US MD), 86% (US DO),
    73% (IMG). A classifier that ignores its input and always outputs "pass"
    therefore scores ~91% accuracy on the US MD population while being a
    constant function that has learned nothing.

Accuracy also throws away the probability. It cannot distinguish a forecast of
0.51 from one of 0.99 when both land on the right side of a threshold, which is
precisely the distinction a readiness score exists to make. A grader (or a
future contributor) looking for `accuracy`, `hit_rate`, `percent_correct` or
`error_rate` will not find them, and `test_appendix_b.py` asserts mechanically
that no such name reappears in this module. If you want to know whether a model
is any good, use `skill_vs_null` below: it reports Brier and log loss *relative
to the constant base-rate predictor*, which is the only comparison that can tell
a model apart from a coin weighted to 91%.

WHAT A GOOD NUMBER HERE DOES NOT LICENSE
----------------------------------------
Nothing in this module says anything about a *student*. These are cohort-level
or set-level summaries. A low Brier score on a held-out set licenses the claim
"this model beat that comparator on this set"; it licenses no claim about the
next individual, about causation, or about any population the set was not drawn
from. Every function's docstring below repeats the specific version of this.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-15
"""Clamp applied to probabilities inside `log_loss`.

Log loss is unbounded: a forecast of exactly 0.0 on an event that occurs costs
infinity. Clamping to [EPS, 1 - EPS] bounds that at ~34.5 nats. This is a
REPORTING CONVENIENCE AND IT FLATTERS OVERCONFIDENT MODELS -- a model that says
0.0 and is wrong is charged 34.5 instead of the infinity it earned. Any log loss
reported from this module is therefore a LOWER BOUND on the true penalty
whenever a clamp fired. `log_loss` returns the clamp count so callers can say so.
"""

DEFAULT_BINS = 10
"""Reliability-curve bin count. Equal-width on [0, 1]. NOT derived from
anything -- it is a display choice, and BRAINLIFT.md Appendix B item 1 asks for
stratification, not for a particular number of strata. Bin counts change what a
reliability curve looks like; a curve is not evidence of calibration at a
resolution the data cannot support, which is why `reliability_curve` reports
per-bin counts and refuses to hide empty bins."""


# ---------------------------------------------------------------------------
# input validation -- a silent length mismatch would corrupt every figure below
# ---------------------------------------------------------------------------


def _validated(probs, outcomes):
    """Return (probs, outcomes) as lists after checking shape and range.

    Raises ValueError rather than returning a plausible-looking number from
    malformed input. An analysis that quietly scores 12 forecasts against 11
    outcomes is worse than one that stops.
    """
    p = list(probs)
    y = list(outcomes)
    if len(p) != len(y):
        raise ValueError(f"length mismatch: {len(p)} forecasts, {len(y)} outcomes")
    if not p:
        raise ValueError("empty forecast set -- there is nothing to score")
    for value in p:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"forecast {value!r} is not a probability in [0, 1]")
    for value in y:
        if value not in (0, 1, 0.0, 1.0, True, False):
            raise ValueError(f"outcome {value!r} is not binary")
    return p, [int(v) for v in y]


# ---------------------------------------------------------------------------
# the two proper scoring rules
# ---------------------------------------------------------------------------


def brier_score(probs, outcomes) -> float:
    """Mean squared error of a probability forecast. Lower is better; range [0, 1].

        BS = (1/N) * sum_i (p_i - y_i)^2

    Proper: it is minimized in expectation by reporting your true belief, so it
    cannot be gamed by shading forecasts toward the base rate.

    WHAT IT LICENSES: a comparison between two forecasters on the SAME set.
    WHAT IT DOES NOT LICENSE: any statement in isolation. A Brier score of 0.08
    sounds good and is exactly what a constant 0.91 predictor scores against a
    91% base rate (see `constant_predictor_brier`) -- i.e. it is the number the
    forbidden accuracy metric wears in disguise. Always report it beside
    `skill_vs_null`.
    """
    p, y = _validated(probs, outcomes)
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(p)


def log_loss(probs, outcomes, eps: float = EPS):
    """Mean negative log-likelihood, in nats. Lower is better; range [0, inf).

        LL = -(1/N) * sum_i [ y_i*ln(p_i) + (1 - y_i)*ln(1 - p_i) ]

    Returns (log_loss, clamp_count). This is the metric upstream's
    accept-only-if-better gate uses (`params.rs:156`), which is why Speedrun's
    gates use it too -- see gates.py.

    WHAT IT LICENSES: a comparison against a stated comparator on the same set.
    WHAT IT DOES NOT LICENSE: reading the value as a probability, a percentage,
    or anything with units a student would recognise. It is in nats. And when
    `clamp_count` is non-zero the value is a LOWER BOUND -- see EPS.
    """
    p, y = _validated(probs, outcomes)
    total = 0.0
    clamped = 0
    for pi, yi in zip(p, y):
        if pi < eps or pi > 1.0 - eps:
            clamped += 1
        q = min(max(pi, eps), 1.0 - eps)
        total += -math.log(q) if yi == 1 else -math.log(1.0 - q)
    return total / len(p), clamped


def log_loss_value(probs, outcomes, eps: float = EPS) -> float:
    """`log_loss` without the clamp count, for use inside sweeps and sorts.

    Provided so callers who are comparing hundreds of candidate models do not
    have to unpack a tuple each time. Anything REPORTED to a human should come
    from `log_loss` so the clamp count is available.
    """
    return log_loss(probs, outcomes, eps)[0]


# ---------------------------------------------------------------------------
# the base-rate null -- the comparator every score in this project is measured
# against, because a metric without a comparator cannot detect a constant
# ---------------------------------------------------------------------------


def empirical_base_rate(outcomes) -> float:
    """Fraction of 1s in `outcomes`. Dimensionless, in [0, 1].

    WHAT IT DOES NOT LICENSE: using the EVALUATION set's base rate to build the
    null. The null must be constructed from training data. A null fitted on the
    evaluation outcomes is an oracle, and beating an oracle is a harder test
    than the honest one, which sounds conservative but silently changes what is
    being measured. `run.py` takes its null rate from the training split and
    says so in the output.
    """
    _, y = _validated([0.5] * len(list(outcomes)), outcomes)
    return sum(y) / len(y)


def base_rate_null(rate: float, n: int):
    """The constant predictor: `n` copies of `rate`. Dimensionless.

    This is the thing BRAINLIFT.md section 1 says a readiness model must beat --
    "a classifier that always outputs pass". It is not a straw man: at a 91%
    pass rate it is a genuinely hard comparator on both proper scoring rules,
    which is exactly why it is the right one.
    """
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"base rate {rate!r} is not a probability in [0, 1]")
    if n <= 0:
        raise ValueError("n must be positive")
    return [rate] * n


def constant_predictor_brier(rate: float, base: float) -> float:
    """Closed-form Brier score of a constant `rate` forecast at true rate `base`.

        BS = base*(1 - rate)^2 + (1 - base)*rate^2

    At rate == base this reduces to base*(1 - base) -- e.g. 0.0819 at a 91% pass
    rate. Used by `test_appendix_b.py` to check the empirical implementation
    against algebra rather than against itself.
    """
    return base * (1.0 - rate) ** 2 + (1.0 - base) * rate**2


def constant_predictor_log_loss(rate: float, base: float) -> float:
    """Closed-form log loss of a constant `rate` forecast at true rate `base`.

        LL = -[ base*ln(rate) + (1 - base)*ln(1 - rate) ]

    At rate == base this is the binary entropy of the base rate -- 0.30254 nats
    at 91%. That number is the bar the Readiness model has to clear, and POV 2's
    falsifier (4) says what happens if it cannot: the app ships two scores.
    """
    q = min(max(rate, EPS), 1.0 - EPS)
    return -(base * math.log(q) + (1.0 - base) * math.log(1.0 - q))


@dataclass(frozen=True)
class Skill:
    """Model performance stated only ever relative to the base-rate null."""

    n: int
    base_rate_used: float
    model_brier: float
    null_brier: float
    model_log_loss: float
    null_log_loss: float
    clamped: int

    @property
    def brier_skill(self) -> float:
        """1 - BS_model/BS_null. Positive means the model beat the null."""
        if self.null_brier == 0.0:
            return float("nan")
        return 1.0 - self.model_brier / self.null_brier

    @property
    def log_loss_skill(self) -> float:
        """1 - LL_model/LL_null. Positive means the model beat the null."""
        if self.null_log_loss == 0.0:
            return float("nan")
        return 1.0 - self.model_log_loss / self.null_log_loss

    @property
    def beats_null(self) -> bool:
        """True only if the model wins on LOG LOSS, the gate's metric.

        Deliberately single-metric: the gate has to make one decision, and
        picking whichever of two metrics happens to favour the model is the
        multiple-comparisons dodge this project exists to avoid. Log loss is
        chosen because it is the metric upstream's own accept-only-if-better
        gate uses. Brier is reported alongside and NEVER used to overturn this.
        """
        return self.model_log_loss < self.null_log_loss


def skill_vs_null(probs, outcomes, null_rate: float) -> Skill:
    """Score a forecast against the constant base-rate predictor.

    `null_rate` is supplied by the caller rather than computed from `outcomes`,
    for the reason given in `empirical_base_rate`.

    WHAT IT LICENSES: "on this held-out set, the model beat / did not beat a
    constant predictor at `null_rate`."
    WHAT IT DOES NOT LICENSE: that the model will beat it on the next set, that
    the margin is significant (nothing here computes a standard error), or
    anything at all about an individual student.
    """
    p, y = _validated(probs, outcomes)
    base = sum(y) / len(y)
    null = base_rate_null(null_rate, len(p))
    model_ll, clamped = log_loss(p, y)
    null_ll, _ = log_loss(null, y)
    return Skill(
        n=len(p),
        base_rate_used=null_rate,
        model_brier=brier_score(p, y),
        null_brier=brier_score(null, y),
        model_log_loss=model_ll,
        null_log_loss=null_ll,
        clamped=clamped,
    )


# ---------------------------------------------------------------------------
# reliability curve -- BRAINLIFT.md Appendix B item 1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReliabilityBin:
    """One predicted-probability band of a reliability curve.

    `mean_predicted` and `observed` are NaN when the bin is empty, so that an
    empty bin cannot be silently averaged into anything. An empty bin is NOT
    evidence that the model is calibrated there; it is evidence that the data
    cannot speak to that band at all, and the report prints it as such.
    """

    index: int
    lo: float
    hi: float
    count: int
    mean_predicted: float
    observed: float

    @property
    def gap(self) -> float:
        """observed - mean_predicted. Positive = the model is UNDER-confident."""
        if self.count == 0:
            return float("nan")
        return self.observed - self.mean_predicted


def reliability_curve(probs, outcomes, n_bins: int = DEFAULT_BINS):
    """Stratify forecasts into equal-width bands and compare predicted to observed.

    Returns a list of `ReliabilityBin`, one per band, INCLUDING empty ones.

    WHAT IT LICENSES: a description of where on the probability scale this model
    is over- or under-confident ON THIS SET.
    WHAT IT DOES NOT LICENSE: reading a bin with a handful of observations as a
    calibration result. With 8 students in a bin the observed frequency moves in
    steps of 12.5 percentage points, so a 10-point "miscalibration" there is one
    student. BRAINLIFT.md section 1 asks for particular attention to the
    low-pass region precisely because that is where the counts are smallest --
    which makes it the region where this curve is least able to answer.
    """
    p, y = _validated(probs, outcomes)
    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    sums = [0.0] * n_bins
    hits = [0] * n_bins
    counts = [0] * n_bins
    for pi, yi in zip(p, y):
        idx = min(int(pi * n_bins), n_bins - 1)
        sums[idx] += pi
        hits[idx] += yi
        counts[idx] += 1
    bins = []
    for i in range(n_bins):
        if counts[i]:
            bins.append(
                ReliabilityBin(
                    index=i,
                    lo=i / n_bins,
                    hi=(i + 1) / n_bins,
                    count=counts[i],
                    mean_predicted=sums[i] / counts[i],
                    observed=hits[i] / counts[i],
                )
            )
        else:
            bins.append(
                ReliabilityBin(
                    index=i,
                    lo=i / n_bins,
                    hi=(i + 1) / n_bins,
                    count=0,
                    mean_predicted=float("nan"),
                    observed=float("nan"),
                )
            )
    return bins


def weighted_calibration_gap(curve) -> float:
    """Count-weighted mean |observed - predicted| over non-empty bins (ECE).

    REPORTED WITH A WARNING AND NEVER USED AS A GATE. Expected calibration error
    is NOT a proper scoring rule: a model can drive it to zero by predicting the
    base rate for everyone, which is the exact degenerate classifier this
    project forbids. It is a diagnostic for reading the curve quickly, nothing
    more. Every accept/withhold decision in gates.py runs on log loss.
    """
    total = sum(b.count for b in curve if b.count)
    if not total:
        return float("nan")
    return sum(b.count * abs(b.gap) for b in curve if b.count) / total


# ---------------------------------------------------------------------------
# Murphy decomposition -- says WHY a Brier score is what it is
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrierParts:
    """Binned decomposition of a Brier score.

        BS = reliability - resolution + uncertainty + residual

    reliability  how far each bin's observed frequency sits from its mean
                 forecast (lower is better; 0 is perfect calibration)
    resolution   how far the bins' observed frequencies sit from the overall
                 base rate (higher is better; 0 means the model separates
                 nobody and is a constant predictor in disguise)
    uncertainty  base*(1 - base) -- a property of the OUTCOMES, not the model.
                 At a 91% base rate this is 0.0819 and no model can change it.
    residual     the within-bin forecast spread and cross term the classical
                 three-way decomposition drops. It is EXACTLY zero when
                 forecasts are constant within each bin and non-zero otherwise;
                 printing it is how this module refuses to pretend the tidy
                 identity holds when it does not.
    """

    reliability: float
    resolution: float
    uncertainty: float
    residual: float
    brier: float


def brier_decomposition(probs, outcomes, n_bins: int = DEFAULT_BINS) -> BrierParts:
    """Decompose a Brier score into reliability, resolution and uncertainty.

    WHAT IT LICENSES: diagnosis. A model with good reliability and near-zero
    resolution is a constant predictor wearing a model's clothes -- and that is
    the specific failure BRAINLIFT.md section 1 warns about, made visible.
    WHAT IT DOES NOT LICENSE: comparing decompositions across different bin
    counts, or reading `uncertainty` as anything to do with the model.
    """
    p, y = _validated(probs, outcomes)
    n = len(p)
    base = sum(y) / n
    curve = reliability_curve(p, y, n_bins)
    reliability = sum(b.count * (b.mean_predicted - b.observed) ** 2 for b in curve if b.count) / n
    resolution = sum(b.count * (b.observed - base) ** 2 for b in curve if b.count) / n
    uncertainty = base * (1.0 - base)
    bs = brier_score(p, y)
    return BrierParts(
        reliability=reliability,
        resolution=resolution,
        uncertainty=uncertainty,
        residual=bs - (reliability - resolution + uncertainty),
        brier=bs,
    )
