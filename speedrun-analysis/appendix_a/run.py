# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix A analytic harness -- single entry point.

    python3 speedrun-analysis/appendix_a/run.py

Prints the pre-registered analytic baseline: the primary result, the null-case
control, the void-condition checks, the two-dimensional decision boundary, the
Delta_a sensitivity, and the alpha* map. Standard library only. Deterministic --
no randomness anywhere, so no seeds are needed to reproduce these figures.

Every number below is labelled d (effect size) or pp (percentage points of
held-out novel-item accuracy). pp figures are a CONVERSION at an assumed sigma,
named at every use.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import model as m  # noqa: E402


WIDTH = 78


def rule(char: str = "-") -> str:
    return char * WIDTH


def heading(text: str) -> None:
    print()
    print(rule("="))
    print(text)
    print(rule("="))


def sub(text: str) -> None:
    print()
    print(text)
    print(rule())


def pp(d: float) -> str:
    """Format an effect size as its pp conversion, always naming sigma."""
    return f"{m.to_pp(d):+.2f} pp at sigma = {m.SIGMA:.0f} pp"


def header() -> None:
    print(rule("="))
    print("APPENDIX A -- ANALYTIC BASELINE (closed form)")
    print(rule("="))
    print("Pre-registration : BRAINLIFT.md, Appendix A -- FROZEN, do not edit to match")
    print("                   results. test_model.py fails if the model is tampered with.")
    print("Status           : this is the ANALYTIC baseline, NOT the FSRS simulation.")
    print("                   The FSRS run is a separate, later deliverable; it PRODUCES")
    print("                   the retention-penalty shape that this file ASSERTS.")
    print("                   Divergence between the two is a FINDING, not an error.")
    print("Determinism      : no stochastic component; closed-form evaluation only, so")
    print("                   no seeds are required and reruns are bit-for-bit identical.")
    print("                   Seed control applies to the FSRS deliverable, not to this.")
    print("Units            : d  = effect size (the pre-registered results live here)")
    print(f"                   pp = percentage points, a CONVERSION at sigma = {m.SIGMA:.0f} pp")
    print("                        (sigma is ASSUMED, not literature-derived)")


def parameters() -> None:
    sub("PRE-REGISTERED PARAMETERS")
    rows = [
        ("Congruency delta  Delta_d", f"{m.DELTA_D:.2f} d", "Published (Pan & Rickard, 3.1)"),
        ("Initial-accuracy slope", f"{m.SLOPE:.4f} d/pp", "Published (Pan & Rickard, 3.1)"),
        ("Cost multiplier  c", f"{m.C_CENTRAL:.1f} x", "Assumed; swept [1.0, 3.0]"),
        ("Allocation  alpha", f"{m.ALPHA_PRIMARY:.2f}", "FIXED by design for the primary"),
        ("Accuracy lost  Delta_a", f"{m.DELTA_A_CENTRAL:.1f} pp", "Inferred; swept {2, 4, 8} pp"),
        ("Penalty shape  p", f"{m.P_LINEAR:.1f}", "Linear; weakest assumption"),
        ("Baseline accuracy  a0", f"{m.A0:.0f} pp", "Assumed; gate reference point"),
        ("Transfer floor", f"{m.FLOOR:.0f} pp", "Assumed, from 3.1's qualitative bound"),
        ("Between-learner SD  sigma", f"{m.SIGMA:.0f} pp", "Assumed; CONVERSION FACTOR ONLY"),
    ]
    print(f"{'Quantity':<28}{'Value':>14}   {'Grounding'}")
    for name, value, source in rows:
        print(f"{name:<28}{value:>14}   {source}")


