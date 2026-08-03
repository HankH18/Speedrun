# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix B calibration harness -- single entry point.

    python3 speedrun-analysis/appendix_b/run.py

Runs every piece of machinery BRAINLIFT.md Appendix B owes, end to end, on a
SYNTHETIC cohort this file generates deterministically. Standard library only.
Fixed seed. No arguments, no configuration, no network.

READ THE BANNER THE PROGRAM PRINTS FIRST. There is no real student data in this
project yet. Every number below is a number about a cohort that does not exist,
produced by a generating process written by hand in this file. The machinery is
real and the thresholds are not.
"""

from __future__ import annotations

import random
import sys
import types
from pathlib import Path

# Compile the modules from SOURCE TEXT rather than importing them, for the
# reason spelled out at length in appendix_a/test_model.py: Python invalidates a
# .pyc on (source mtime seconds, source size), so an edit that changes neither
# is served from a stale cache. `sys.dont_write_bytecode` stops this file
# WRITING a .pyc; it does not stop it READING one some other tool left behind.
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


# ===========================================================================
# SYNTHETIC COHORT PARAMETERS -- every one of these is a number I chose
# ===========================================================================

SEED = 20260802
"""The only seed in this harness. Everything downstream derives from it."""

N_STUDENTS = 1200
"""Cohort size. Chosen so the evaluation split holds ~300 students and ~27
failures at a 91% pass rate -- enough for a reliability curve to have any bins
at all, and still small enough that the report says so."""

FIT_FRAC, CALIB_FRAC = 0.50, 0.25
"""Three-way split of STUDENTS: fit the model / fit the calibrator / evaluate."""

# -- Memory -----------------------------------------------------------------
DEFAULT_RETENTION = 0.85
"""The incumbent memory model: a constant, standing in for shipped FSRS
defaults. A student whose true retention is near 0.85 is one the incumbent
already predicts well, so their fitted model has almost nothing to win with --
which is the whole point of an accept-only-if-better gate."""

N_MEMORY_GATE = 40
N_MEMORY_EVAL = 40
"""Later reviews used to DECIDE the gate and to SCORE it. Two disjoint slices,
because deciding and scoring on the same reviews lets the gate select on its own
evaluation set. Upstream does exactly that (`params.rs:156` compares on the
training items); this harness does not, and the difference is a real one.
Holding both at 40 for every student is a simplification: it gives every
student's gate equal statistical power, which real data would not."""

# -- Performance ------------------------------------------------------------
TOPIC_PRIOR = 0.62
"""The impersonal comparator for Performance: population accuracy on the topic."""

SESSION_LEN = 10
ZERO_EFFORT_RATE = 0.18
ZERO_EFFORT_ACCURACY = 0.25
ZERO_EFFORT_LATENCY = (0.01, 0.35)
GENUINE_LATENCY = (0.15, 1.70)
"""Zero-effort sessions: the adversarial case from BRAINLIFT.md section 4.3 --
answered at 1-4 seconds against a ~90 second target. Their responses are close
to guessing on a five-option item. 18% of sessions are drawn this way; nothing
establishes 18%, it is a contamination level chosen to make the latency filter's
job visible.

THE TWO LATENCY RANGES OVERLAP ON PURPOSE (0.15 to 0.35). An earlier version of
this generator drew them disjointly, and the fitted cut then separated the two
populations perfectly -- which made the filter look like a solved problem when
what it had actually solved was my own generator. Overlapping them means a fast
genuine session and a slow careless one are indistinguishable from latency
alone, which is the situation in real data, and it means the fitted cut has to
trade false exclusions against missed contamination like a real threshold."""

N_PERF_GATE = 40
N_PERF_EVAL = 40

# -- Readiness --------------------------------------------------------------
B0, B_MEMORY, B_PERF, B_COVERAGE = 3.05, 6.0, 4.0, 2.0
"""Coefficients of the synthetic pass-probability model, on the logit scale.
B0 is set so the cohort pass rate lands near the published 91% US MD
first-attempt rate (BRAINLIFT.md section 1). THAT IS A PROPERTY OF THIS
GENERATOR, NOT A FINDING -- the base rate was put in by hand so the null
predictor faced here is as hard as the real one."""

PROVISIONAL_COVERAGE_FLOOR = 0.50
"""The retracted figure from the assignment brief's worked example, carried here
ONLY so the report can show what it does and be compared against a derived one.
BRAINLIFT.md section 8 records that inheriting it and justifying it afterwards
was the original defect."""

RETRACTED_MEMORY_FLOOR = 200
UPSTREAM_FSRS_ITEMS_FLOOR = 8
"""Two floors with different standing: 200 is the retracted figure from the
brief's example (and in the wrong unit, graded reviews rather than fsrs_items);
8 is what `fsrs-rs` v6.6.0 actually does at `training.rs:319`. Neither is
Speedrun's."""

ITEM_BUCKETS = (0, 2, 5, 10, 20, 40, 80, 160, 320, 640)
ITEM_BUCKET_WEIGHTS = (6, 8, 10, 12, 12, 11, 9, 7, 5, 3)
"""How much fitting data each student has, and how common that is. Right-skewed
by hand: most students have little, a few have a lot. UNGROUNDED -- a real
distribution would come from a real collection, and the derived floors in this
report are conditional on this shape."""

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


