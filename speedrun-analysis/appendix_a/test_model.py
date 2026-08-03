# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tamper-check for the Appendix A analytic model.

    python3 speedrun-analysis/appendix_a/test_model.py

Every pre-registered number in BRAINLIFT.md Appendix A is asserted here, to
3 decimal places or better. This file exists for one purpose: IF SOMEONE EDITS
THE MODEL TO MAKE A RESULT COME OUT, THESE FAIL. The pre-registration is frozen;
a pre-registration that gets quietly reconciled with its own outcome is worth
less than no pre-registration at all.

Standard library only. No randomness -- these are closed-form identities, so a
failure is a real disagreement with the pre-registration, never a bad draw.

If a test here fails, the correct response is NOT to edit the expected value.
It is to establish which of the model or the pre-registration is wrong, and
record the correction in BRAINLIFT.md 8 with the original preserved -- the
same protocol used for the FSRS precedent error.
"""

from __future__ import annotations

import ast
import sys
import traceback
import types
from pathlib import Path

# Never let cached bytecode into the trust path. Python invalidates a source
# .pyc on (source mtime seconds, source size), so an edit that changes neither
# -- "P_LINEAR = 1.0" to "P_LINEAR = 2.0" is the same byte length -- is served
# from the stale cache within the same mtime second, and the tamper-check then
# passes on a tampered model. Observed in practice; it is not hypothetical.
#
# `sys.dont_write_bytecode` alone does NOT close this: it stops Python WRITING a
# .pyc, not READING one that some other tool (pytest, an IDE, a plain `import
# model`) already left in __pycache__. It is kept only so this file litters
# nothing. The actual fix is `load_model_from_source` below, which compiles the
# source text itself and never consults the cache at all.
sys.dont_write_bytecode = True

MODEL_PATH = Path(__file__).resolve().parent / "model.py"


def load_model_from_source() -> types.ModuleType:
    """Load model.py by compiling its SOURCE TEXT. Never reads a .pyc."""
    source = MODEL_PATH.read_text(encoding="utf-8")
    module = types.ModuleType("model")
    module.__file__ = str(MODEL_PATH)
    exec(compile(source, str(MODEL_PATH), "exec"), module.__dict__)
    sys.modules["model"] = module
    return module


m = load_model_from_source()


# ---------------------------------------------------------------------------
# assertion helpers
# ---------------------------------------------------------------------------


def close(actual: float, expected: float, places: int = 3) -> bool:
    """True if actual agrees with expected when rounded to `places` decimals."""
    return abs(actual - expected) < 0.5 * 10.0 ** (-places)


def eq(actual: float, expected: float, label: str, places: int = 3) -> None:
    if not close(actual, expected, places):
        raise AssertionError(
            f"{label}: pre-registered {expected!r}, model returned {actual!r} "
            f"(disagreement at {places} dp)"
        )


def pct(value: float, of: float) -> int:
    """Percentage, rounded to whole numbers, as the pre-registration reports it."""
    return int(round(100.0 * value / of))


# ---------------------------------------------------------------------------
# PRIMARY -- BRAINLIFT.md Appendix A, "Pre-registered main number", steps 9-15
# ---------------------------------------------------------------------------


def test_primary_derivation_steps() -> None:
    """Every intermediate of the primary derivation, not just the total."""
    a, c, p = 0.5, 2.0, 1.0
    eq(m.reps_relative(a, c), 0.75, "step 9: reps relative R", 4)
    eq(m.rep_deficit(a, c), 0.25, "step 9: rep deficit", 4)
    eq(m.congruent_share(a, c), 0.3333, "step 10: congruent share", 4)
    eq(m.delta_a(a, c, p), 4.0, "step 11: Delta_a (pp)", 4)
    eq(m.initial_accuracy(a, c, p), 81.0, "step 11: accuracy a (pp)", 4)
    eq(m.retention_gate(a, c, p), 0.84, "step 12: retention gate", 4)
    eq(m.transfer_gain_d(a, c, p), 0.0840, "step 13: gated congruency gain (d)", 4)
    eq(m.retention_penalty_d(a, c, p), 0.0232, "step 14: retention penalty (d)", 4)


def test_primary_net() -> None:
    """PRIMARY: net_d(alpha=0.5, c=2.0, p=1) = +0.0608 d."""
    eq(m.net_d(0.5, 2.0, 1.0), 0.0608, "PRIMARY net (d)", 4)


def test_primary_in_pp() -> None:
    """PRIMARY converted at sigma = 13 pp: +0.79 pp. sigma is the conversion factor."""
    eq(m.SIGMA, 13.0, "sigma (pp)", 6)
    eq(m.to_pp(m.net_d()), 0.79, "PRIMARY net converted at sigma = 13 pp", 2)


def test_primary_inside_preregistered_interval() -> None:
    """The primary must fall inside its own pre-registered interval +0.03 to +0.09 d."""
    net = m.net_d()
    assert 0.03 <= net <= 0.09, f"primary {net:+.4f} d outside pre-registered interval"


def test_primary_is_insulated_from_penalty_shape() -> None:
    """p cannot move the primary: Delta_a is calibrated AT alpha = 0.5, c = 2.0,
    so every shape agrees there by construction. p = 1, 2 and 3 alike -> +0.0608 d."""
    for p in (1.0, 1.5, 1.75, 2.0, 3.0):
        eq(m.net_d(p=p), 0.0608, f"primary at penalty shape p = {p}", 4)


def test_primary_conservatism_is_as_stated() -> None:
    """The fixed alpha = 0.5 comparison captures ~39% of the benefit at alpha*,
    a 2.6x understatement; ~92% if alpha* is interior at p = 2."""
    eq(m.alpha_star_net_d(), 0.158, "net at alpha* (d), c = 2.0, p = 1", 3)
    assert pct(m.net_d(), m.alpha_star_net_d()) == 39, "capture fraction at p = 1"
    eq(m.alpha_star_net_d() / m.net_d(), 2.6, "understatement factor", 1)
    assert pct(m.net_d(), m.alpha_star_net_d(p=2.0)) == 92, "capture fraction at p = 2"


# ---------------------------------------------------------------------------
# FALSIFIERS AND CONTROLS
# ---------------------------------------------------------------------------


def test_ceiling_tripwire() -> None:
    """Upper tripwire = 0.30 d = 3.9 pp at sigma = 13 pp. This is Delta_d itself:
    the effect if congruency were free and wholly allocated."""
    eq(m.CEILING_D, 0.30, "ceiling tripwire (d)", 4)
    eq(m.to_pp(m.CEILING_D), 3.9, "ceiling tripwire converted at sigma = 13 pp", 2)
    # And it is exactly attained in the degenerate free-congruency case,
    # which is what makes it the right number rather than an arbitrary one.
    eq(m.net_d(alpha=1.0, c=1.0), 0.30, "net at alpha = 1, c = 1 (free congruency, d)", 6)


def test_null_case() -> None:
    """NULL CONTROL: with Delta_d = 0 the model must predict -0.0232 d (-0.30 pp
    at sigma = 13 pp) -- the retention penalty standing alone."""
    null = m.net_d(delta_d=0.0)
    eq(null, -0.0232, "null case net (d)", 4)
    eq(m.to_pp(null), -0.30, "null case converted at sigma = 13 pp", 2)
    assert null < 0.0, "VOID: arm 1 wins under the null -- the harness is rigged"


def test_void_conditions_all_pass() -> None:
    """No pre-registered void condition may trigger on the frozen model."""
    for name, passed, detail in m.void_conditions():
        assert passed, f"VOID condition triggered: {name} -- {detail}"


def test_retention_floor_is_implemented() -> None:
    """Replacement implementation check (the inferred one was withdrawn): drive
    accuracy below the floor and transfer must be EXACTLY zero, not merely small."""
    passed, gain = m.gate_floor_check()
    assert passed, f"floor unimplemented -- gain below floor was {gain!r}, not 0.0"
    assert m.retention_gate(0.5, 2.0, delta_a_base=40.0) == 0.0, "gate must clamp at 0"
    assert m.net_d(delta_a_base=40.0) < 0.0, "below the floor only the penalty remains"


# ---------------------------------------------------------------------------
# HEADLINE DELIVERABLE -- decision boundary Delta_d*(c) at alpha = 0.5, p = 1
# ---------------------------------------------------------------------------


def test_decision_boundary() -> None:
    """Pre-registered boundary, in d, and as a percentage of the published 0.30."""
    expected = {1.0: (0.000, 0), 1.5: (0.043, 14), 2.0: (0.083, 28),
                2.5: (0.121, 40), 3.0: (0.157, 52)}
    for c, (star, share_pct) in expected.items():
        actual = m.boundary_delta_d_star(c=c)
        eq(actual, star, f"decision boundary Delta_d* at c = {c} (d)", 3)
        assert pct(actual, m.DELTA_D) == share_pct, (
            f"boundary at c = {c}: pre-registered {share_pct}% of published 0.30, "
            f"model gives {pct(actual, m.DELTA_D)}%"
        )


def test_boundary_is_sigma_free() -> None:
    """The boundary is reported in d and does not depend on sigma -- gain and
    penalty both scale by sigma and it cancels. The headline deliverable
    therefore does not depend on the one assumed number with no grounding."""
    before = [m.boundary_delta_d_star(c=c) for c in m.C_SWEEP]
    original = m.SIGMA
    try:
        m.SIGMA = 10.0
        mid = [m.boundary_delta_d_star(c=c) for c in m.C_SWEEP]
        m.SIGMA = 16.0
        after = [m.boundary_delta_d_star(c=c) for c in m.C_SWEEP]
    finally:
        m.SIGMA = original
    assert before == mid == after, "boundary moved with sigma -- it must not"


def test_delta_a_sensitivity_of_boundary() -> None:
    """Third sweep axis: Delta_a in {2, 4, 8} pp at c = 2.0. The crossing point
    rises FASTER than linearly because a larger loss both raises the penalty and
    shrinks the gate."""
    expected = {2.0: (0.038, 13), 4.0: (0.083, 28), 8.0: (0.205, 68)}
    for da, (star, share_pct) in expected.items():
        actual = m.boundary_delta_d_star(delta_a_base=da)
        eq(actual, star, f"boundary at Delta_a = {da} pp (d)", 3)
        assert pct(actual, m.DELTA_D) == share_pct, (
            f"Delta_a = {da} pp: pre-registered {share_pct}%, model gives "
            f"{pct(actual, m.DELTA_D)}%"
        )
    # Faster than linear: doubling Delta_a more than doubles the crossing point.
    b2, b4, b8 = (m.boundary_delta_d_star(delta_a_base=d) for d in (2.0, 4.0, 8.0))
    assert b4 > 2 * b2 and b8 > 2 * b4, "boundary must rise faster than linearly"


def test_primary_sensitivity_closed_form() -> None:
    """net(alpha = 0.5) = 0.100 - 0.0098 x Delta_a (d, at c = 2.0), reversing
    sign beyond Delta_a ~ 10.2 pp. The primary sees Delta_a's LEVEL directly."""
    intercept, slope = m.primary_sensitivity_intercept_slope()
    eq(intercept, 0.100, "primary sensitivity intercept (d)", 4)
    eq(slope, 0.0098, "primary sensitivity slope (d per pp)", 4)
    eq(m.primary_sign_flip_delta_a(), 10.204, "Delta_a at primary sign flip (pp)", 3)
    for da, net in ((2.0, 0.080), (4.0, 0.061), (6.0, 0.041), (8.0, 0.022)):
        eq(m.net_d(delta_a_base=da), net, f"primary at Delta_a = {da} pp (d)", 3)
    # The closed form must agree with the full model, not merely be plausible.
    for da in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0):
        eq(m.net_d(delta_a_base=da), intercept - slope * da,
           f"closed form vs full model at Delta_a = {da} pp", 9)