def primary() -> None:
    heading("PRIMARY RESULT -- arm 1 minus arm 2 on held-out novel-item accuracy")
    a, c, p = m.ALPHA_PRIMARY, m.C_CENTRAL, m.P_LINEAR
    print(f"Fixed allocation alpha = {a:.2f}, c = {c:.1f}, Delta_a = {m.DELTA_A_CENTRAL:.0f} pp, "
          f"p = {p:.0f}, floor = {m.FLOOR:.0f} pp.")
    print("This is a FIXED-ALLOCATION comparison, not an optimization. It answers")
    print("'does spending half the budget on congruent practice beat spending none?'")
    print("It does NOT answer what the best allocation is -- that is alpha*, below.")

    sub("Derivation, step by step")
    print(f"  reps relative to arm 2   R      = {m.reps_relative(a, c):.4f}      (dimensionless)")
    print(f"  rep deficit              1 - R  = {m.rep_deficit(a, c):.4f}      (dimensionless)")
    print(f"  congruent share of items share  = {m.congruent_share(a, c):.4f}      (dimensionless)")
    print(f"  accuracy lost            Delta_a = {m.delta_a(a, c, p):.4f} pp")
    print(f"  accuracy after deficit   a      = {m.initial_accuracy(a, c, p):.4f} pp")
    print(f"  retention gate           gate   = {m.retention_gate(a, c, p):.4f}      (dimensionless)")
    print(f"  congruency gain, gated          = {m.transfer_gain_d(a, c, p):+.4f} d   ({pp(m.transfer_gain_d(a, c, p))})")
    print(f"  retention penalty               = {-m.retention_penalty_d(a, c, p):+.4f} d   ({pp(-m.retention_penalty_d(a, c, p))})")

    net = m.net_d()
    sub("PRE-REGISTERED PRIMARY")
    print(f"  net = {net:+.4f} d        ({pp(net)})")
    print(f"  pre-registered interval: +0.03 to +0.09 d  "
          f"(+{m.to_pp(0.03):.1f} to +{m.to_pp(0.09):.1f} pp at sigma = {m.SIGMA:.0f} pp)")

    at_star = m.alpha_star_net_d()
    star = m.alpha_star()
    sub("The primary is deliberately conservative -- stated in advance, not after")
    print(f"  net at alpha* = {star:.2f} would be {at_star:+.4f} d ({pp(at_star)}),")
    print(f"  so the fixed alpha = 0.50 comparison captures {100 * net / at_star:.0f}% of the")
    print(f"  achievable benefit -- a {at_star / net:.1f}x understatement of the feature.")
    net_p2 = m.alpha_star_net_d(p=2.0)
    print(f"  That handicap shrinks sharply if alpha* is interior: at p = 2.0, alpha* = "
          f"{m.alpha_star(p=2.0):.2f}")
    print(f"  and the fixed comparison captures {100 * net / net_p2:.0f}%.")


def null_case() -> None:
    heading("REQUIRED CONTROL -- the null case (Delta_d = 0)")
    null = m.net_d(delta_d=0.0)
    print("Remove the congruency effect entirely and rerun. Arm 1 still pays the")
    print("allocation cost while receiving no benefit, so the sharper pre-registered")
    print("prediction is a small DISADVANTAGE -- the retention penalty standing alone.")
    print()
    print(f"  net under the null = {null:+.4f} d        ({pp(null)})")
    print()
    print("  If arm 1 WINS under the null, the harness is rigged and the entire")
    print("  result is VOID -- not merely weakened. This check is reported whether")
    print("  or not the main result is favourable.")


def voids() -> None:
    heading("VOID CONDITIONS")
    print("A failure in any row voids the entire result. Note the withdrawn condition:")
    print("'a corner optimum at alpha = 1.0 means the harness failed' does NOT follow --")
    print("a correctly-gated model corners at these parameters. It is replaced by a")
    print("direct implementation check of the floor.")
    print()
    all_pass = True
    for name, passed, detail in m.void_conditions():
        flag = "PASS" if passed else "VOID"
        all_pass = all_pass and passed
        print(f"  [{flag}] {name}")
        print(f"         {detail}")
    print()
    print(f"  Overall: {'no void condition triggered' if all_pass else 'RESULT IS VOID'}")