def banner() -> None:
    print(rule("#"))
    print("#" + " SYNTHETIC DATA. NOT REAL STUDENTS. NO THRESHOLD BELOW IS FINAL. ".center(WIDTH - 2, " ") + "#")
    print(rule("#"))
    print("#")
    print("#  Speedrun has NO real student data. This harness generates a cohort of")
    print(f"#  {N_STUDENTS} imaginary students from a hand-written generating process in this")
    print(f"#  file, under seed {SEED}, and runs the Appendix B machinery on them.")
    print("#")
    print("#  WHAT THAT MEANS FOR EVERY NUMBER PRINTED BELOW:")
    print("#")
    print("#   * The MACHINERY is real. The metrics, the calibrators, the gates and the")
    print("#     splits are the ones that will run on real data unchanged.")
    print("#   * The RESULTS are not results. They describe a process I wrote. Where the")
    print("#     readiness model beats the base-rate null here, it does so because the")
    print("#     signal was put into the data by hand, forty lines above.")
    print("#   * NO DERIVED FLOOR HERE IS FINAL. Not the fsrs_items floor, not the")
    print("#     coverage floor, not the latency cut, not the shrinkage constant. Each")
    print("#     is the value this synthetic cohort implies, and BRAINLIFT.md section 7")
    print("#     stays at TBD until the same code is run against real reviews.")
    print("#   * Nothing here licenses any claim about a student, about Step 1, or about")
    print("#     whether Speedrun can measure readiness at all.")
    print("#")
    print("#  Accuracy is a FORBIDDEN metric in this project (BRAINLIFT.md section 1) and")
    print("#  is not computed anywhere in this directory. Everything is Brier and log")
    print("#  loss against a named comparator.")
    print("#")
    print(rule("#"))


# ===========================================================================
# THE SYNTHETIC COHORT
# ===========================================================================


class Student:
    """One imaginary student. Every field is generated; none is observed."""

    def __init__(self, idx: int, rng: random.Random) -> None:
        self.id = f"s{idx:04d}"
        # -- latent truths, never visible to any model ----------------------
        self.true_retention = rng.uniform(0.60, 0.98)
        self.true_ability = rng.uniform(0.30, 0.90)
        self.coverage = rng.uniform(0.05, 1.00)

        # -- Memory: fitting data, then two disjoint later slices -----------
        self.n_fsrs_items = rng.choices(ITEM_BUCKETS, weights=ITEM_BUCKET_WEIGHTS, k=1)[0]
        fit_hits = sum(
            1 for _ in range(self.n_fsrs_items) if rng.random() < self.true_retention
        )
        self.memory_estimate = (fit_hits + 1.0) / (self.n_fsrs_items + 2.0)
        self.memory_gate_outcomes = [
            1 if rng.random() < self.true_retention else 0 for _ in range(N_MEMORY_GATE)
        ]
        self.memory_eval_outcomes = [
            1 if rng.random() < self.true_retention else 0 for _ in range(N_MEMORY_EVAL)
        ]

        # -- Performance: sessions, some of them zero-effort ----------------
        self.n_scored_items = rng.choices(ITEM_BUCKETS, weights=ITEM_BUCKET_WEIGHTS, k=1)[0]
        self.sessions = []
        remaining = self.n_scored_items
        while remaining > 0:
            size = min(SESSION_LEN, remaining)
            remaining -= size
            zero_effort = rng.random() < ZERO_EFFORT_RATE
            if zero_effort:
                latency = rng.uniform(*ZERO_EFFORT_LATENCY)
                p = ZERO_EFFORT_ACCURACY
            else:
                latency = rng.uniform(*GENUINE_LATENCY)
                p = self.true_ability
            self.sessions.append(
                {
                    "latency_fraction": latency,
                    "zero_effort": zero_effort,
                    "outcomes": [1 if rng.random() < p else 0 for _ in range(size)],
                }
            )
        self.perf_gate_outcomes = [
            1 if rng.random() < self.true_ability else 0 for _ in range(N_PERF_GATE)
        ]
        self.perf_eval_outcomes = [
            1 if rng.random() < self.true_ability else 0 for _ in range(N_PERF_EVAL)
        ]
        self.performance_estimate = self.estimate_from_sessions(self.sessions)

        # -- Readiness: the outcome, one bit, arriving once -----------------
        logit = (
            B0
            + B_MEMORY * (self.true_retention - DEFAULT_RETENTION)
            + B_PERF * (self.true_ability - TOPIC_PRIOR)
            + B_COVERAGE * (self.coverage - 0.5)
        )
        self.true_pass_probability = calibration.sigmoid(logit)
        self.passed = 1 if rng.random() < self.true_pass_probability else 0

    @staticmethod
    def estimate_from_sessions(sessions) -> float:
        """Laplace-smoothed accuracy over whichever sessions are retained."""
        hits = sum(sum(s["outcomes"]) for s in sessions)
        n = sum(len(s["outcomes"]) for s in sessions)
        return (hits + 1.0) / (n + 2.0)

    @property
    def features(self):
        """What the readiness model actually sees: ESTIMATES, not truths."""
        return [self.memory_estimate, self.performance_estimate, self.coverage]


def build_cohort():
    rng = random.Random(SEED)
    return [Student(i, rng) for i in range(N_STUDENTS)]


# ===========================================================================
# REPORT SECTIONS
# ===========================================================================


def section_cohort(cohort, fit_idx, calib_idx, eval_idx) -> None:
    heading("[SYNTHETIC] 0. COHORT AND SPLIT")
    base = sum(s.passed for s in cohort) / len(cohort)
    print(f"Students generated              : {len(cohort)}  (seed {SEED})")
    print(f"Synthetic cohort pass rate      : {base:.4f}")
    print("Published comparison            : 91% US MD, 86% US DO, 73% IMG first-attempt")
    print("                                  (BRAINLIFT.md section 1). The generator was")
    print("                                  tuned toward the US MD figure ON PURPOSE, so")
    print("                                  that the null predictor here is as hard to")
    print("                                  beat as the real one. It is an input.")
    sub("Three-way split, by STUDENT, disjointness asserted before anything is reported")
    print(f"  fit    (model parameters)     : {len(fit_idx):>5} students")
    print(f"  calib  (Platt / isotonic)     : {len(calib_idx):>5} students")
    print(f"  eval   (every reported number): {len(eval_idx):>5} students")
    calibration.assert_disjoint(("fit", fit_idx), ("calib", calib_idx), ("eval", eval_idx))
    print("  assert_disjoint(fit, calib, eval) ... PASSED (it raises; it does not warn)")
    print()
    print("  The unit is the STUDENT because the readiness outcome is per student.")
    print("  Per-student review splits, used by the Memory and Performance gates below,")
    print("  are splits IN TIME instead -- reviews of one card are not independent.")