# ---------------------------------------------------------------------------
# SECONDARY RESULT -- optimal allocation alpha*
# ---------------------------------------------------------------------------


def test_alpha_star_is_a_corner_at_central_parameters() -> None:
    """Pre-registered: alpha* = 1.00 for ALL c in [1.5, 3.0] at Delta_a = 4 pp,
    floor = 60 pp, p = 1. A corner is a legitimate outcome of a correctly-gated
    model -- the void condition claiming otherwise was withdrawn as incorrect."""
    for i in range(15, 31):
        c = i / 10.0
        eq(m.alpha_star(c=c), 1.00, f"alpha* at c = {c}", 3)


def test_alpha_star_map_by_delta_a_and_cost() -> None:
    """Pre-registered alpha* map (floor 60 pp, p = 1), BRAINLIFT.md Appendix A."""
    expected = {
        4.0: (1.00, 1.00, 1.00, 1.00),
        6.0: (1.00, 1.00, 1.00, 1.00),
        8.0: (1.00, 0.70, 0.18, 0.01),
        10.0: (0.89, 0.30, 0.01, 0.01),
        12.0: (0.62, 0.07, 0.01, 0.01),
    }
    for da, row in expected.items():
        for c, want in zip((1.5, 2.0, 2.5, 3.0), row):
            eq(m.alpha_star(c=c, delta_a_base=da), want,
               f"alpha* at Delta_a = {da} pp, c = {c}", 3)
    # Pre-registered range across the full sweep: alpha* in [0.01, 1.00].
    seen = [m.alpha_star(c=c, delta_a_base=da)
            for da in expected for c in (1.5, 2.0, 2.5, 3.0)]
    assert min(seen) == 0.01 and max(seen) == 1.00, "alpha* range must be [0.01, 1.00]"