def boundary() -> None:
    heading("HEADLINE DELIVERABLE -- decision boundary Delta_d*(c)")
    print("The locus where arm 1's advantage crosses zero, swept over the cost")
    print("multiplier c in [1.0, 3.0] at fixed alpha = 0.50. Above the boundary the")
    print("feature pays; below it, it does not. Reported in d and SIGMA-FREE: gain")
    print("and penalty both scale by sigma, so it cancels.")
    print()
    print(f"{'c':>6}  {'rep deficit':>12}  {'Delta_a':>10}  {'Delta_d* (d)':>13}  "
          f"{'% of published 0.30':>20}")
    print(rule())
    for c in m.C_SWEEP:
        star = m.boundary_delta_d_star(c=c)
        deficit = m.rep_deficit(m.ALPHA_PRIMARY, c)
        da = m.delta_a(m.ALPHA_PRIMARY, c)
        mark = "  <- headline slice" if c == m.C_CENTRAL else ""
        print(f"{c:>6.1f}  {100 * deficit:>11.0f}%  {da:>7.1f} pp  {star:>13.3f}  "
              f"{100 * star / m.DELTA_D:>19.0f}%{mark}")
    print()
    print("Read as a whole: if congruency-matched practice costs twice a plain rep,")
    print("the real congruency effect must be at least ~28% of Pan & Rickard's")
    print("published estimate for the feature to pay for itself -- rising to ~52%,")
    print("more than half, if it costs three times as much.")


def delta_a_sensitivity() -> None:
    heading("THIRD AXIS -- Delta_a robustness sweep at c = 2.0")
    print("Delta_a is the least-grounded quantity in the derivation: INFERRED, not")
    print("published. The crossing point rises FASTER THAN LINEARLY in Delta_a under")
    print("gating, because a larger retention loss both raises the penalty and")
    print("shrinks the gate.")
    print()
    print(f"{'Delta_a':>10}  {'Delta_d* (d)':>13}  {'% of published':>15}  {'primary net (d)':>16}")
    print(rule())
    for da in m.DELTA_A_SWEEP:
        star = m.boundary_delta_d_star(delta_a_base=da)
        net = m.net_d(delta_a_base=da)
        mark = "  <- pre-registered" if da == m.DELTA_A_CENTRAL else ""
        print(f"{da:>7.0f} pp  {star:>13.3f}  {100 * star / m.DELTA_D:>14.0f}%  "
              f"{net:>+16.4f}{mark}")

    intercept, slope = m.primary_sensitivity_intercept_slope()
    flip = m.primary_sign_flip_delta_a()
    print()
    print("The primary is insulated from the penalty's SHAPE (p) but NOT its LEVEL:")
    print(f"  net(alpha = 0.50) = {intercept:.4f} - {slope:.4f} x Delta_a   "
          f"(d, at c = 2.0, Delta_a in pp)")
    print(f"  sign flip at Delta_a = {flip:.3f} pp")
    print()
    print("  In simulation FSRS DETERMINES the real accuracy loss from a 25% rep")
    print("  deficit -- it is an output of scheduling dynamics, not an input. If it")
    print(f"  exceeds {flip:.1f} pp, the primary reverses sign and the feature loses at")
    print("  alpha = 0.50. A divergent simulated primary is therefore a finding about")
    print("  the retention cost of studying less, to be back-calculated into an")
    print("  implied Delta_a and reported -- not diagnosed as a defect.")