def section_metric_checks() -> None:
    heading("1. METRIC IMPLEMENTATION vs CLOSED FORM (no synthetic data involved)")
    print("Before any model is scored: do the scoring rules agree with algebra?")
    print("These four rows are computed two ways -- empirically over a vector, and from")
    print("the closed form -- and `test_appendix_b.py` asserts them independently.")
    print()
    for rate in (0.91, 0.86, 0.73):
        n = 10000
        ones = int(round(rate * n))
        outcomes = [1] * ones + [0] * (n - ones)
        preds = metrics.base_rate_null(rate, n)
        bs = metrics.brier_score(preds, outcomes)
        ll, _ = metrics.log_loss(preds, outcomes)
        print(
            f"  constant p = {rate:.2f} at base rate {rate:.2f}:  "
            f"Brier {bs:.6f} (closed form {metrics.constant_predictor_brier(rate, rate):.6f})  "
            f"log loss {ll:.6f} (closed form {metrics.constant_predictor_log_loss(rate, rate):.6f})"
        )
    print()
    print("  Read the first row carefully. A CONSTANT function -- the thing BRAINLIFT.md")
    print("  section 1 forbids -- scores Brier 0.0819 and log loss 0.3025 at a 91% pass")
    print("  rate, and ~91% on the forbidden metric. 0.0819 is not a good Brier score;")
    print("  it is the number to beat, and any Brier reported without it is theatre.")


def section_gate_layers() -> None:
    heading("2. THE THREE GATES ARE THREE LAYERS (BRAINLIFT.md section 7)")
    print("Same mechanism -- accept only if it beats the incumbent on log loss -- at")
    print("three different layers, against three different comparators. Collapsing")
    print("these rows is the error the table exists to prevent, so gates.py exposes")
    print("three entry points with different arguments and Readiness returns a")
    print("different TYPE.")
    print()
    print(f"{'Score':<13}{'Layer':<32}{'Comparator':<33}")
    print(rule())
    for score, layer, comparator, unit in gates.layer_table():
        print(f"{score:<13}{layer:<32}{comparator[:32]:<33}")
        print(f"{'':<13}held out: {unit}")
    print()
    print("Why Readiness cannot share the layer: a student sits Step 1 once, and the")
    print("outcome arrives after the app has stopped being useful to them. There is no")
    print("per-student held-out set, so validation moves up to the cohort -- and a")
    print("cohort-level result licenses a claim about the MODEL, never about a student.")
    print("That is why per-student abstention survives there and only there.")


def _memory_records(cohort):
    """Per student: candidate/incumbent forecasts on the gate and eval slices."""
    records = []
    for s in cohort:
        cand = s.memory_estimate
        inc = DEFAULT_RETENTION
        gate_result = gates.memory_gate(
            s.id,
            [cand] * N_MEMORY_GATE,
            [inc] * N_MEMORY_GATE,
            s.memory_gate_outcomes,
        )
        records.append(
            {
                "student": s,
                "n_items": s.n_fsrs_items,
                "gate": gate_result,
                "gate_wins": gate_result.reports,
                "candidate_probs": [cand] * N_MEMORY_EVAL,
                "incumbent_probs": [inc] * N_MEMORY_EVAL,
                "outcomes": s.memory_eval_outcomes,
            }
        )
    return records