def test_alpha_star_map_by_penalty_shape() -> None:
    """Pre-registered alpha* map over penalty convexity p (c = 2.0, floor 60 pp).
    alpha* = 1.00 is a prediction of the ANALYTIC model and may not survive
    simulation -- it is the prediction in this appendix least expected to hold."""
    for p, want in ((1.0, 1.00), (1.5, 1.00), (1.75, 0.78), (2.0, 0.65), (3.0, 0.49)):
        eq(m.alpha_star(p=p), want, f"alpha* at penalty shape p = {p}", 3)
    # Delta_a at alpha = 1 for each shape, in pp -- the extrapolated penalty.
    for p, want in ((1.0, 8.0), (1.5, 11.3), (1.55, 11.7), (1.75, 13.5),
                    (2.0, 16.0), (3.0, 32.0)):
        eq(m.delta_a(1.0, 2.0, p), want, f"Delta_a at alpha = 1, p = {p} (pp)", 1)


def test_corner_break_thresholds() -> None:
    """The corner breaks under MILD convexity (p ~ 1.55, short of quadratic) or
    an implausibly high floor (>= ~72.1 pp)."""
    eq(m.corner_break_p(), 1.55, "penalty convexity p at which alpha* leaves 1.00", 2)
    eq(m.corner_break_floor(), 72.1, "floor (pp) at which alpha* leaves 1.00", 1)
    # Below each threshold the corner must still hold -- a one-sided check would
    # pass on a model that had lost the corner entirely.
    eq(m.alpha_star(p=1.54), 1.00, "corner must survive at p = 1.54", 3)
    eq(m.alpha_star(floor=72.0), 1.00, "corner must survive at floor = 72.0 pp", 3)