def alpha_star_map() -> None:
    heading("SECONDARY RESULT -- the optimal allocation alpha*")
    print("This is the result that actually answers the allocation question; the")
    print("primary holds alpha fixed and cannot. Grid search over the pre-registered")
    print(f"range alpha in [0.01, 1.00] at {m.ALPHA_GRID_STEP} resolution (dimensionless).")

    sub(f"alpha* at the pre-registered penalty shape p = 1.0, floor = {m.FLOOR:.0f} pp")
    print(f"{'Delta_a at alpha=0.5':>21}  {'c = 1.5':>9}  {'c = 2.0':>9}  {'c = 2.5':>9}  "
          f"{'c = 3.0':>9}")
    print(rule())
    for da in (4.0, 6.0, 8.0, 10.0, 12.0):
        cells = "  ".join(f"{m.alpha_star(c=c, delta_a_base=da):>9.2f}" for c in (1.5, 2.0, 2.5, 3.0))
        mark = "  <- pre-registered" if da == m.DELTA_A_CENTRAL else ""
        print(f"{da:>18.0f} pp  {cells}{mark}")
    print()
    print(f"At the central parameters alpha* = {m.alpha_star():.2f} -- the CORNER, for every")
    print("c in [1.5, 3.0]. Predicting a corner is a real, falsifiable prediction. The")
    print("honest reading is not 'the feature is spectacular' but 'under these")
    print("assumptions the model says go all-in, and the assumptions are doing most of")
    print("that work' -- which is why the boundary, not this point estimate, is the")
    print("deliverable.")

    sub("Sensitivity of alpha* to the penalty SHAPE p (c = 2.0, floor = 60 pp)")
    print("The corner survives only because a convex gain races a LINEAR penalty. The")
    print("penalty is calibrated at alpha = 0.50 and extrapolated to alpha = 1.00 --")
    print("the prediction is made at the point furthest from its own calibration.")
    print()
    print(f"{'p':>6}  {'Delta_a at alpha=1':>19}  {'alpha*':>8}  {'net at alpha* (d)':>18}")
    print(rule())
    for p in (1.0, 1.5, 1.75, 2.0, 3.0):
        star = m.alpha_star(p=p)
        print(f"{p:>6.2f}  {m.delta_a(1.0, m.C_CENTRAL, p):>16.1f} pp  {star:>8.2f}  "
              f"{m.alpha_star_net_d(p=p):>+18.4f}")

    p_break = m.corner_break_p()
    floor_break = m.corner_break_floor()
    print()
    print(f"  Corner breaks at p >= {p_break:.2f} (dimensionless) -- MILD convexity, well")
    print("  short of quadratic, is sufficient.")
    print(f"  Corner breaks at floor >= {floor_break:.1f} pp -- transfer would have to vanish")
    print("  for anyone below that accuracy, which is not plausible.")
    print()
    print("  So gating changes the magnitudes but does not by itself make the")
    print("  allocation question interior. alpha* = 1.00 is a prediction of the")
    print("  ANALYTIC model, not of the system under test. It is the prediction in")
    print("  this appendix I expect least to hold.")


def footer() -> None:
    heading("WHAT THIS BASELINE DOES AND DOES NOT ESTABLISH")
    print("Everything above is closed form. Its penalty shape is ASSERTED; the FSRS")
    print("simulation's will be PRODUCED -- from spacing intervals, forgetting between")
    print("reviews, lapses resetting stability, and per-card gating accumulating over")
    print("simulated time. Pre-registered disposition, so it cannot be chosen later:")
    print()
    print("  * These figures are a pre-registered BASELINE, not a prediction the")
    print("    simulation is expected to reproduce. They exist to be compared against.")
    print("  * Divergence between simulated alpha* and the analytic alpha* = 1.00 is a")
    print("    REPORTABLE FINDING, not an error. It must not be 'corrected' toward the")
    print("    algebra.")
    print("  * If the simulation merely reproduces the algebra, say so plainly. A null")
    print("    finding about one's own added machinery is still a finding.")
    print("  * No claim of student efficacy is made anywhere here, and none may be")
    print("    inferred. This tests whether the mechanism COULD work given the")
    print("    published effect sizes hold -- it is not evidence that it works in")
    print("    humans, and cannot become such evidence by being run more carefully.")
    print()
    print(rule("="))
    print("Tamper-check: python3 speedrun-analysis/appendix_a/test_model.py")
    print(rule("="))


def main() -> int:
    header()
    parameters()
    primary()
    null_case()
    voids()
    boundary()
    delta_a_sensitivity()
    alpha_star_map()
    footer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