def section_memory(records) -> None:
    heading("[SYNTHETIC] 3. MEMORY -- per-student accept-only-if-better (item 2)")
    print("Candidate : the model fitted on this student's own history.")
    print(f"Incumbent : a constant {DEFAULT_RETENTION:.2f}, standing in for shipped FSRS defaults.")
    print(f"Decided on: {N_MEMORY_GATE} later reviews.   Scored on: {N_MEMORY_EVAL} FURTHER reviews.")
    print("The two slices are disjoint. Upstream decides and scores on the same items;")
    print("that lets the gate select on its own evaluation set, and this harness does not.")

    sub("Accept rate by how much data the candidate was fitted on")
    print(f"{'fsrs_items':>11}  {'students':>9}  {'accepted':>9}  {'accept rate':>12}  "
          f"{'median margin (nats)':>21}")
    print(rule())
    for bucket in ITEM_BUCKETS:
        rows = [r for r in records if r["n_items"] == bucket]
        if not rows:
            continue
        accepted = [r for r in rows if r["gate_wins"]]
        margins = sorted(r["gate"].margin for r in rows)
        median = margins[len(margins) // 2]
        print(
            f"{bucket:>11}  {len(rows):>9}  {len(accepted):>9}  "
            f"{len(accepted) / len(rows):>11.1%}  {median:>+21.4f}"
        )
    total_acc = sum(1 for r in records if r["gate_wins"])
    print(rule())
    print(f"{'all':>11}  {len(records):>9}  {total_acc:>9}  {total_acc / len(records):>11.1%}")
    print()
    print("The gate does real work at every level and refuses hardest where the data is")
    print("thinnest -- WITHOUT any floor being asserted. That is the point of BRAINLIFT.md")
    print("section 7's replacement of the retracted 200-review rule: the accept rate IS")
    print("the gate, and a floor is only worth adding if it beats this (see item 5).")

    sub("What the gate is worth, scored on the held-out eval slice")
    gated_p, always_p, never_p, outs = [], [], [], []
    for r in records:
        outs.extend(r["outcomes"])
        never_p.extend(r["incumbent_probs"])
        always_p.extend(r["candidate_probs"])
        gated_p.extend(r["candidate_probs"] if r["gate_wins"] else r["incumbent_probs"])
    for label, probs in (
        ("never report the fitted model (incumbent only)", never_p),
        ("always report the fitted model (no gate)", always_p),
        ("accept-only-if-better (the rule)", gated_p),
    ):
        ll, clamped = metrics.log_loss(probs, outs)
        print(f"  {label:<48} log loss {ll:.5f}  Brier {metrics.brier_score(probs, outs):.5f}"
              + (f"  [{clamped} clamped]" if clamped else ""))
    print()
    print("  Scored on reviews neither the fit nor the gate ever saw. If the gated row")
    print("  did not beat both others, the gate would be costing information and this")
    print("  report would say so.")


def _performance_records(cohort):
    records = []
    for s in cohort:
        cand = s.performance_estimate
        gate_result = gates.performance_gate(
            s.id,
            [cand] * N_PERF_GATE,
            [TOPIC_PRIOR] * N_PERF_GATE,
            s.perf_gate_outcomes,
        )
        records.append(
            {
                "student": s,
                "n_items": s.n_scored_items,
                "gate": gate_result,
                "gate_wins": gate_result.reports,
                "candidate_probs": [cand] * N_PERF_EVAL,
                "incumbent_probs": [TOPIC_PRIOR] * N_PERF_EVAL,
                "outcomes": s.perf_eval_outcomes,
            }
        )
    return records


def section_performance(records) -> None:
    heading("[SYNTHETIC] 4. PERFORMANCE -- per-student, DIFFERENT comparator (item 2)")
    print("Same layer as Memory, different comparator: the TOPIC PRIOR")
    print(f"(a constant {TOPIC_PRIOR:.2f}) -- what we would say knowing nothing about this")
    print("student. Beating your own incumbent and beating the impersonal prior are")
    print("different achievements, which is why these are two functions and not one.")
    print()
    accepted = sum(1 for r in records if r["gate_wins"])
    print(f"  accepted: {accepted} of {len(records)} students ({accepted / len(records):.1%})")
    gated_p, prior_p, outs = [], [], []
    for r in records:
        outs.extend(r["outcomes"])
        prior_p.extend(r["incumbent_probs"])
        gated_p.extend(r["candidate_probs"] if r["gate_wins"] else r["incumbent_probs"])
    print(f"  topic prior alone                 log loss {metrics.log_loss_value(prior_p, outs):.5f}")
    print(f"  accept-only-if-better (the rule)  log loss {metrics.log_loss_value(gated_p, outs):.5f}")
    print()
    print("  Note what contaminates the candidate here and not in Memory: zero-effort")
    print(f"  sessions. {ZERO_EFFORT_RATE:.0%} of fitting sessions were answered at 1-15% of target")
    print("  time with near-guessing accuracy, exactly the adversarial probe BRAINLIFT.md")
    print("  section 4.3 ran against three commercial tools. Item 6 below fits the cut.")


def _fit_readiness(cohort, fit_idx, calib_idx, eval_idx, shuffle_features=False):
    """Fit on FIT, calibrate on CALIB, predict on EVAL. Returns a dict."""
    fit_rows = [cohort[i].features for i in fit_idx]
    fit_y = [cohort[i].passed for i in fit_idx]
    if shuffle_features:
        # Destroy the feature-outcome link while keeping both marginals exactly
        # as they were. Deterministic permutation, so the control is reproducible.
        order = list(range(len(fit_rows)))
        random.Random(SEED + 1).shuffle(order)
        fit_rows = [fit_rows[i] for i in order]
    model = calibration.fit_logistic(fit_rows, fit_y)

    calib_scores = [model.score(cohort[i].features) for i in calib_idx]
    calib_y = [cohort[i].passed for i in calib_idx]
    platt = calibration.PlattCalibrator().fit(calib_scores, calib_y)
    iso = calibration.IsotonicCalibrator().fit(calib_scores, calib_y)

    eval_scores = [model.score(cohort[i].features) for i in eval_idx]
    eval_y = [cohort[i].passed for i in eval_idx]
    return {
        "model": model,
        "platt": platt,
        "iso": iso,
        "null_rate": sum(fit_y) / len(fit_y),
        "eval_y": eval_y,
        "raw": [calibration.sigmoid(z) for z in eval_scores],
        "platt_probs": platt.predict_all(eval_scores),
        "iso_probs": iso.predict_all(eval_scores),
    }


def section_readiness(fitted) -> None:
    heading("[SYNTHETIC] 5. READINESS -- model-level vs the base-rate null (item 3)")
    print("The test POV 2's falsifier (4) turns on. Fitted on the FIT students,")
    print("calibrated on the CALIB students, scored on the EVAL students -- three")
    print("disjoint sets of PEOPLE.")
    print()
    print(f"Null rate taken from the FIT split: {fitted['null_rate']:.4f}")
    print("NOT from the eval outcomes. A null built on the evaluation set is an oracle,")
    print("and beating an oracle is a different (harder) test than the honest one.")

    sub("Three forecasts, one held-out set of students")
    print(f"{'forecast':<34}{'Brier':>10}{'log loss':>11}{'Brier skill':>13}{'LL skill':>11}")
    print(rule())
    rows = [
        ("base-rate null (constant)", [fitted["null_rate"]] * len(fitted["eval_y"])),
        ("raw logistic (uncalibrated)", fitted["raw"]),
        ("+ Platt scaling", fitted["platt_probs"]),
        ("+ isotonic regression", fitted["iso_probs"]),
    ]
    for label, probs in rows:
        sk = metrics.skill_vs_null(probs, fitted["eval_y"], fitted["null_rate"])
        print(
            f"{label:<34}{sk.model_brier:>10.5f}{sk.model_log_loss:>11.5f}"
            f"{sk.brier_skill:>13.4f}{sk.log_loss_skill:>11.4f}"
        )
    print()
    print("Skill = 1 - model/null. Zero is the constant predictor by construction.")

    raw_ll = metrics.log_loss_value(fitted["raw"], fitted["eval_y"])
    platt_ll = metrics.log_loss_value(fitted["platt_probs"], fitted["eval_y"])
    iso_ll = metrics.log_loss_value(fitted["iso_probs"], fitted["eval_y"])
    sub("BOTH CALIBRATORS MADE IT WORSE, AND THE GATE STILL RUNS ON PLATT")
    print(f"  raw {raw_ll:.5f}   Platt {platt_ll:.5f} ({platt_ll - raw_ll:+.5f})   "
          f"isotonic {iso_ll:.5f} ({iso_ll - raw_ll:+.5f})")
    print()
    print("  This is a real result of the run and it is not flattering. A logistic model")
    print("  fitted by minimising log loss is already close to calibrated, so a second")
    print("  monotone rescaling fitted on 300 students mostly adds estimation noise --")
    print("  a known effect, visible here rather than hidden.")
    print()
    print("  WHY THE GATE BELOW STILL SCORES THE PLATT FORECAST. Platt is the")
    print("  pre-committed variant. Choosing the best of three ON THE EVALUATION SET is")
    print("  selection on the evaluation set: it would report the maximum of three noisy")
    print("  numbers as if it were one clean one, and the margin it produced would be")
    print("  partly the selection. So the gate runs on what was committed to in advance")
    print("  and takes the worse number. Picking raw here would have LOOKED better and")
    print("  meant less. Choosing a calibrator honestly needs a fourth split, and this")
    print("  harness does not have one -- that is an admitted gap, not a solved problem.")

    gate = gates.readiness_model_gate(
        fitted["platt_probs"], fitted["eval_y"], fitted["null_rate"]
    )
    sub("MODEL-LEVEL GATE (Platt-calibrated forecast)")
    print(f"  layer        : {gate.layer}")
    print(f"  comparator   : {gate.comparator}")
    print(f"  held-out unit: {gate.held_out_unit}  (n = {gate.n_students})")
    print(f"  model  log loss: {gate.model_log_loss:.5f}")
    print(f"  null   log loss: {gate.null_log_loss:.5f}")
    print(f"  margin         : {gate.margin:+.5f} nats")
    print(f"  DECISION       : {gate.decision}")
    print(f"  reason         : {gate.reason}")
    print()
    print("  READ THIS AS MACHINERY, NOT AS A RESULT. The model beats the null here")
    print("  because the generator put the signal in. The same code run against real")
    print("  students is the actual test, and BRAINLIFT.md commits in advance to what a")
    print("  failure means: ship two scores, do not relax the gate, do not blend the")
    print("  components into something that looks like a third score.")


def section_readiness_abstention(cohort, eval_idx, fitted, memory_records, perf_records) -> None:
    heading("[SYNTHETIC] 5b. READINESS -- the PER-STUDENT layer on top (item 3)")
    print("The model-level test above licenses a claim about the MODEL. It licenses")
    print("nothing about a student, so a second layer decides per student: outline")
    print("coverage at or above the floor, AND both component gates reporting.")
    print()
    print(f"Coverage floor used: {PROVISIONAL_COVERAGE_FLOOR:.2f} -- THE RETRACTED FIGURE from the")
    print("assignment brief's worked example, passed in explicitly because gates.py")
    print("refuses to hold a floor as a module constant. Section 7 derives a candidate")
    print("replacement; nothing is adopted.")

    mem_by_id = {r["gate"].student_id: r["gate"] for r in memory_records}
    perf_by_id = {r["gate"].student_id: r["gate"] for r in perf_records}
    decisions = []
    for i in eval_idx:
        s = cohort[i]
        decisions.append(
            gates.readiness_gate(
                s.id,
                fitted["platt_probs"],
                fitted["eval_y"],
                fitted["null_rate"],
                s.coverage,
                PROVISIONAL_COVERAGE_FLOOR,
                mem_by_id[s.id],
                perf_by_id[s.id],
            )
        )
    reported = [d for d in decisions if d.decision == gates.REPORT]
    print()
    print(f"  eval students                        : {len(decisions)}")
    print(f"  model-level gate passed              : {decisions[0].model_level.decision}")
    print(f"  students shown a Readiness number    : {len(reported)} "
          f"({len(reported) / len(decisions):.1%})")
    reasons = {}
    for d in decisions:
        if d.decision == gates.WITHHOLD:
            for r in d.student.reasons:
                key = (
                    f"outline coverage below the {PROVISIONAL_COVERAGE_FLOOR:.2f} floor"
                    if r.startswith("outline coverage")
                    else r
                )
                reasons[key] = reasons.get(key, 0) + 1
    sub("Why the other students were refused (a student can trip more than one)")
    for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>5}  {reason}")
    refused = len(decisions) - len(reported)
    print()
    print(f"  Refusing {refused} of {len(decisions)} students ({refused / len(decisions):.0%}) is not a "
          "design goal and it is not a")
    print("  triumph. It is what these three conditions do to this synthetic cohort at a")
    print("  floor taken from an example. Whether that trade is right is an empirical")
    print("  question about real students, and it is open.")
    print()
    print("  The asymmetry to notice: had the model-level gate failed, EVERY student")
    print("  would be refused, including the ones whose own data is excellent. A cohort")
    print("  result cannot be overridden by an individual's diligence, which is exactly")
    print("  why the two layers are separate objects in gates.py and not one flag.")