def test_net_at_alpha_star_by_shape() -> None:
    """Net at alpha* for each penalty shape, in d. See test_known_discrepancies
    for the one cell where the pre-registration's printed value is a rounding
    artefact rather than a model disagreement."""
    for p, want in ((1.0, 0.158), (1.5, 0.099), (2.0, 0.066), (3.0, 0.061)):
        eq(m.alpha_star_net_d(p=p), want, f"net at alpha*, p = {p} (d)", 3)


# ---------------------------------------------------------------------------
# PROVENANCE -- constants, and the superseded formulation
# ---------------------------------------------------------------------------


def test_frozen_constants() -> None:
    """The pre-registered inputs themselves. If these move, everything above is
    meaningless regardless of whether it still passes."""
    eq(m.DELTA_D, 0.30, "Delta_d (d)", 6)
    eq(m.SLOPE, 0.0058, "initial-accuracy slope (d per pp)", 6)
    eq(m.C_CENTRAL, 2.0, "cost multiplier c", 6)
    eq(m.ALPHA_PRIMARY, 0.5, "allocation alpha", 6)
    eq(m.DELTA_A_CENTRAL, 4.0, "Delta_a (pp)", 6)
    eq(m.CALIBRATION_DEFICIT, 0.25, "calibration deficit", 6)
    eq(m.P_LINEAR, 1.0, "penalty shape p", 6)
    eq(m.A0, 85.0, "baseline accuracy a0 (pp)", 6)
    eq(m.FLOOR, 60.0, "transfer floor (pp)", 6)
    eq(m.SIGMA, 13.0, "sigma (pp)", 6)
    assert m.C_SWEEP == (1.0, 1.5, 2.0, 2.5, 3.0), "cost sweep points"
    assert m.DELTA_A_SWEEP == (2.0, 4.0, 8.0), "Delta_a sweep points"
    # Delta_d is derived from the published pair, and is also the ceiling.
    eq(0.58 - 0.28, m.DELTA_D, "Delta_d from published 0.58 - 0.28", 6)
    eq(m.CEILING_D, m.DELTA_D, "ceiling is Delta_d itself", 6)


