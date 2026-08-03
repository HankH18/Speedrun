# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix B calibration -- Platt scaling, isotonic regression, and shrinkage.

WHAT THIS IS
------------
The layer that turns a raw model score into a probability that can be believed
at face value, plus the shrinkage estimator POV 2's falsifier (3) puts on trial
against abstention. Standard library only. No numpy, no sklearn.

THE THREE-WAY SPLIT IS NOT OPTIONAL
-----------------------------------
A calibrator fitted on the same data as the model it calibrates will report that
the model is well calibrated, because it has been shown the answers. A
calibrator fitted on the evaluation set will report that it fixed the model,
for the same reason. Both are the circularity BRAINLIFT.md section 8 records
against itself ("a threshold that constrains the analysis cannot also be
validated by it"), and both are easy to commit by accident.

So this module ships `three_way_split` and `assert_disjoint`, and every entry
point that fits something takes its data explicitly:

    FIT   split -- the model's parameters are estimated here
    CALIB split -- the calibrator (Platt / isotonic) is fitted here, DISJOINT
                   from FIT and from EVAL
    EVAL  split -- every number that gets reported comes from here, and nothing
                   is fitted on it, ever

`run.py` asserts the disjointness mechanically before it reports anything, and
`test_appendix_b.py` asserts that `assert_disjoint` actually raises.

SEEDS AND ITERATIONS
--------------------
`fit_logistic` (and therefore Platt) is full-batch gradient descent with a
SEEDED random initialisation, a fixed learning rate, and a fixed iteration
count -- all module constants below, all reported by `run.py`. The seed is real,
not decorative: it initialises the weights. Because the objective is convex the
seed should not change the answer, and `test_appendix_b.py` asserts exactly that
by fitting the same data from several seeds and requiring agreement. If that
test ever fails, the optimiser has not converged and the stated iteration count
is a lie.

Isotonic regression has no seed because pool-adjacent-violators has no random
component -- it is an exact algorithm, not an optimiser.
"""

from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# OPTIMISER CONSTANTS -- stated here so the report can print them
# ---------------------------------------------------------------------------

PLATT_ITERATIONS = 4000
"""Full-batch gradient steps for `fit_logistic`. Fixed, not tuned against a
result. Convergence is checked by the multi-seed agreement test, not asserted."""

PLATT_LEARNING_RATE = 0.5
"""Step size on standardized features. Fixed."""

PLATT_INIT_SCALE = 0.01
"""Half-width of the uniform seeded weight initialisation."""

PLATT_SEED = 20260802
"""Default initialisation seed. Convex objective, so this should not matter;
`test_platt_is_seed_invariant` is the check that it does not."""

PLATT_L2 = 1e-6
"""Ridge penalty on the weights, NOT on the bias.

Its job is to keep the fit finite when a feature separates the classes
perfectly -- without it the weights diverge and the "converged" parameters are
whatever the iteration count happened to reach. It is deliberately tiny; it is a
numerical guard, and it is NOT presented as a tuned regularisation strength.

MEASURED LIMIT, STATED RATHER THAN LEFT TO BE DISCOVERED. On perfectly separable
data the maximum-likelihood optimum is at infinity and this penalty is the only
thing bounding it, so PLATT_ITERATIONS stops being enough: separate seeds then
land ~2e-4 apart on a slope of ~47.6 (relative ~4e-6) instead of agreeing bit
for bit as they do on overlapping data. Nothing in `run.py` is fitted on
separable data, but a caller who supplies some is entitled to know that the
"deterministic given the seed" guarantee weakens exactly there.
"""


def sigmoid(z: float) -> float:
    """Logistic function, overflow-safe at large |z|."""
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


# ---------------------------------------------------------------------------
# splitting -- disjointness enforced, not assumed
# ---------------------------------------------------------------------------


def three_way_split(n: int, seed: int, fit_frac: float = 0.5, calib_frac: float = 0.25):
    """Deterministically split range(n) into (fit, calib, eval) index lists.

    Shuffles a fixed permutation under `seed`, then cuts. Returns sorted lists
    so downstream output is stable.

    WHAT IT LICENSES: an honest held-out evaluation, PROVIDED the units being
    split are independent. For Readiness the unit is a STUDENT, and splitting by
    student is what makes the held-out set meaningful -- see gates.py.
    WHAT IT DOES NOT LICENSE: splitting a single student's reviews at random and
    calling the result held out. Reviews of the same card are not independent
    and a random split leaks the answer across the boundary; per-student splits
    in `run.py` are therefore splits IN TIME (earlier reviews fit, later reviews
    score), which is what "the student's own later reviews" means in
    BRAINLIFT.md section 7.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0.0 < fit_frac < 1.0 or not 0.0 < calib_frac < 1.0:
        raise ValueError("fractions must lie strictly inside (0, 1)")
    if fit_frac + calib_frac >= 1.0:
        raise ValueError("fit_frac + calib_frac must leave room for an eval split")
    order = list(range(n))
    random.Random(seed).shuffle(order)
    a = int(round(n * fit_frac))
    b = a + int(round(n * calib_frac))
    fit, calib, ev = sorted(order[:a]), sorted(order[a:b]), sorted(order[b:])
    if not fit or not calib or not ev:
        raise ValueError(f"split of n={n} produced an empty part; n is too small")
    assert_disjoint(("fit", fit), ("calib", calib), ("eval", ev))
    return fit, calib, ev


def assert_disjoint(*named_groups) -> None:
    """Raise if any two of the named index groups share a member.

    Called by `three_way_split` on the way out and by `run.py` again before it
    reports anything. Belt and braces on purpose: a leak here would make every
    figure in Appendix B optimistic in a way no reader could detect from the
    output.
    """
    seen = {}
    for name, group in named_groups:
        for idx in group:
            if idx in seen:
                raise AssertionError(
                    f"split leak: index {idx} appears in both {seen[idx]!r} and {name!r}"
                )
            seen[idx] = name


# ---------------------------------------------------------------------------
# logistic regression by gradient descent -- Platt scaling is the 1-D case
# ---------------------------------------------------------------------------


@dataclass
class LogisticModel:
    """Fitted logistic model, carrying the standardisation it was fitted under.

    The means and standard deviations are computed on the FIT data and stored,
    so that predicting on the calibration or evaluation split reuses the
    training statistics. Re-standardising against the evaluation set would leak
    that set's distribution into the model -- a small leak, and a real one.
    """

    weights: list = field(default_factory=list)
    bias: float = 0.0
    means: list = field(default_factory=list)
    sds: list = field(default_factory=list)
    iterations: int = 0
    seed: int = 0
    final_log_loss: float = float("nan")

    def score(self, row) -> float:
        """Linear predictor (log-odds) for one standardized-on-the-fly row."""
        z = self.bias
        for w, x, mu, sd in zip(self.weights, row, self.means, self.sds):
            z += w * ((x - mu) / sd)
        return z

    def predict(self, row) -> float:
        """Probability for one feature row."""
        return sigmoid(self.score(row))

    def predict_all(self, rows):
        return [self.predict(r) for r in rows]


def _column_stats(rows):
    """Per-column (mean, sd) with a floor on sd so a constant column cannot divide by zero."""
    n = len(rows)
    k = len(rows[0])
    means = [sum(r[j] for r in rows) / n for j in range(k)]
    sds = []
    for j in range(k):
        var = sum((r[j] - means[j]) ** 2 for r in rows) / n
        sds.append(math.sqrt(var) if var > 1e-12 else 1.0)
    return means, sds


def fit_logistic(
    rows,
    outcomes,
    iterations: int = PLATT_ITERATIONS,
    learning_rate: float = PLATT_LEARNING_RATE,
    seed: int = PLATT_SEED,
    l2: float = PLATT_L2,
) -> LogisticModel:
    """Fit P(y = 1 | x) by full-batch gradient descent on LOG LOSS.

    Deterministic given `seed`: the only random draw is the initialisation, from
    `random.Random(seed).uniform(-PLATT_INIT_SCALE, PLATT_INIT_SCALE)`.

    Gradient descent on the mean log loss, `iterations` steps at a fixed
    `learning_rate` on standardized features. No line search, no early stopping,
    no convergence tolerance -- a fixed budget, so the run is reproducible and
    the cost is stated rather than discovered.

    WHAT IT LICENSES: a probability forecast whose parameters were chosen to
    minimise log loss ON THE DATA PASSED IN.
    WHAT IT DOES NOT LICENSE: treating the fitted coefficients as effects. They
    are correlational, they are not standard-errored, and on the synthetic
    cohort in `run.py` they recover a relationship that was put there by hand.
    """
    if len(rows) != len(outcomes):
        raise ValueError(f"length mismatch: {len(rows)} rows, {len(outcomes)} outcomes")
    if not rows:
        raise ValueError("cannot fit on an empty set")
    y = [int(v) for v in outcomes]
    means, sds = _column_stats(rows)
    xs = [[(r[j] - means[j]) / sds[j] for j in range(len(means))] for r in rows]
    rng = random.Random(seed)
    w = [rng.uniform(-PLATT_INIT_SCALE, PLATT_INIT_SCALE) for _ in means]
    b = rng.uniform(-PLATT_INIT_SCALE, PLATT_INIT_SCALE)
    n = len(xs)
    k = len(means)
    for _ in range(iterations):
        gw = [0.0] * k
        gb = 0.0
        for xi, yi in zip(xs, y):
            z = b + sum(w[j] * xi[j] for j in range(k))
            err = sigmoid(z) - yi
            gb += err
            for j in range(k):
                gw[j] += err * xi[j]
        b -= learning_rate * (gb / n)
        for j in range(k):
            w[j] -= learning_rate * (gw[j] / n + l2 * w[j])
    model = LogisticModel(
        weights=w, bias=b, means=means, sds=sds, iterations=iterations, seed=seed
    )
    preds = [model.predict(r) for r in rows]
    model.final_log_loss = -sum(
        math.log(max(p if t == 1 else 1.0 - p, 1e-15)) for p, t in zip(preds, y)
    ) / n
    return model


@dataclass
class PlattCalibrator:
    """Platt scaling: a one-dimensional logistic fitted on a raw score.

        p_calibrated = sigmoid(A * s + B)

    Platt scaling IS logistic regression on a single feature, so it is fitted by
    `fit_logistic` rather than by a second, subtly different optimiser.

    WHAT IT LICENSES: a monotone rescaling of the score onto the probability
    scale, fitted on a set disjoint from the model's own training set.
    WHAT IT DOES NOT LICENSE: fixing a model that ranks badly. Platt is monotone
    -- it cannot reorder two students, so it can repair overconfidence and can
    do nothing whatever about a model that puts the wrong student first. If the
    raw score has no resolution (see `metrics.brier_decomposition`), calibrating
    it produces a well-behaved constant predictor, which is precisely the thing
    BRAINLIFT.md section 1 forbids reporting.
    """

    model: LogisticModel = None

    @property
    def a(self) -> float:
        """A, on the RAW score scale (the fit standardizes internally)."""
        return self.model.weights[0] / self.model.sds[0]

    @property
    def b(self) -> float:
        """B, on the raw score scale."""
        return self.model.bias - self.model.weights[0] * self.model.means[0] / self.model.sds[0]

    def fit(self, scores, outcomes, seed: int = PLATT_SEED, iterations: int = PLATT_ITERATIONS):
        self.model = fit_logistic(
            [[s] for s in scores], outcomes, iterations=iterations, seed=seed
        )
        return self

    def predict(self, score: float) -> float:
        return self.model.predict([score])

    def predict_all(self, scores):
        return [self.predict(s) for s in scores]


# ---------------------------------------------------------------------------
# isotonic regression by pool-adjacent-violators
# ---------------------------------------------------------------------------


@dataclass
class IsotonicCalibrator:
    """Isotonic regression by pool-adjacent-violators (PAV).

    Fits the non-decreasing step function that minimises squared error against
    the binary outcomes. Non-parametric: unlike Platt it can bend anywhere, so
    it fixes shapes Platt cannot -- and for the same reason it overfits a small
    calibration set enthusiastically, converging on a step function with one
    step per outcome flip.

    ALGORITHM. Sort by score, pool tied scores, then sweep left to right
    maintaining a stack of blocks; whenever the last block's mean falls below
    the one before it (a violation of monotonicity), merge them and re-check.
    Exact, terminating, and free of any random component -- hence no seed.

    WHAT IT LICENSES: a monotone recalibration fitted on a disjoint set.
    WHAT IT DOES NOT LICENSE: reading its steps as structure in the world. A
    step is where the calibration set happened to flip. And like Platt it cannot
    reorder anyone: `test_isotonic_is_monotone` asserts the output is
    non-decreasing, which is the same fact stated as a guarantee.
    """

    xs: list = field(default_factory=list)
    ys: list = field(default_factory=list)

    def fit(self, scores, outcomes):
        if len(scores) != len(outcomes):
            raise ValueError(f"length mismatch: {len(scores)} scores, {len(outcomes)} outcomes")
        if not scores:
            raise ValueError("cannot fit on an empty set")
        pairs = sorted(zip([float(s) for s in scores], [float(int(v)) for v in outcomes]))
        # Pool exact ties first: identical scores must receive identical output.
        pooled = []
        for x, y in pairs:
            if pooled and pooled[-1][0] == x:
                sy, w = pooled[-1][1], pooled[-1][2]
                pooled[-1] = (x, sy + y, w + 1.0)
            else:
                pooled.append((x, y, 1.0))
        # PAV over the pooled points.
        blocks = []  # each: [x_max, sum_y, weight]
        for x, sy, w in pooled:
            blocks.append([x, sy, w])
            while len(blocks) >= 2 and (
                blocks[-2][1] / blocks[-2][2] >= blocks[-1][1] / blocks[-1][2]
            ):
                x2, sy2, w2 = blocks.pop()
                blocks[-1][0] = x2
                blocks[-1][1] += sy2
                blocks[-1][2] += w2
        self.xs = [blk[0] for blk in blocks]
        self.ys = [blk[1] / blk[2] for blk in blocks]
        return self

    def predict(self, score: float) -> float:
        """Value of the fitted step function at `score`.

        Clamped outside the fitted range: below the first block it returns the
        first block's value, above the last it returns the last. Extrapolating
        an isotonic fit is not defined, and inventing a slope for it would be
        making a number up.
        """
        if not self.xs:
            raise ValueError("calibrator is not fitted")
        i = bisect.bisect_left(self.xs, score)
        if i >= len(self.xs):
            return self.ys[-1]
        return self.ys[i]

    def predict_all(self, scores):
        return [self.predict(s) for s in scores]


# ---------------------------------------------------------------------------
# shrinkage -- the rival mechanism POV 2's falsifier (3) puts on trial
# ---------------------------------------------------------------------------

BORROWED_SHRINKAGE_K = 50.0
"""The constant Speedrun inherited and does NOT trust.

From fsrs-optimizer issue #116, where Expertium proposed n/(50 + n) for
smoothing MEDIAN REVIEW TIMES in a different estimator. BRAINLIFT.md section 7
records that it has no authority for this application; Appendix B item 7 owes a
fitted replacement. It is kept here only so the report can print the fitted
value beside the borrowed one.
"""

SHRINKAGE_K_GRID = tuple(float(k) for k in (0, 1, 2, 4, 8, 16, 24, 32, 50, 64, 96, 128, 192, 256))
"""Grid `fit_shrinkage_constant` searches. A grid, not an optimiser: the
objective is noisy and a continuous minimiser would report false precision."""


def shrink_toward_prior(estimate: float, prior: float, n: float, k: float) -> float:
    """Blend an estimate with a prior, weighted by how much data supports it.

        shrunk = (n / (k + n)) * estimate + (k / (k + n)) * prior

    k = 0 recovers the raw estimate; large k pins everything to the prior.

    WHAT IT LICENSES: a usable number in the low-data regime WHERE THE PRIOR
    CARRIES INFORMATION THE STUDENT DOES NOT ALREADY HAVE -- which BRAINLIFT.md
    POV 2 argues is true for Memory (FSRS ships defaults fitted across ~20k
    collections) and false for Readiness (the only population prior is the pass
    rate, which is the forbidden constant predictor).
    WHAT IT DOES NOT LICENSE: applying this to Readiness. Shrinking a readiness
    estimate toward a 91% base rate tells every data-poor student they will pass
    at the base rate, dressed as a prediction. That is the degenerate classifier
    section 1 forbids, and no amount of fitted k makes it not one.
    """
    if k < 0 or n < 0:
        raise ValueError("k and n must be non-negative")
    if k + n == 0:
        return prior
    return (n / (k + n)) * estimate + (k / (k + n)) * prior


def fit_shrinkage_constant(records, prior: float, grid=SHRINKAGE_K_GRID):
    """Choose k by held-out log loss. Appendix B item 7.

    `records` is a sequence of (estimate, n, held_out_probs_outcomes) triples,
    where the third element is the list of held-out binary outcomes that the
    shrunk estimate is used as a constant forecast for.

    Returns (best_k, [(k, log_loss), ...]) over the whole grid, so the report
    can show the curve rather than just the argmin -- a flat curve means k is
    not identified by this data, and that has to be visible.

    WHAT IT DOES NOT LICENSE: treating the argmin as "the" shrinkage constant.
    It is the argmin on the data supplied. On the synthetic cohort in `run.py`
    it is the argmin on data whose generating process was written by hand.
    """
    curve = []
    for k in grid:
        total = 0.0
        count = 0
        for estimate, n, outs in records:
            p = min(max(shrink_toward_prior(estimate, prior, n, k), 1e-15), 1 - 1e-15)
            for yi in outs:
                total += -math.log(p) if yi == 1 else -math.log(1.0 - p)
                count += 1
        curve.append((k, total / count if count else float("nan")))
    best = min(curve, key=lambda kv: kv[1])[0]
    return best, curve
