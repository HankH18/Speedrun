# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix A analytic model -- the closed-form baseline for the thesis test.

WHAT THIS IS
------------
The pre-registered, closed-form data-generating process from BRAINLIFT.md
Appendix A ("Thesis test design"). It answers one question analytically:

    Under a fixed study-time budget, does a scheduler that trades retention
    practice for congruency-matched (transfer) practice beat one that
    maximizes retention alone?

WHAT THIS IS NOT
----------------
This is NOT the FSRS simulation. The analytic model has one hand-written line
standing in for the entire retention consequence of studying less
(`delta_a`, below), and that line is LINEAR IN ALPHA BY CONSTRUCTION. The FSRS
simulation -- a separate, later deliverable -- produces that penalty shape from
scheduling dynamics instead of asserting it. Divergence between the two is a
FINDING, not an error. See README.md.

FROZEN
------
Every constant below is pre-registered in BRAINLIFT.md Appendix A and must not
be edited to match a result. `test_model.py` asserts each pre-registered output
and exists specifically to fail if this file is tampered with.

UNITS -- stated because two different ones are in play
------------------------------------------------------
  d   effect size (Cohen's d). The pre-registered results live here.
  pp  percentage points of held-out novel-item accuracy. A CONVERSION ONLY,
      obtained by multiplying d by SIGMA. SIGMA is assumed, not literature-
      derived, so any pp figure silently encodes a guess and must name SIGMA.

DETERMINISM
-----------
There is no stochastic component anywhere in this module. Every result is a
closed-form evaluation, so re-running reproduces figures bit-for-bit without
seed control. The pre-registered seed-control requirement applies to the FSRS
simulation deliverable, which does draw randomly.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# LITERATURE-DERIVED CONSTANTS -- Pan & Rickard (2018), via BRAINLIFT.md 3.1
# ---------------------------------------------------------------------------

DELTA_D = 0.30
"""Congruency delta, in d. Published (BRAINLIFT.md 3.1): congruent transfer
d = 0.58 minus non-congruent transfer d = 0.28. This is the *entire* effect
available to the feature, which is why it is also the ceiling tripwire."""

SLOPE = 0.0058
"""Initial-accuracy moderator slope, in d per percentage point. Published
(BRAINLIFT.md 3.1). Converts a loss of initial retrieval accuracy (pp) into a
loss of transfer (d)."""

# ---------------------------------------------------------------------------
# ASSUMED / INFERRED CONSTANTS -- named so the sweep can attack them
# ---------------------------------------------------------------------------

C_CENTRAL = 2.0
"""Cost multiplier of a congruency-matched rep, dimensionless. ASSUMED.
A congruent rep costs c times a plain rep. Swept over [1.0, 3.0]; c = 2.0 is
the pre-registered central value and the headline slice of the boundary."""

C_SWEEP = (1.0, 1.5, 2.0, 2.5, 3.0)
"""Pre-registered cost-multiplier sweep points, dimensionless."""

ALPHA_PRIMARY = 0.5
"""Fraction of budget allocated to congruent practice, dimensionless.
FIXED BY DESIGN for the primary comparison -- the primary is a fixed-allocation
comparison, NOT an optimization. The optimization is the secondary result
(`alpha_star`), and the two must not be conflated."""

DELTA_A_CENTRAL = 4.0
"""Initial accuracy lost to the rep deficit, in pp, calibrated AT a 25% deficit.
INFERRED, not published -- the least-grounded magnitude in the derivation.
Pan & Rickard supply the slope relating initial accuracy to transfer; nothing in
the cited literature says how much accuracy a given cut in practice volume
costs. Swept over {2, 4, 8} pp as the third axis."""

DELTA_A_SWEEP = (2.0, 4.0, 8.0)
"""Pre-registered Delta_a robustness sweep, in pp."""

CALIBRATION_DEFICIT = 0.25
"""The rep deficit, dimensionless, at which DELTA_A_CENTRAL is calibrated.
This is the deficit produced by alpha = 0.5, c = 2.0. Every penalty SHAPE (p)
agrees at this point by construction, which is why the primary is insulated
from p but not from DELTA_A_CENTRAL."""

P_LINEAR = 1.0
"""Exponent of the retention penalty in the rep deficit, dimensionless.
p = 1 is PRE-REGISTERED and is the model's weakest assumption -- structural, not
merely numeric. The penalty is calibrated at alpha = 0.5 and extrapolated to
alpha = 1.0, which is exactly where the corner optimum sits. Verified
symbolically: deficit = alpha * (1 - 1/c), so the p = 1 penalty is exactly
linear in alpha (second derivative identically zero). p > 1 is convex."""

A0 = 85.0
"""Baseline initial retrieval accuracy, in pp. ASSUMED. Gate reference point."""

FLOOR = 60.0
"""Accuracy, in pp, below which transfer vanishes entirely. ASSUMED, derived
from BRAINLIFT.md 3.1's qualitative statement that transfer "disappears
entirely at particularly poor initial performance". Swept."""

SIGMA = 13.0
"""Between-learner SD of held-out novel-item accuracy, in pp. ASSUMED.
CONVERSION FACTOR ONLY -- it scales d to pp linearly and touches nothing else.
The decision boundary is sigma-free: gain and penalty both scale by sigma and
it cancels."""

CEILING_D = DELTA_D
"""Upper tripwire, in d. Delta_d itself: the effect if congruency were free and
wholly allocated. No cost-bearing design can exceed it, so a result above this
is a harness bug, not a discovery. See `void_conditions`."""

ALPHA_GRID_STEP = 0.01
"""Resolution of the alpha grid used for `alpha_star`, dimensionless.
The pre-registered alpha* range is [0.01, 1.00], i.e. a 100-point grid.
alpha = 0 is excluded: it is the arm-2 allocation, where net is identically 0."""


# ---------------------------------------------------------------------------
# THE MODEL
# ---------------------------------------------------------------------------


def reps_relative(alpha: float, c: float) -> float:
    """R -- total reps arm 1 completes, relative to arm 2. Dimensionless.

    R = (1 - alpha) + alpha / c

    Arm 1 spends fraction (1 - alpha) of its budget on plain reps, which cost 1
    each, and fraction alpha on congruent reps, which cost c each and therefore
    buy only alpha/c of them. R = 1 when c = 1 (congruency free) and falls as c
    rises. BRAINLIFT.md Appendix A, derivation step 9.
    """
    return (1.0 - alpha) + alpha / c


def rep_deficit(alpha: float, c: float) -> float:
    """The rep deficit arm 1 accepts relative to arm 2. Dimensionless.

    deficit = 1 - R.  At alpha = 0.5, c = 2.0 this is 0.25 -- a 25% deficit,
    the point at which Delta_a is calibrated.
    """
    return 1.0 - reps_relative(alpha, c)


def congruent_share(alpha: float, c: float) -> float:
    """Share of items actually practised that are congruency-matched. Dimensionless.

    share = (alpha / c) / R

    Note this is CONVEX in alpha (at c = 2 it is alpha / (2 - alpha), whose
    second derivative 4/(2 - alpha)^3 is positive). A convex gain racing a
    linear penalty is what produces the corner optimum at alpha* = 1.00.
    BRAINLIFT.md Appendix A, derivation step 10.
    """
    return (alpha / c) / reps_relative(alpha, c)


def delta_a(
    alpha: float,
    c: float,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
) -> float:
    """Initial retrieval accuracy lost to the rep deficit, in pp.

    Delta_a = delta_a_base * (deficit / 0.25) ** p

    Calibrated so that every shape p agrees at the 25% deficit (alpha = 0.5,
    c = 2.0), where it returns delta_a_base exactly. p = 1 is pre-registered
    and exactly linear in alpha; p > 1 is convex and is the shape FSRS dynamics
    are expected to produce (lapses reset stability rather than pausing it, so
    losses compound). p is NOT swept analytically as part of the primary -- the
    simulation replaces this line entirely.
    """
    return delta_a_base * (rep_deficit(alpha, c) / CALIBRATION_DEFICIT) ** p


def initial_accuracy(
    alpha: float,
    c: float,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
) -> float:
    """Arm 1's initial retrieval accuracy after paying the rep deficit, in pp.

    a = a0 - Delta_a.  BRAINLIFT.md Appendix A, derivation step 11.
    """
    return A0 - delta_a(alpha, c, p, delta_a_base)


def retention_gate(
    alpha: float,
    c: float,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    floor: float = FLOOR,
) -> float:
    """Multiplier, dimensionless in [0, 1], gating transfer on retention.

    gate = max(0, (a - floor) / (a0 - floor))

    A learner who abandons retention practice cannot transfer a fact they no
    longer retain. Added in Revision 3 of the pre-registration, AFTER the
    ungated model produced an unwanted corner -- the justification is recorded
    at length in BRAINLIFT.md Appendix A ("Gating the transfer channel").
    It specifies a moderator already declared (the 0.0058 d/pp slope from
    3.1) more completely by honouring the bound stated in the same sentence;
    it imports no new literature quantity.

    The max(0, .) clamp is load-bearing and is the pre-registered
    implementation check: drive accuracy below the floor and transfer must go
    to EXACTLY zero, not merely small. See `gate_floor_check`.
    """
    return max(0.0, (initial_accuracy(alpha, c, p, delta_a_base) - floor) / (A0 - floor))


def transfer_gain_d(
    alpha: float,
    c: float,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    floor: float = FLOOR,
    delta_d: float = DELTA_D,
) -> float:
    """Gated congruency gain, in d.

    gain = share * Delta_d * gate.  BRAINLIFT.md Appendix A, derivation step 13.
    """
    return (
        congruent_share(alpha, c)
        * delta_d
        * retention_gate(alpha, c, p, delta_a_base, floor)
    )


def retention_penalty_d(
    alpha: float,
    c: float,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
) -> float:
    """Transfer lost to the accuracy drop, in d.

    penalty = slope * Delta_a, where slope is in d/pp and Delta_a is in pp.
    BRAINLIFT.md Appendix A, derivation step 14.
    """
    return SLOPE * delta_a(alpha, c, p, delta_a_base)


def net_d(
    alpha: float = ALPHA_PRIMARY,
    c: float = C_CENTRAL,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    floor: float = FLOOR,
    delta_d: float = DELTA_D,
) -> float:
    """Arm 1 minus arm 2 on held-out novel-item accuracy, in d.

    net = share * Delta_d * gate  -  slope * Delta_a

    At the pre-registered point (alpha = 0.5, c = 2.0, p = 1, Delta_a = 4 pp,
    floor = 60 pp) this is +0.0608 d. BRAINLIFT.md Appendix A, derivation
    step 15.
    """
    return transfer_gain_d(alpha, c, p, delta_a_base, floor, delta_d) - retention_penalty_d(
        alpha, c, p, delta_a_base
    )


def net_d_ungated(
    alpha: float = ALPHA_PRIMARY,
    c: float = C_CENTRAL,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    delta_d: float = DELTA_D,
) -> float:
    """SUPERSEDED additive formulation, in d. Retained for provenance only.

    net = share * Delta_d - slope * Delta_a  (no retention gate)

    This is the pre-Revision-3 model. It is NOT the model under test and must
    not be used for any reported result; it exists so the documented reason for
    gating (BRAINLIFT.md Appendix A's alpha-vs-net additive table) stays
    reproducible and tamper-checked.
    """
    return congruent_share(alpha, c) * delta_d - retention_penalty_d(
        alpha, c, p, delta_a_base
    )


# ---------------------------------------------------------------------------
# DERIVED RESULTS
# ---------------------------------------------------------------------------


def to_pp(d: float, sigma: float = SIGMA) -> float:
    """Convert an effect size (d) to percentage points of accuracy (pp).

    pp = d * sigma. sigma is ASSUMED, so every caller must name it in output.
    """
    return d * sigma


def boundary_delta_d_star(
    c: float = C_CENTRAL,
    alpha: float = ALPHA_PRIMARY,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    floor: float = FLOOR,
) -> float:
    """The decision boundary Delta_d*(c), in d -- the headline deliverable.

    The real congruency effect at which arm 1's advantage crosses zero:

        share * Delta_d* * gate = slope * Delta_a
        =>  Delta_d* = slope * Delta_a / (share * gate)

    Above the boundary the feature pays; below it, it does not. This quantity
    is SIGMA-FREE -- gain and penalty both scale by sigma and it cancels --
    which is why it, rather than the pp point estimate, is the deliverable.
    Returns +inf where the gate has closed and no Delta_d can break even.
    """
    denom = congruent_share(alpha, c) * retention_gate(alpha, c, p, delta_a_base, floor)
    if denom <= 0.0:
        return float("inf")
    return retention_penalty_d(alpha, c, p, delta_a_base) / denom


def alpha_star(
    c: float = C_CENTRAL,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    floor: float = FLOOR,
    delta_d: float = DELTA_D,
) -> float:
    """Optimal allocation alpha*, dimensionless -- the SECONDARY result.

    Grid search over the pre-registered range alpha in [0.01, 1.00] at
    ALPHA_GRID_STEP resolution. Ties resolve to the lower alpha.

    alpha* = 1.00 (the corner) is the pre-registered prediction at the central
    parameters. A corner is a legitimate outcome of a correctly-gated model
    here -- the earlier void condition claiming otherwise was withdrawn as
    incorrect. Where the optimum lands is a RESULT, not a diagnostic.
    """
    steps = int(round(1.0 / ALPHA_GRID_STEP))
    best_alpha = ALPHA_GRID_STEP
    best_net = None
    for i in range(1, steps + 1):
        alpha = i / steps
        value = net_d(alpha, c, p, delta_a_base, floor, delta_d)
        if best_net is None or value > best_net:
            best_net = value
            best_alpha = alpha
    return best_alpha


def alpha_star_net_d(
    c: float = C_CENTRAL,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    floor: float = FLOOR,
    delta_d: float = DELTA_D,
) -> float:
    """Net benefit at alpha*, in d."""
    return net_d(alpha_star(c, p, delta_a_base, floor, delta_d), c, p, delta_a_base, floor, delta_d)


def corner_break_p(
    c: float = C_CENTRAL,
    delta_a_base: float = DELTA_A_CENTRAL,
    floor: float = FLOOR,
    step: float = 0.01,
    p_max: float = 3.0,
) -> float | None:
    """Smallest penalty convexity p at which alpha* leaves the corner. Dimensionless.

    Scans p upward from 1.00 at `step` resolution and returns the first p where
    alpha* < 1.00. Pre-registered answer: p ~ 1.55 -- mild convexity, well short
    of quadratic, is enough to break the corner. Returns None if the corner
    survives to p_max.
    """
    steps = int(round((p_max - 1.0) / step))
    for i in range(steps + 1):
        p = 1.0 + i * step
        if alpha_star(c, p, delta_a_base, floor) < 1.0:
            return round(p, 10)
    return None


def corner_break_floor(
    c: float = C_CENTRAL,
    p: float = P_LINEAR,
    delta_a_base: float = DELTA_A_CENTRAL,
    step: float = 0.1,
) -> float | None:
    """Lowest transfer floor at which alpha* leaves the corner, in pp.

    Scans the floor upward from the pre-registered 60 pp at `step` resolution
    and returns the first floor where alpha* < 1.00. Pre-registered answer:
    floor >= ~72.1 pp -- i.e. transfer would have to vanish for anyone below
    72% accuracy, which is not plausible. Returns None if the corner survives.
    """
    steps = int(round((A0 - FLOOR) / step))
    for i in range(steps):
        floor = FLOOR + i * step
        if alpha_star(c, p, delta_a_base, floor) < 1.0:
            return round(floor, 10)
    return None


def primary_sensitivity_intercept_slope() -> tuple[float, float]:
    """Closed form of the primary's dependence on Delta_a, at alpha = 0.5, c = 2.

    Returns (intercept in d, slope in d per pp) for

        net(alpha = 0.5) = intercept - slope * Delta_a

    Pre-registered as net = 0.100 - 0.0098 * Delta_a. Two channels carry the
    sensitivity: the direct penalty (0.0058, 59%) and the shrinking retention
    gate (0.0040, 41%). The primary is insulated from the penalty's SHAPE (p)
    but not at all from its LEVEL (Delta_a).
    """
    share = congruent_share(ALPHA_PRIMARY, C_CENTRAL)
    intercept = share * DELTA_D  # gain when Delta_a = 0, i.e. gate = 1
    gate_channel = share * DELTA_D / (A0 - FLOOR)  # d lost per pp via the gate
    return intercept, gate_channel + SLOPE


def primary_sign_flip_delta_a() -> float:
    """Delta_a, in pp, at which the primary reverses sign. Pre-registered ~10.2 pp.

    If FSRS's true accuracy loss from a 25% rep deficit exceeds this, the
    feature LOSES at alpha = 0.5 and the primary prediction is wrong.
    """
    intercept, slope = primary_sensitivity_intercept_slope()
    return intercept / slope


# ---------------------------------------------------------------------------
# VOID CONDITIONS AND IMPLEMENTATION CHECKS
# ---------------------------------------------------------------------------


def gate_floor_check() -> tuple[bool, float]:
    """Pre-registered implementation check for the retention floor.

    The withdrawn void condition inferred the floor's presence from where the
    optimum landed, which does not follow. This is its replacement: drive
    accuracy below the floor and confirm the transfer gain is EXACTLY zero,
    not merely small. If it is not, the floor is unimplemented and the run is
    VOID.

    Driven here with an absurd Delta_a of 40 pp, which puts accuracy at 45 pp,
    well below the 60 pp floor. Returns (passed, observed gain in d).
    """
    gain = transfer_gain_d(ALPHA_PRIMARY, C_CENTRAL, P_LINEAR, delta_a_base=40.0)
    return gain == 0.0, gain


def void_conditions() -> list[tuple[str, bool, str]]:
    """Evaluate every pre-registered void condition.

    Returns a list of (name, passed, detail). A False in any row means the
    entire result is VOID -- not merely weakened.
    """
    rows: list[tuple[str, bool, str]] = []

    # 1. Null case: with Delta_d = 0, arm 1 must NOT win. If it does, the
    #    harness is rigged and the entire result is void.
    null = net_d(delta_d=0.0)
    rows.append(
        (
            "Null case (Delta_d = 0): arm 1 must not beat arm 2",
            null <= 0.0,
            f"net = {null:+.4f} d ({to_pp(null):+.2f} pp at sigma = {SIGMA:.0f} pp)",
        )
    )

    # 2. Ceiling tripwire: no cost-bearing design can exceed Delta_d itself.
    #    Checked at the primary and at the best allocation over the whole
    #    cost sweep. c = 1.0 is included deliberately: it is the degenerate
    #    free-congruency case, where alpha* = 1.00 attains exactly 0.30 d --
    #    the tripwire's own definition, and evidence it is set correctly.
    largest = max([net_d(), alpha_star_net_d()] + [alpha_star_net_d(c=c) for c in C_SWEEP])
    rows.append(
        (
            f"Ceiling tripwire: no result may exceed {CEILING_D:.2f} d",
            largest <= CEILING_D,
            f"largest net over the sweep = {largest:+.4f} d "
            f"({to_pp(largest):+.2f} pp at sigma = {SIGMA:.0f} pp)",
        )
    )

    # 3. Retention floor implemented: transfer must go to exactly zero below it.
    passed, gain = gate_floor_check()
    rows.append(
        (
            "Retention floor implemented (gain is exactly 0 below the floor)",
            passed,
            f"gain at accuracy {A0 - 40.0:.0f} pp (floor {FLOOR:.0f} pp) = {gain:.6f} d",
        )
    )

    return rows