def test_frozen_constants_match_the_source_text_on_disk() -> None:
    """Assert the frozen constants against the BYTES OF model.py, not against an
    imported module -- so no import mechanism, cache or loader sits between the
    pre-registration and the check.

    This is the belt to `load_model_from_source`'s braces. A stale .pyc that
    validates on (mtime, size) can satisfy every other test in this file while
    the source on disk says something else; parsing the source text cannot be
    fooled that way. It also proves the loaded module and the file agree.
    """
    tree = ast.parse(MODEL_PATH.read_text(encoding="utf-8"))
    literals: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    literals[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError, TypeError):
                    continue  # e.g. CEILING_D = DELTA_D, a name not a literal

    expected = {
        "DELTA_D": 0.30, "SLOPE": 0.0058, "C_CENTRAL": 2.0, "ALPHA_PRIMARY": 0.5,
        "DELTA_A_CENTRAL": 4.0, "CALIBRATION_DEFICIT": 0.25, "P_LINEAR": 1.0,
        "A0": 85.0, "FLOOR": 60.0, "SIGMA": 13.0, "ALPHA_GRID_STEP": 0.01,
        "C_SWEEP": (1.0, 1.5, 2.0, 2.5, 3.0), "DELTA_A_SWEEP": (2.0, 4.0, 8.0),
    }
    for name, want in expected.items():
        assert name in literals, f"{name} is not a module-level literal in model.py"
        got = literals[name]
        assert got == want, (
            f"{name}: pre-registered {want!r}, model.py SOURCE TEXT says {got!r}"
        )
        assert getattr(m, name) == got, (
            f"{name}: loaded module has {getattr(m, name)!r} but the source text on "
            f"disk says {got!r} -- the model was NOT loaded from source"
        )


def test_alpha_star_ties_resolve_to_the_lower_alpha() -> None:
    """`alpha_star` documents that ties resolve to the LOWER alpha. Assert it on a
    genuine tie, so the strict `>` in the grid search cannot silently become `>=`.

    At c = 1.0 congruency is free (deficit = 0, so Delta_a = 0 and no penalty);
    with Delta_d = 0 there is no gain either, so net is exactly 0.0 at every
    alpha on the grid and the whole range is one tie.
    """
    assert m.net_d(0.01, 1.0, delta_d=0.0) == 0.0 == m.net_d(1.0, 1.0, delta_d=0.0), (
        "precondition: c = 1, Delta_d = 0 must be a flat tie across the grid"
    )
    eq(m.alpha_star(c=1.0, delta_d=0.0), 0.01, "tie must resolve to the lower alpha", 6)


