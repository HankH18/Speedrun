# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix B gates -- accept-only-if-better, implemented at three layers.

WHAT THIS IS
------------
BRAINLIFT.md section 7 replaced every asserted numeric floor with one rule
borrowed from upstream (`rslib/src/scheduler/fsrs/params.rs:156`):

    if current_log_loss <= optimized_log_loss {
        params = current_params.to_vec();   // keep what you had
    }

Fit freely, then throw the fit away unless it beats the incumbent on log loss.
Speedrun adopts this as the primary gate for all three scores. Standard library
only; every decision below is a pure function of the numbers passed in.

THE THREE LAYERS DO NOT COLLAPSE INTO ONE FUNCTION, AND THAT IS THE CONTENT
---------------------------------------------------------------------------
The mechanism is identical in all three cases. What differs is WHAT the model is
validated against and AT WHICH LAYER, and BRAINLIFT.md section 7 says in terms
that collapsing the three rows is the error its table exists to prevent:

    Memory       per-student   vs the incumbent memory model (the student's own
                               FSRS parameters, or the shipped defaults)
                               held-out unit: that student's own later reviews
    Performance  per-student   vs the topic prior (what we would say knowing
                               nothing about this student)
                               held-out unit: that student's own later items
    Readiness    MODEL-LEVEL   vs the base-rate null (a constant at the cohort
                               pass rate), over HELD-OUT STUDENTS
                               plus a per-student abstention rule on top

Why Readiness cannot share the layer: a student sits Step 1 once, and the
outcome arrives after the app has stopped being useful to them. There is no
per-student held-out set to validate against, so validation moves up a layer to
the cohort -- and a cohort-level result licenses a statement about the MODEL,
never about this student. That is why the per-student abstention rule survives
there and only there.

This module therefore exposes three separate entry points with STRUCTURALLY
DIFFERENT ARGUMENTS -- `memory_gate` and `performance_gate` take one student's
held-out outcomes; `readiness_gate` takes a cohort plus that student's coverage
and component decisions -- and `readiness_gate` returns a DIFFERENT TYPE. You
cannot pass readiness data to `memory_gate` by accident, and you cannot treat a
readiness decision as a per-student one, because it is not the same object.
`test_appendix_b.py` asserts all of this.