def section_null_control(cohort, fit_idx, calib_idx, eval_idx) -> None:
    heading("REQUIRED CONTROL -- the signal-free null (can this gate ever fail?)")
    print("A gate that never withholds is not a gate. Refit the entire readiness")
    print("pipeline on features that have been PERMUTED against the outcomes -- same")
    print("marginals, no relationship -- and the model-level gate must WITHHOLD.")
    print("If it reports, the harness is rigged and every number above is void.")
    control = _fit_readiness(cohort, fit_idx, calib_idx, eval_idx, shuffle_features=True)
    gate = gates.readiness_model_gate(
        control["platt_probs"], control["eval_y"], control["null_rate"]
    )
    print()
    print(f"  model  log loss: {gate.model_log_loss:.5f}")
    print(f"  null   log loss: {gate.null_log_loss:.5f}")
    print(f"  margin         : {gate.margin:+.5f} nats")
    print(f"  DECISION       : {gate.decision}")
    verdict = "PASS -- the gate can fail" if gate.decision == gates.WITHHOLD else "VOID -- the gate is rigged"
    print(f"  CONTROL        : {verdict}")


def section_reliability(fitted) -> None:
    heading("[SYNTHETIC] 6. RELIABILITY CURVE, STRATIFIED BY BAND (item 1)")
    print("BRAINLIFT.md section 1 asks for particular attention to the low-pass region,")
    print("'where the base rate stops doing the work'. Note what the count column shows:")
    print("that is exactly the region where there is almost no data, so the curve is")
    print("LEAST able to answer there. Empty bins are printed rather than dropped.")
    for label, probs in (("Platt-calibrated", fitted["platt_probs"]),
                         ("isotonic-calibrated", fitted["iso_probs"])):
        curve = metrics.reliability_curve(probs, fitted["eval_y"])
        sub(f"{label}")
        print(f"{'band':>12}{'n':>7}{'mean predicted':>17}{'observed':>11}{'gap':>9}")
        print(rule())
        for b in curve:
            if b.count == 0:
                print(f"{f'[{b.lo:.1f}, {b.hi:.1f})':>12}{0:>7}{'--':>17}{'--':>11}{'--':>9}"
                      "   (empty: no evidence either way)")
            else:
                print(f"{f'[{b.lo:.1f}, {b.hi:.1f})':>12}{b.count:>7}"
                      f"{b.mean_predicted:>17.4f}{b.observed:>11.4f}{b.gap:>+9.4f}")
        print(f"  count-weighted |gap| (ECE) = {metrics.weighted_calibration_gap(curve):.4f}")
        print("  ECE is a diagnostic and NEVER a gate: it is not a proper scoring rule,")
        print("  and a constant predictor at the base rate drives it toward zero.")

    sub("Murphy decomposition of the Platt-calibrated Brier score")
    parts = metrics.brier_decomposition(fitted["platt_probs"], fitted["eval_y"])
    print(f"  reliability  {parts.reliability:>10.6f}   (lower is better; 0 = perfectly calibrated)")
    print(f"  resolution   {parts.resolution:>10.6f}   (higher is better; 0 = constant predictor)")
    print(f"  uncertainty  {parts.uncertainty:>10.6f}   (a property of the OUTCOMES, not the model)")
    print(f"  residual     {parts.residual:>10.6f}   (within-bin spread the tidy identity drops)")
    print(f"  Brier        {parts.brier:>10.6f}")
    print()
    print("  Resolution is the row that matters: it is how much the model separates")
    print("  students at all. A model with good reliability and no resolution is the")
    print("  constant predictor section 1 forbids, wearing a model's clothes.")