def test_superseded_ungated_formulation() -> None:
    """The pre-Revision-3 additive model, retained for provenance. It is what
    produced the unwanted corner and motivated gating; it is NOT under test."""
    for alpha, share, da, net in (
        (0.25, 0.143, 2.0, 0.031),
        (0.50, 0.333, 4.0, 0.077),
        (0.75, 0.600, 6.0, 0.145),
        (1.00, 1.000, 8.0, 0.254),
    ):
        eq(m.congruent_share(alpha, 2.0), share, f"share at alpha = {alpha}", 3)
        eq(m.delta_a(alpha, 2.0), da, f"Delta_a at alpha = {alpha} (pp)", 3)
        eq(m.net_d_ungated(alpha), net, f"ungated net at alpha = {alpha} (d)", 3)
    # Gating multiplies the primary's congruency gain by 0.84 and leaves the
    # penalty untouched, moving the primary from +0.077 d to +0.061 d.
    eq(m.net_d_ungated(0.5), 0.0768, "ungated primary (d)", 4)
    eq(m.retention_gate(0.5, 2.0), 0.84, "gate applied to the primary", 4)


def test_congruent_share_is_convex_in_alpha() -> None:
    """Why the model corners: gain is linear in share, share is CONVEX in alpha,
    and the p = 1 penalty is exactly linear. Convex minus linear is convex, and
    a convex function on an interval maximizes at an endpoint."""
    h = 1e-4
    for alpha in (0.2, 0.4, 0.6, 0.8):
        second = (m.congruent_share(alpha + h, 2.0) - 2 * m.congruent_share(alpha, 2.0)
                  + m.congruent_share(alpha - h, 2.0)) / (h * h)
        assert second > 0, f"share must be convex at alpha = {alpha}, got {second}"
        # And the linear penalty's second derivative is identically zero.
        second_pen = (m.delta_a(alpha + h, 2.0) - 2 * m.delta_a(alpha, 2.0)
                      + m.delta_a(alpha - h, 2.0)) / (h * h)
        assert abs(second_pen) < 1e-4, f"p = 1 penalty must be exactly linear, got {second_pen}"


def test_known_discrepancies_in_the_pre_registration() -> None:
    """Two printed figures in BRAINLIFT.md Appendix A disagree with the frozen
    model. Neither is a model defect, and NEITHER MAY BE FIXED BY EDITING THE
    MODEL. They are recorded here so the disagreement is tracked rather than
    silently absorbed, and so they cannot drift further.

    (1) "Net at alpha*" for p = 1.75 is printed as 0.075 d; the model gives
        0.074458 d, which rounds to 0.074 d. alpha* = 0.78 itself matches
        exactly, so this is a reporting-precision artefact, not a divergence.

    (2) The sigma-sensitivity line reads "at sigma = 10 the prediction is
        +0.77 pp; at sigma = 16, +1.23 pp". Those are 0.077 d x sigma -- the
        PRE-GATING primary from before Revision 3. At the current +0.0608 d the
        conversions are +0.61 pp and +0.97 pp. Stale figures, not a live claim;
        the d result and the sigma-free boundary are unaffected.
    """
    eq(m.alpha_star(p=1.75), 0.78, "alpha* at p = 1.75 (matches pre-registration)", 3)
    eq(m.alpha_star_net_d(p=1.75), 0.074458, "net at alpha*, p = 1.75 (d)", 5)
    eq(m.to_pp(m.net_d(), sigma=10.0), 0.61, "primary at sigma = 10 pp", 2)
    eq(m.to_pp(m.net_d(), sigma=16.0), 0.97, "primary at sigma = 16 pp", 2)


# ---------------------------------------------------------------------------
# runner -- plain stdlib, no pytest required
# ---------------------------------------------------------------------------


def main() -> int:
    tests = [(name, obj) for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    print("=" * 78)
    print("APPENDIX A TAMPER-CHECK -- asserting the frozen pre-registration")
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
        print(f"{len(failures)} of {len(tests)} FAILED -- the model disagrees with the")
        print("pre-registration. Do NOT edit the expected values to match. Establish")
        print("which is wrong and record the correction in BRAINLIFT.md 8.")
        for name, detail in failures:
            print()
            print(f"  {name}:")
            print(f"    {detail}")
        return 1
    print(f"{len(tests)} of {len(tests)} passed -- every pre-registered number reproduced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