WHAT A PASSING GATE LICENSES
----------------------------
"On this held-out set, this model beat that named comparator on log loss." That
is all. It is a RELATIVE test: a model can win it while being badly calibrated
in absolute terms, which is why `sanity_gate` exists as a second, absolute check
and why BRAINLIFT.md section 7 says Speedrun needs both.
"""

from __future__ import annotations

from dataclasses import dataclass

from metrics import log_loss, log_loss_value

REPORT = "REPORT"
WITHHOLD = "WITHHOLD"

LAYER_PER_STUDENT = "per-student"
LAYER_MODEL = "model-level (held-out students)"

UNIT_STUDENT_REVIEWS = "the student's own later reviews"
UNIT_STUDENT_ITEMS = "the student's own later scored items"
UNIT_HELD_OUT_STUDENTS = "held-out students"

COMPARATOR_INCUMBENT = "incumbent memory model (their FSRS params, or shipped defaults)"
COMPARATOR_TOPIC_PRIOR = "topic prior (population performance on that topic)"
COMPARATOR_BASE_RATE_NULL = "base-rate null (constant at the cohort pass rate)"


# ---------------------------------------------------------------------------
# the shared primitive -- shared BECAUSE the mechanism is genuinely the same
# ---------------------------------------------------------------------------


def _beats_on_log_loss(candidate_probs, comparator_probs, outcomes):
    """Return (candidate_ll, comparator_ll, candidate_wins, clamped).

    Strict inequality, matching upstream: `if current_log_loss <= optimized`
    keeps the incumbent, so a TIE GOES TO THE INCUMBENT. That asymmetry is
    deliberate and is inherited rather than invented -- a new model must earn
    its place, and equal evidence is not earning it.

    This is private on purpose. It is the one piece of arithmetic the three
    layers share; exporting it would invite a caller to make the layer decision
    themselves, which is the collapse this module exists to prevent.
    """
    if not outcomes:
        raise ValueError("no held-out outcomes -- the gate cannot run on an empty set")
    cand_ll, cand_clamped = log_loss(candidate_probs, outcomes)
    comp_ll, comp_clamped = log_loss(comparator_probs, outcomes)
    return cand_ll, comp_ll, cand_ll < comp_ll, cand_clamped + comp_clamped


@dataclass(frozen=True)
class GateResult:
    """Outcome of a PER-STUDENT accept-only-if-better test.

    Returned by `memory_gate` and `performance_gate` only. Readiness returns
    `ReadinessDecision`, a different type, for the reason in the module
    docstring.
    """

    score: str
    student_id: str
    layer: str
    comparator: str
    held_out_unit: str
    n_held_out: int
    candidate_log_loss: float
    comparator_log_loss: float
    decision: str
    reason: str
    clamped: int = 0

    @property
    def margin(self) -> float:
        """comparator_ll - candidate_ll, in nats. Positive means the candidate won.

        DOES NOT LICENSE a significance claim. Nothing here computes a standard
        error, and on a 40-review held-out set a margin of 0.01 nats is noise.
        `run.py` reports the margin distribution rather than any single margin.
        """
        return self.comparator_log_loss - self.candidate_log_loss

    @property
    def reports(self) -> bool:
        return self.decision == REPORT


def memory_gate(
    student_id: str,
    candidate_probs,
    incumbent_probs,
    later_review_outcomes,
) -> GateResult:
    """PER-STUDENT gate for the Memory score. BRAINLIFT.md section 7, row 1.

    Candidate: the model fitted on this student's own history (in the shipped
    app, their optimised FSRS parameters).
    Comparator: the INCUMBENT memory model -- the parameters they already had,
    or the shipped defaults if they have none.
    Held out: this student's own LATER reviews. Later, not random: reviews of
    the same card are not independent, so a random split leaks.

    LICENSES: "for this student, the fitted model predicted their later reviews
    better than the incumbent did." That is a per-student claim and it is the
    strongest thing this project can say about Memory.
    DOES NOT LICENSE: anything about a different student, or about the absolute
    quality of either model -- see `sanity_gate`.
    """
    cand_ll, comp_ll, wins, clamped = _beats_on_log_loss(
        candidate_probs, incumbent_probs, later_review_outcomes
    )
    return GateResult(
        score="Memory",
        student_id=student_id,
        layer=LAYER_PER_STUDENT,
        comparator=COMPARATOR_INCUMBENT,
        held_out_unit=UNIT_STUDENT_REVIEWS,
        n_held_out=len(list(later_review_outcomes)),
        candidate_log_loss=cand_ll,
        comparator_log_loss=comp_ll,
        decision=REPORT if wins else WITHHOLD,
        reason=(
            "fitted model beat the incumbent on this student's later reviews"
            if wins
            else "fitted model did not beat the incumbent; the incumbent is kept "
            "and no personalised Memory score is reported"
        ),
        clamped=clamped,
    )


def performance_gate(
    student_id: str,
    candidate_probs,
    topic_prior_probs,
    later_item_outcomes,
) -> GateResult:
    """PER-STUDENT gate for the Performance score. BRAINLIFT.md section 7, row 2.

    Same layer as Memory and a DIFFERENT COMPARATOR: the topic prior, i.e. what
    the population does on that topic, which is what we would say knowing
    nothing about this student. Beating your own incumbent (Memory) and beating
    the impersonal prior (Performance) are different achievements, and the two
    gates are separate functions so that no caller can substitute one for the
    other and report the wrong claim.

    LICENSES: "for this student, a personal performance model beat the
    impersonal one on their later scored items."
    DOES NOT LICENSE: any readiness statement. Performance is DOK 2/3 item
    accuracy; readiness is a pass probability, and combining components into
    something that looks like a third score is exactly what POV 2's falsifier
    (4) forbids doing when the readiness model itself fails.
    """
    cand_ll, comp_ll, wins, clamped = _beats_on_log_loss(
        candidate_probs, topic_prior_probs, later_item_outcomes
    )
    return GateResult(
        score="Performance",
        student_id=student_id,
        layer=LAYER_PER_STUDENT,
        comparator=COMPARATOR_TOPIC_PRIOR,
        held_out_unit=UNIT_STUDENT_ITEMS,
        n_held_out=len(list(later_item_outcomes)),
        candidate_log_loss=cand_ll,
        comparator_log_loss=comp_ll,
        decision=REPORT if wins else WITHHOLD,
        reason=(
            "personal model beat the topic prior on this student's later items"
            if wins
            else "personal model did not beat the topic prior; no personalised "
            "Performance score is reported"
        ),
        clamped=clamped,
    )


# ---------------------------------------------------------------------------
# Readiness -- a different layer, and therefore a different type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelLevelResult:
    """Outcome of the MODEL-LEVEL readiness test over held-out students.

    Deliberately NOT a `GateResult`: this object carries no `student_id`,
    because it cannot say anything about a student. Attempting to read one off
    it is a type error rather than a subtle mistake.
    """

    layer: str
    comparator: str
    held_out_unit: str
    n_students: int
    model_log_loss: float
    null_log_loss: float
    null_rate: float
    decision: str
    reason: str

    @property
    def margin(self) -> float:
        return self.null_log_loss - self.model_log_loss

    @property
    def model_is_publishable(self) -> bool:
        return self.decision == REPORT


def readiness_model_gate(
    cohort_probs,
    cohort_outcomes,
    null_rate: float,
) -> ModelLevelResult:
    """MODEL-LEVEL accept-only-if-better for Readiness. BRAINLIFT.md Appendix B item 3.

    Does a readiness model beat a CONSTANT predictor at the cohort pass rate, on
    HELD-OUT STUDENTS? This is POV 2's falsifier (4), and BRAINLIFT.md commits in
    advance to what a negative result means:

        "It would mean this project can measure Memory and Performance and
        cannot measure Readiness, and the correct response is to ship two scores
        and say so -- not to relax the gate, not to blend the components into
        something that looks like a third score, and not to fall back on the
        base rate while calling it a prediction."

    `null_rate` must come from the TRAINING split, never from `cohort_outcomes`.
    A null fitted on the evaluation outcomes is an oracle.

    LICENSES: "the readiness model beat / did not beat the base-rate null on
    these held-out students."
    DOES NOT LICENSE: showing any individual student a number. That decision is
    `readiness_student_abstention`, and it is a separate layer.
    """
    outs = list(cohort_outcomes)
    probs = list(cohort_probs)
    if len(outs) != len(probs):
        raise ValueError(f"length mismatch: {len(probs)} forecasts, {len(outs)} students")
    model_ll = log_loss_value(probs, outs)
    null_ll = log_loss_value([null_rate] * len(outs), outs)
    wins = model_ll < null_ll
    return ModelLevelResult(
        layer=LAYER_MODEL,
        comparator=COMPARATOR_BASE_RATE_NULL,
        held_out_unit=UNIT_HELD_OUT_STUDENTS,
        n_students=len(outs),
        model_log_loss=model_ll,
        null_log_loss=null_ll,
        null_rate=null_rate,
        decision=REPORT if wins else WITHHOLD,
        reason=(
            "model beat the base-rate null on held-out students"
            if wins
            else "model failed to beat the base-rate null -- POV 2 falsifier (4) fires: "
            "ship Memory and Performance only and say so"
        ),
    )


@dataclass(frozen=True)
class StudentAbstention:
    """Per-student abstention decision for Readiness -- the layer ON TOP.

    Abstention survives here and nowhere else. Not because refusing is safer,
    but because the validation that replaced it everywhere else (a per-student
    held-out set) does not exist at this layer.
    """

    student_id: str
    coverage: float
    coverage_floor: float
    memory_reports: bool
    performance_reports: bool
    decision: str
    reasons: tuple


def readiness_student_abstention(
    student_id: str,
    coverage: float,
    coverage_floor: float,
    memory_result: GateResult,
    performance_result: GateResult,
) -> StudentAbstention:
    """Per-student abstention for Readiness. BRAINLIFT.md section 7.

    Three conditions, all required: outline coverage at or above the floor, and
    both component gates reporting. `coverage_floor` is an ARGUMENT, not a
    module constant, because BRAINLIFT.md section 8 records that inheriting the
    50% figure from the assignment brief's worked example and then justifying it
    afterwards was the original defect. A floor is an OUTPUT of this analysis --
    see `sweep_coverage_floor` -- and until one is derived the caller must pass
    the provisional value explicitly and label it.

    DOES NOT LICENSE: reporting a readiness number to this student on the
    strength of the model-level test alone. Both layers must pass.
    """
    reasons = []
    if coverage < coverage_floor:
        reasons.append(
            f"outline coverage {coverage:.2f} below the floor {coverage_floor:.2f}"
        )
    if not memory_result.reports:
        reasons.append("Memory gate withheld")
    if not performance_result.reports:
        reasons.append("Performance gate withheld")
    return StudentAbstention(
        student_id=student_id,
        coverage=coverage,
        coverage_floor=coverage_floor,
        memory_reports=memory_result.reports,
        performance_reports=performance_result.reports,
        decision=WITHHOLD if reasons else REPORT,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class ReadinessDecision:
    """Both readiness layers, kept separate inside one object.

    A DIFFERENT TYPE from `GateResult` on purpose. If Readiness returned a
    `GateResult` the three rows of BRAINLIFT.md section 7's table would be
    interchangeable in code, which is the collapse the table exists to prevent.
    """

    student_id: str
    model_level: ModelLevelResult
    student: StudentAbstention
    decision: str
    reason: str


def readiness_gate(
    student_id: str,
    cohort_probs,
    cohort_outcomes,
    null_rate: float,
    coverage: float,
    coverage_floor: float,
    memory_result: GateResult,
    performance_result: GateResult,
) -> ReadinessDecision:
    """Compose both readiness layers. Reports only if BOTH pass.

    The model-level test is a property of the cohort and is identical for every
    student; the abstention test is a property of this student. Running them in
    that order is the whole asymmetry: a model that fails at the cohort level
    withholds from EVERYONE, including students whose own data is excellent.
    """
    model_level = readiness_model_gate(cohort_probs, cohort_outcomes, null_rate)
    student = readiness_student_abstention(
        student_id, coverage, coverage_floor, memory_result, performance_result
    )
    if not model_level.model_is_publishable:
        return ReadinessDecision(
            student_id=student_id,
            model_level=model_level,
            student=student,
            decision=WITHHOLD,
            reason="model-level: " + model_level.reason,
        )
    if student.decision == WITHHOLD:
        return ReadinessDecision(
            student_id=student_id,
            model_level=model_level,
            student=student,
            decision=WITHHOLD,
            reason="per-student abstention: " + "; ".join(student.reasons),
        )
    return ReadinessDecision(
        student_id=student_id,
        model_level=model_level,
        student=student,
        decision=REPORT,
        reason="model beat the base-rate null AND this student clears every abstention condition",
    )


def layer_table():
    """The three rows of BRAINLIFT.md section 7's gate table, as data.

    `run.py` prints this and `test_appendix_b.py` asserts the rows are pairwise
    distinct -- a mechanical check that the layers have not been quietly merged
    by a later edit.
    """
    return (
        ("Memory", LAYER_PER_STUDENT, COMPARATOR_INCUMBENT, UNIT_STUDENT_REVIEWS),
        ("Performance", LAYER_PER_STUDENT, COMPARATOR_TOPIC_PRIOR, UNIT_STUDENT_ITEMS),
        ("Readiness", LAYER_MODEL, COMPARATOR_BASE_RATE_NULL, UNIT_HELD_OUT_STUDENTS),
    )


# ---------------------------------------------------------------------------
# the SECOND, ABSOLUTE gate -- accept-only-if-better cannot catch this
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SanityResult:
    """Absolute quality check, analogous to upstream's FSRS health check.

    Accept-only-if-better is RELATIVE: a model can beat its predecessor and
    still be badly calibrated. Upstream runs a separate absolute check
    (`params.rs:182`) with fixed bounds, gated at > 300 items because below that
    an absolute quality estimate is too noisy to act on.
    """

    n_items: int
    min_items: int
    log_loss: float
    bound: float
    bound_provenance: str
    decision: str
    reason: str


UPSTREAM_HEALTH_LOG_LOSS_BOUND = 1.11
"""Upstream's adjusted-log-loss bound (`params.rs:182`, `<= 1.11 || rmse <= 1.53`).