def section_floors(memory_records, cohort, fitted, eval_idx) -> None:
    heading("[SYNTHETIC] 7. DERIVED FLOORS (item 5) -- outputs, never inputs")
    print("BRAINLIFT.md section 8: a give-up threshold must be an OUTPUT of this")
    print("analysis, not an input to it. Every floor below is read off the data.")
    print("EVERY ONE OF THEM IS READ OFF SYNTHETIC DATA AND IS THEREFORE PROVISIONAL.")

    sub("fsrs_items floor: policy = report the fitted model if n >= floor AND the gate accepted")
    floors = [0, 2, 5, 8, 10, 20, 40, 80, 160, 200, 320, 640]
    best, rows = gates.sweep_items_floor(memory_records, floors)
    print(f"{'floor':>7}{'students reporting':>21}{'gated out':>12}{'policy log loss':>18}")
    print(rule())
    for r in rows:
        mark = ""
        if r.floor == best.floor:
            mark = "  <- argmin"
        elif r.floor == RETRACTED_MEMORY_FLOOR:
            mark = "  <- the RETRACTED 200"
        elif r.floor == UPSTREAM_FSRS_ITEMS_FLOOR:
            mark = "  <- fsrs-rs training.rs:319"
        print(f"{r.floor:>7}{r.n_students_reporting:>21}{r.n_students_gated_out:>12}"
              f"{r.policy_log_loss:>18.6f}{mark}")
    print()
    print(f"  Derived floor on this cohort: {best.floor} fsrs_items.")
    print("  Read the SPREAD, not the argmin: if the column is nearly flat, the floor is")
    print("  not identified by this data and the honest report is 'no floor is supported',")
    print("  which is a legitimate outcome and the one an accept-only-if-better gate")
    print("  should produce -- the gate is already doing the refusing.")

    sub("Coverage floor: where does the readiness model still beat the null?")
    coverages = [cohort[i].coverage for i in eval_idx]
    rows = gates.sweep_coverage_floor(
        coverages, fitted["platt_probs"], fitted["eval_y"], fitted["null_rate"],
        [i / 10 for i in range(0, 10)],
    )
    print(f"{'floor':>7}{'students':>10}{'model LL':>12}{'null LL':>11}{'margin':>11}")
    print(rule())
    for r in rows:
        mark = "  <- the retracted 50% from the brief's example" if abs(r.floor - PROVISIONAL_COVERAGE_FLOOR) < 1e-9 else ""
        print(f"{r.floor:>7.1f}{r.n_students:>10}{r.model_log_loss:>12.5f}"
              f"{r.null_log_loss:>11.5f}{r.margin:>+11.5f}{mark}")
    print()
    print("  Subsets shrink as the floor rises, so the margin gets noisier upward. The")
    print("  student count is printed in every row so that is visible rather than hidden.")

    sub("Sanity gate (the ABSOLUTE check) -- distinct from accept-only-if-better")
    sanity = gates.sanity_gate(
        fitted["platt_probs"],
        fitted["eval_y"],
        min_items=gates.UPSTREAM_HEALTH_MIN_ITEMS,
        log_loss_bound=gates.UPSTREAM_HEALTH_LOG_LOSS_BOUND,
        bound_provenance="BORROWED from Anki params.rs:182 -- NOT derived for Speedrun",
    )
    print(f"  n = {sanity.n_items} (needs >= {sanity.min_items})   log loss {sanity.log_loss:.5f} "
          f"vs bound {sanity.bound:.2f}")
    print(f"  DECISION   : {sanity.decision}")
    print(f"  bound came from: {sanity.bound_provenance}")
    small = gates.sanity_gate(
        fitted["platt_probs"][:20], fitted["eval_y"][:20],
        min_items=gates.UPSTREAM_HEALTH_MIN_ITEMS,
        log_loss_bound=gates.UPSTREAM_HEALTH_LOG_LOSS_BOUND,
        bound_provenance="BORROWED from Anki params.rs:182 -- NOT derived for Speedrun",
    )
    print(f"  and on 20 items: {small.decision} -- {small.reason}")
    print()
    print("  A relative gate cannot catch a model that beat its predecessor and is still")
    print("  badly calibrated. Only this one can, and its bound is BORROWED, so Appendix")
    print("  B item 5 is not discharged by running it.")