IMPORTED FOR SHAPE, NOT FOR AUTHORITY. It was chosen for FSRS card-level recall
prediction on Anki's own benchmark corpus; nothing establishes it as the right
bound for a Speedrun score, and BRAINLIFT.md Appendix B item 5 owes a derived
replacement. Any run that uses it must say so in its output, which `run.py`
does.
"""

UPSTREAM_HEALTH_MIN_ITEMS = 300
"""Upstream's item floor for running the health check at all (`params.rs:182`).
Same status as the bound above: borrowed shape, not derived authority."""


def sanity_gate(
    probs,
    outcomes,
    min_items: int,
    log_loss_bound: float,
    bound_provenance: str,
) -> SanityResult:
    """Absolute check: is this model fit to show at all? BRAINLIFT.md section 7.

    Three outcomes, and the middle one matters: below `min_items` the check
    cannot run, and NOT-RUN is reported as WITHHOLD rather than as a pass. A
    check that silently passes when it could not be evaluated is worse than no
    check.

    `bound_provenance` is a required argument so that no caller can use a bound
    without recording where it came from. Passing "derived in Appendix B" when
    it was not is a lie a human has to type deliberately.
    """
    outs = list(outcomes)
    if len(outs) < min_items:
        return SanityResult(
            n_items=len(outs),
            min_items=min_items,
            log_loss=float("nan"),
            bound=log_loss_bound,
            bound_provenance=bound_provenance,
            decision=WITHHOLD,
            reason=f"only {len(outs)} items; the absolute check needs >= {min_items} "
            "to be worth acting on, so it did NOT run and this is not a pass",
        )
    ll = log_loss_value(probs, outs)
    ok = ll <= log_loss_bound
    return SanityResult(
        n_items=len(outs),
        min_items=min_items,
        log_loss=ll,
        bound=log_loss_bound,
        bound_provenance=bound_provenance,
        decision=REPORT if ok else WITHHOLD,
        reason=(
            f"log loss {ll:.4f} <= bound {log_loss_bound:.4f}"
            if ok
            else f"log loss {ll:.4f} exceeds bound {log_loss_bound:.4f}; the model may "
            "still have beaten its incumbent, and it is still not fit to show"
        ),
    )


# ---------------------------------------------------------------------------
# DERIVED FLOORS -- BRAINLIFT.md Appendix B item 5
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FloorSweepRow:
    floor: int
    n_students_gated_out: int
    n_students_reporting: int
    policy_log_loss: float


def sweep_items_floor(records, floors):
    """Find the `fsrs_items` floor that minimises held-out log loss. Item 5.

    `records` is a sequence of dicts with keys:
        n_items          how much data the candidate was fitted on
        candidate_probs  candidate forecasts on the student's EVAL slice
        incumbent_probs  incumbent forecasts on the same slice
        gate_wins        whether the candidate beat the incumbent on a
                         SEPARATE gate slice (never on the eval slice)
        outcomes         the eval-slice outcomes

    The policy under test is: report the candidate if `n_items >= floor` AND the
    gate accepted it; otherwise report the incumbent. Every policy therefore
    emits a forecast for every student, so all floors are scored on identical
    data and the comparison is fair. THAT IS WHY THE POLICY FALLS BACK TO THE
    INCUMBENT RATHER THAN ABSTAINING -- an abstaining policy emits nothing and
    cannot be scored by a proper scoring rule at all, which is the asymmetry
    BRAINLIFT.md POV 2 flags. Abstention is handled separately, by
    `abstention_vs_shrinkage`.

    Note the gate/eval separation. Upstream evaluates its accept-only-if-better
    comparison on the SAME items it fitted on. Doing that here would let the
    gate select on the evaluation set and guarantee a flattering floor.
    """
    rows = []
    for floor in floors:
        probs = []
        outs = []
        gated_out = 0
        reporting = 0
        for rec in records:
            use_candidate = rec["n_items"] >= floor and rec["gate_wins"]
            if use_candidate:
                reporting += 1
                probs.extend(rec["candidate_probs"])
            else:
                gated_out += 1
                probs.extend(rec["incumbent_probs"])
            outs.extend(rec["outcomes"])
        rows.append(
            FloorSweepRow(
                floor=int(floor),
                n_students_gated_out=gated_out,
                n_students_reporting=reporting,
                policy_log_loss=log_loss_value(probs, outs),
            )
        )
    best = min(rows, key=lambda r: r.policy_log_loss)
    return best, rows


@dataclass(frozen=True)
class CoverageFloorRow:
    floor: float
    n_students: int
    model_log_loss: float
    null_log_loss: float

    @property
    def margin(self) -> float:
        return self.null_log_loss - self.model_log_loss


def sweep_coverage_floor(coverages, probs, outcomes, null_rate: float, floors):
    """Where on the coverage scale does the readiness model still beat the null?

    For each candidate floor, restrict to students at or above it and compare
    the model against the base-rate null ON THAT SUBSET. The lowest floor at
    which the margin is still positive is the derived coverage floor -- the
    point below which the model has not been shown to add anything, and
    abstention is therefore not a preference but the only supported behaviour.

    DOES NOT LICENSE reading the argmax as an optimum: subsets shrink as the
    floor rises, so the margin gets noisier, and this function reports the
    student count in every row precisely so a reader can see that happening.
    """
    rows = []
    for floor in floors:
        idx = [i for i, c in enumerate(coverages) if c >= floor]
        if len(idx) < 20:
            continue
        sub_p = [probs[i] for i in idx]
        sub_y = [outcomes[i] for i in idx]
        rows.append(
            CoverageFloorRow(
                floor=float(floor),
                n_students=len(idx),
                model_log_loss=log_loss_value(sub_p, sub_y),
                null_log_loss=log_loss_value([null_rate] * len(idx), sub_y),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# ABSTENTION vs SHRINKAGE -- BRAINLIFT.md Appendix B item 4, POV 2 falsifier (3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AbstentionComparison:
    """The comparison POV 2's falsifier (3) turns on.

    `overlap_*` is the region where BOTH mechanisms emit a number, which is the
    only region where a proper scoring rule can compare them at all.
    `abstained_*` is the region abstention refuses. Abstention scores NOTHING
    there -- not a bad score, no score -- and shrinkage's log loss on that region
    is the size of the information abstention destroys.
    """

    floor: float
    overlap_students: int
    overlap_abstention_log_loss: float
    overlap_shrinkage_log_loss: float
    abstained_students: int
    abstained_forecasts: int
    abstained_shrinkage_log_loss: float
    abstained_null_log_loss: float
    shrinkage_k: float

    @property
    def overlap_winner(self) -> str:
        if self.overlap_shrinkage_log_loss < self.overlap_abstention_log_loss:
            return "shrinkage"
        if self.overlap_shrinkage_log_loss > self.overlap_abstention_log_loss:
            return "abstention (raw estimate)"
        return "tie"


def abstention_vs_shrinkage(records, prior: float, k: float, floor: float, null_rate: float):
    """Run POV 2's falsifier (3). BRAINLIFT.md Appendix B item 4.

    `records`: sequence of dicts with keys `n`, `estimate`, `outcomes`.

    Two mechanisms:
      ABSTENTION  emit the raw per-student estimate when n >= floor; below the
                  floor, emit nothing.
      SHRINKAGE   always emit shrink_toward_prior(estimate, prior, n, k).

    Compared on the overlap (n >= floor), where both emit. Reported separately
    on the abstained region, where only shrinkage emits -- because BRAINLIFT.md
    is explicit that abstention "has to justify the information it destroys on
    the rest", and the only way to show that quantity is to print what the rival
    achieved there.

    The null log loss on the abstained region is reported alongside: if
    shrinkage there is no better than a constant, abstention destroyed nothing
    of value and the comparison favours it.
    """
    from calibration import shrink_toward_prior  # local: keeps the import graph one-way

    over_abst_p, over_shrink_p, over_y = [], [], []
    below_p, below_y = [], []
    overlap_students = 0
    abstained_students = 0
    for rec in records:
        n = rec["n"]
        est = rec["estimate"]
        outs = list(rec["outcomes"])
        shrunk = shrink_toward_prior(est, prior, n, k)
        if n >= floor:
            overlap_students += 1
            over_abst_p.extend([est] * len(outs))
            over_shrink_p.extend([shrunk] * len(outs))
            over_y.extend(outs)
        else:
            abstained_students += 1
            below_p.extend([shrunk] * len(outs))
            below_y.extend(outs)
    return AbstentionComparison(
        floor=float(floor),
        overlap_students=overlap_students,
        overlap_abstention_log_loss=log_loss_value(over_abst_p, over_y) if over_y else float("nan"),
        overlap_shrinkage_log_loss=(
            log_loss_value(over_shrink_p, over_y) if over_y else float("nan")
        ),
        abstained_students=abstained_students,
        abstained_forecasts=len(below_y),
        abstained_shrinkage_log_loss=(
            log_loss_value(below_p, below_y) if below_y else float("nan")
        ),
        abstained_null_log_loss=(
            log_loss_value([null_rate] * len(below_y), below_y) if below_y else float("nan")
        ),
        shrinkage_k=float(k),
    )


# ---------------------------------------------------------------------------
# LATENCY CUT -- BRAINLIFT.md Appendix B item 6
# ---------------------------------------------------------------------------


def fit_latency_cut(latency_fractions, evaluate, grid=None):
    """Fit the latency threshold for the scored-item plausibility filter. Item 6.

    `latency_fractions[i]` is session i's median response latency as a fraction
    of the item's displayed target time. `evaluate(keep)` takes a list of bools
    -- which sessions to KEEP in the fitting set -- and returns held-out log
    loss. The evaluation set never changes; only what is excluded from fitting
    does, which is what makes the sweep a fair comparison.

    Returns (best_cut, [(cut, log_loss, n_kept), ...]).

    This replaces the 20% figure BRAINLIFT.md section 7 records as taken from
    teardown observation rather than derived. The operational definition here is
    the honest one: a cut is good if excluding the sessions below it IMPROVES
    held-out prediction. Note what that does not require -- it never asks
    whether a session was "really" zero-effort, because in real data nobody can
    know that. On synthetic data the ground-truth label exists, and `run.py`
    reports the agreement as a diagnostic explicitly marked unavailable in
    production.
    """
    if grid is None:
        grid = [i / 100.0 for i in range(0, 101, 2)]
    curve = []
    for cut in grid:
        keep = [f >= cut for f in latency_fractions]
        if not any(keep):
            continue
        curve.append((float(cut), evaluate(keep), sum(keep)))
    if not curve:
        raise ValueError("every candidate cut discarded the entire fitting set")
    best = min(curve, key=lambda row: row[1])[0]
    return best, curve