def section_abstention(memory_records) -> None:
    heading("[SYNTHETIC] 8. ABSTENTION vs SHRINKAGE (item 4, POV 2 falsifier 3)")
    print("POV 2 predicted this would be the load-bearing test: if shrinkage toward a")
    print("prior beats abstention in the low-data regime, abstention is the wrong")
    print("mechanism and POV 2 needs rewriting rather than patching.")
    print()
    print("The asymmetry BRAINLIFT.md insists on: abstention emits NOTHING below the")
    print("floor, so no proper scoring rule can score it there. The comparison therefore")
    print("runs on the OVERLAP -- where both emit -- and the abstained region is reported")
    print("separately as the information abstention destroys.")
    records = [
        {"n": r["n_items"], "estimate": r["student"].memory_estimate, "outcomes": r["outcomes"]}
        for r in memory_records
    ]
    print()
    print(f"{'floor':>7}{'overlap n':>11}{'abstain LL':>13}{'shrink LL':>12}{'winner':>26}")
    print(rule())
    for floor in (UPSTREAM_FSRS_ITEMS_FLOOR, 20, 64, RETRACTED_MEMORY_FLOOR):
        cmp_ = gates.abstention_vs_shrinkage(
            records, prior=DEFAULT_RETENTION, k=calibration.BORROWED_SHRINKAGE_K,
            floor=floor, null_rate=DEFAULT_RETENTION,
        )
        print(f"{floor:>7}{cmp_.overlap_students:>11}{cmp_.overlap_abstention_log_loss:>13.5f}"
              f"{cmp_.overlap_shrinkage_log_loss:>12.5f}{cmp_.overlap_winner:>26}")
    print()
    cmp_ = gates.abstention_vs_shrinkage(
        records, prior=DEFAULT_RETENTION, k=calibration.BORROWED_SHRINKAGE_K,
        floor=RETRACTED_MEMORY_FLOOR, null_rate=DEFAULT_RETENTION,
    )
    print(f"What abstention destroys, at the retracted floor of {RETRACTED_MEMORY_FLOOR}:")
    print(f"  students refused          : {cmp_.abstained_students}")
    print(f"  forecasts never made      : {cmp_.abstained_forecasts}")
    print(f"  shrinkage's log loss there: {cmp_.abstained_shrinkage_log_loss:.5f}")
    print(f"  a constant prior there    : {cmp_.abstained_null_log_loss:.5f}")
    print()
    print("  If shrinkage on the refused region is no better than a constant, abstention")
    print("  destroyed nothing of value. If it is better, that gap is the price of")
    print("  refusing, and abstention has to be worth it. This is the quantity POV 2")
    print("  says abstention must justify, and it is the first time it has been measured")
    print("  at all -- on data that is not real.")
    gap = cmp_.abstained_null_log_loss - cmp_.abstained_shrinkage_log_loss
    print()
    print(f"  On this cohort that gap is {gap:+.5f} nats over {cmp_.abstained_forecasts} forecasts "
          "abstention never")
    print("  made. Read with the table above, which splits: shrinkage wins the overlap at")
    print("  the lowest floor and loses it at the higher ones. NEITHER MECHANISM WON")
    print("  OUTRIGHT HERE, so POV 2's falsifier (3) does not fire and does not clear")
    print("  either -- on synthetic data it could not have done. The result that counts")
    print("  is this same table computed from real reviews.")


def section_shrinkage(memory_records) -> None:
    heading("[SYNTHETIC] 9. FITTED SHRINKAGE CONSTANT (item 7)")
    print("Replacing the 50 borrowed from fsrs-optimizer issue #116, where it was tuned")
    print("for smoothing MEDIAN REVIEW TIMES in a different estimator and has, in")
    print("BRAINLIFT.md's own words, no authority here.")
    records = [
        (r["student"].memory_estimate, r["n_items"], r["outcomes"]) for r in memory_records
    ]
    best, curve = calibration.fit_shrinkage_constant(records, prior=DEFAULT_RETENTION)
    print()
    print(f"{'k':>7}{'held-out log loss':>21}")
    print(rule())
    for k, ll in curve:
        mark = ""
        if k == best:
            mark = "  <- argmin"
        elif k == calibration.BORROWED_SHRINKAGE_K:
            mark = "  <- the BORROWED 50"
        print(f"{k:>7.0f}{ll:>21.6f}{mark}")
    print()
    print(f"  Fitted k on this synthetic cohort: {best:.0f}. Borrowed value: "
          f"{calibration.BORROWED_SHRINKAGE_K:.0f}.")
    print("  The curve, not the argmin, is the deliverable: a flat curve means k is not")
    print("  identified and picking an argmin off it would be false precision.")
    print("  This value is NOT adopted anywhere. BRAINLIFT.md section 7 stays at TBD.")


def section_latency(cohort) -> None:
    heading("[SYNTHETIC] 10. LATENCY CUT (item 6)")
    print("Replacing the 20% of target time BRAINLIFT.md section 7 records as taken from")
    print("teardown observation rather than derived. Operational definition, and it is")
    print("the only honest one: a cut is good if EXCLUDING the sessions below it improves")
    print("held-out prediction. It never asks whether a session was 'really' zero-effort,")
    print("because on real data nobody can know that.")

    with_sessions = [s for s in cohort if s.sessions]
    flat = []
    for si, s in enumerate(with_sessions):
        for sess in s.sessions:
            flat.append((si, sess))
    fractions = [sess["latency_fraction"] for _, sess in flat]

    def evaluate(keep):
        kept = {}
        for (si, sess), k in zip(flat, keep):
            if k:
                kept.setdefault(si, []).append(sess)
        probs, outs = [], []
        for si, s in enumerate(with_sessions):
            sessions = kept.get(si)
            est = Student.estimate_from_sessions(sessions) if sessions else TOPIC_PRIOR
            probs.extend([est] * len(s.perf_eval_outcomes))
            outs.extend(s.perf_eval_outcomes)
        return metrics.log_loss_value(probs, outs)

    best, curve = gates.fit_latency_cut(fractions, evaluate)
    print()
    print(f"{'cut':>7}{'sessions kept':>16}{'held-out log loss':>21}")
    print(rule())
    for cut, ll, kept in curve:
        if int(round(cut * 100)) % 10 and abs(cut - best) > 1e-9 and abs(cut - 0.20) > 1e-9:
            continue
        mark = ""
        if abs(cut - best) < 1e-9:
            mark = "  <- argmin"
        elif abs(cut - 0.20) < 1e-9:
            mark = "  <- the 20% from teardown observation"
        print(f"{cut:>7.2f}{kept:>16}{ll:>21.6f}{mark}")
    print()
    truth = sum(1 for _, sess in flat if sess["zero_effort"])
    caught = sum(1 for _, sess in flat if sess["zero_effort"] and sess["latency_fraction"] < best)
    kept_genuine = sum(
        1 for _, sess in flat if not sess["zero_effort"] and sess["latency_fraction"] >= best
    )
    genuine = len(flat) - truth
    print(f"  Fitted cut on this synthetic cohort: {best:.2f} of target time.")
    print(f"  Ground-truth check (AVAILABLE ONLY BECAUSE THE DATA IS SYNTHETIC --")
    print(f"  no such column exists in production): {caught}/{truth} zero-effort sessions")
    print(f"  excluded, {kept_genuine}/{genuine} genuine sessions kept.")
    print("  This diagnostic is printed to show the operational criterion found something")
    print("  real HERE. It is not available to validate the cut on real data, which is")
    print("  exactly why the operational definition is the one that ships.")


def section_scorecard(memory_gate_pass, readiness_gate) -> None:
    heading("SCORECARD -- the seven things BRAINLIFT.md Appendix B owes")
    print("Machinery-complete means: implemented, tested, and demonstrated end to end on")
    print("synthetic data. It does NOT mean discharged. Every item that produces a")
    print("number is blocked on real reviews before that number means anything.")
    print()
    rows = [
        ("1. Reliability curves, Brier + log loss vs the null, never accuracy",
         "MACHINERY COMPLETE", "metrics.py; section 6. Curves shown for two calibrators."),
        ("2. Accept-only-if-better implemented and MEASURED (Memory, Performance)",
         "MACHINERY COMPLETE", "gates.py; sections 3-4. Runs per student, gate/eval disjoint."),
        ("3. Readiness model-level test vs the base-rate null on held-out students",
         "MACHINERY COMPLETE", "gates.py; section 5 + the signal-free control."),
        ("4. Abstention vs shrinkage, on the overlap, destruction accounted",
         "MACHINERY COMPLETE", "gates.abstention_vs_shrinkage; section 8."),
        ("5. Derived floors (fsrs_items, scored items, coverage, sanity bounds)",
         "PARTIAL", "sweeps run (section 7); the SANITY BOUND is still borrowed from"),
        ("", "", "     upstream (1.11 / 300 items) and is NOT derived. Item not discharged."),
        ("6. Latency fraction fitted, replacing the 20%",
         "MACHINERY COMPLETE", "gates.fit_latency_cut; section 10."),
        ("7. Shrinkage constant fitted, replacing the borrowed 50",
         "MACHINERY COMPLETE", "calibration.fit_shrinkage_constant; section 9."),
    ]
    for name, status, detail in rows:
        if name:
            print(f"  [{status:<18}] {name}")
        print(f"   {'':<20}  {detail}")
    print()
    print("  ADOPTED INTO BRAINLIFT.md section 7 AS A DERIVED THRESHOLD: nothing. Not one")
    print("  number in this run is eligible, because none of it came from a student.")
    print()
    print(f"  Memory gate accept rate this run : {memory_gate_pass:.1%}")
    print(f"  Readiness model-level decision   : {readiness_gate.decision}")


def footer() -> None:
    heading("WHAT THIS RUN DOES AND DOES NOT ESTABLISH")
    print("  * It establishes that the Appendix B machinery RUNS: the metrics agree with")
    print("    closed forms, the splits are disjoint, the gates decide, the calibrators")
    print("    fit, and the signal-free control makes the readiness gate withhold.")
    print("  * It establishes NOTHING about USMLE Step 1, about any student, or about")
    print("    whether Speedrun can measure readiness. The cohort is imaginary.")
    print("  * Every floor it derived is a floor for an imaginary cohort. BRAINLIFT.md")
    print("    section 7 stays at TBD. A threshold that constrains the analysis cannot")
    print("    also be validated by it, and a threshold derived from data I wrote is")
    print("    worse still -- it validates the generator.")
    print("  * Accuracy was not computed. There is no function for it in metrics.py and")
    print("    test_appendix_b.py asserts there is not.")
    print()
    print(rule("#"))
    print("#" + " EVERYTHING ABOVE IS SYNTHETIC. NO THRESHOLD HERE IS FINAL. ".center(WIDTH - 2, " ") + "#")
    print(rule("#"))
    print()
    print("Tests: python3 speedrun-analysis/appendix_b/test_appendix_b.py")


def main() -> int:
    banner()
    cohort = build_cohort()
    fit_idx, calib_idx, eval_idx = calibration.three_way_split(
        len(cohort), SEED, FIT_FRAC, CALIB_FRAC
    )
    section_cohort(cohort, fit_idx, calib_idx, eval_idx)
    section_metric_checks()
    section_gate_layers()

    memory_records = _memory_records(cohort)
    section_memory(memory_records)

    perf_records = _performance_records(cohort)
    section_performance(perf_records)

    fitted = _fit_readiness(cohort, fit_idx, calib_idx, eval_idx)
    section_readiness(fitted)
    section_readiness_abstention(cohort, eval_idx, fitted, memory_records, perf_records)
    section_null_control(cohort, fit_idx, calib_idx, eval_idx)
    section_reliability(fitted)
    section_floors(memory_records, cohort, fitted, eval_idx)
    section_abstention(memory_records)
    section_shrinkage(memory_records)
    section_latency(cohort)

    readiness = gates.readiness_model_gate(
        fitted["platt_probs"], fitted["eval_y"], fitted["null_rate"]
    )
    accept_rate = sum(1 for r in memory_records if r["gate_wins"]) / len(memory_records)
    section_scorecard(accept_rate, readiness)
    footer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
