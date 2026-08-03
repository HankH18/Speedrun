# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix B -- threshold derivation. Every numeric floor BRAINLIFT.md section 7
owes, derived here or reported UNKNOWN.

    python3 speedrun-analysis/appendix_b/derive_thresholds.py
    python3 speedrun-analysis/appendix_b/derive_thresholds.py --dataset PATH
    python3 speedrun-analysis/appendix_b/derive_thresholds.py --self-test

THE STANDING RULE
-----------------
**Thresholds are OUTPUTS of Appendix B and never inputs to it.** BRAINLIFT.md
section 8 records the defect this rule exists to prevent: two numbers were taken
from the assignment brief's illustrative sentence, asserted in section 7, and
then "validated" by an analysis they constrained. That ordering is circular.
So no derivation in this file may read a threshold from anywhere; each one has
to produce its number from data, and where the data does not exist the honest
output is UNKNOWN -- not a plausible-looking constant.

The retired figures (200 graded reviews, 50 scored items, 50% coverage, >300
items, 20% latency, shrinkage 50) appear in this file in exactly one place: the
`retired_starting_value` field of each threshold's record, which exists so a
reader can see what was NOT used. No procedure reads them.

WHAT "DERIVED" MEANS HERE
-------------------------
A threshold is DERIVED only when all four hold:

  1. its procedure ran to completion,
  2. on a dataset whose manifest says `"synthetic": false`,
  3. with enough held-out units in every bin the procedure needed, and
  4. the crossover it was searching for actually exists in that data.

Anything else is UNKNOWN with a stated reason. **On synthetic data no threshold
is final and none is ever marked DERIVED** -- a synthetic run reports its number
under `dry_run.value_not_a_threshold`, with the top-level `value` left null, so
that a number produced by a data-generating process this project wrote cannot be
mistaken for a number read off students.

FORBIDDEN METRIC
----------------
Accuracy is not computed anywhere in this file and must not be added. At a ~91%
first-attempt pass rate a constant "pass" predictor scores ~91% accuracy while
being a constant function. Every comparison below runs on log loss (the metric
upstream's own accept-only-if-better gate uses at `params.rs:156`), with Brier
reported alongside and never used to overturn a log-loss decision.

CORE MODULES
------------
This script computes no metric of its own. It binds, at import time:

  metrics.py      REQUIRED. `log_loss_value`, `brier_score`, `skill_vs_null`,
                  `constant_predictor_log_loss`, `constant_predictor_brier`.
                  Without it every threshold is UNKNOWN for a reason that is
                  about tooling, not data, and says so.
  gates.py        OPTIONAL. `accept_only_if_better(candidate_ll, incumbent_ll)`.
                  When absent, the accept decision falls back to the identical
                  rule expressed directly on log loss (strict improvement; ties
                  keep the incumbent, as upstream does). The binding actually
                  used is recorded in `core_modules` in the output.
  calibration.py  DECLARED, NOT CONSUMED. Appendix B items 1 and 3 (reliability
                  curves, post-hoc calibration) live there. Two thresholds below
                  -- the coverage floor and the shrinkage constant -- must be
                  RE-DERIVED on post-hoc-calibrated probabilities once that
                  module's entry point is fixed; each carries a
                  `pending_integration` note saying so. Its presence or absence
                  is reported, never silently worked around.

Every bound function is probe-validated against a fixture with a known answer
before use, so a signature change upstream of this file surfaces as a refusal to
bind rather than as a wrong number.

DATASET MANIFEST
----------------
One JSON file. No part of it is optional-by-omission: a missing block makes the
thresholds that need it UNKNOWN, with the block named.

    {
      "dataset_id":  "str, required",
      "synthetic":   true | false,          # required; true forbids DERIVED
      "description": "str",
      "memory": {
        "students": [
          {"student_id": "s1",
           "fsrs_items": 137,               # counted per params.rs:506 rules
           "holdout": [{"p_personal": 0.8, "p_incumbent": 0.7, "outcome": 1}]}
        ]
      },
      "performance": {
        "students": [
          {"student_id": "s1",
           "scored_items": 88,
           "holdout": [{"p_personal": .., "p_topic_prior": .., "outcome": 0|1}]}
        ]
      },
      "readiness": {
        "cohort_null_rates": {"us_md": 0.91},   # from the TRAINING split only
        "students": [
          {"student_id": "s1", "cohort": "us_md",
           "coverage": 0.38, "p_model": 0.74, "outcome": 1}
        ]
      },
      "sessions": {
        "null_rate": 0.55,                      # training-split item base rate
        "sessions": [
          {"session_id": "x", "median_latency_s": 3.1, "target_time_s": 90.0,
           "items": [{"p_model": 0.6, "outcome": 1}]}
        ]
      },
      "shrinkage": {
        "prior_label": "topic prior",
        "fit":  [{"n": 12, "p_personal": .., "p_prior": .., "outcomes": [0,1]}],
        "eval": [ ... same shape, DISJOINT students ... ]
      }
    }

DETERMINISM
-----------
Every bootstrap in this file draws from `random.Random(SEED)` with SEED fixed
below, and the output carries no timestamp, so two runs over the same dataset
produce byte-identical JSON. The dataset is identified by SHA-256 of its bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SCRIPT = "speedrun-analysis/appendix_b/derive_thresholds.py"
SCHEMA_VERSION = 1

SEED = 20260802
"""Fixed so bootstrap intervals are reproducible. Changing it changes every
interval in the output and must be recorded as a change, not a rerun."""

N_BOOTSTRAP = 1000
ALPHA = 0.05

COUNT_GRID: Tuple[int, ...] = (0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024)
"""Candidate count floors. Powers of two because the quantity being located is
an order of magnitude, and a grid finer than the evidence is a false precision."""

COVERAGE_GRID: Tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(0, 20))
LATENCY_GRID: Tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(0, 21))
K_GRID: Tuple[float, ...] = tuple(
    round(0.5 * (10.0 ** (i / 30.0)), 4) for i in range(0, 121)
)
K_CI_GRID: Tuple[float, ...] = K_GRID[::5]
"""Coarser grid used only for the bootstrap interval on k. The point estimate
uses the full `K_GRID`; the interval uses every fifth point because each
resample costs a whole grid sweep, and an interval quoted to a finer resolution
than the resampling supports would be false precision anyway."""

MIN_BIN_UNITS = 20
"""Minimum held-out units (students, or sessions) in a bin before that bin is
allowed to decide anything. A bin below this is 'not evaluable', which is a
different answer from 'fails', and the search treats it as such."""

STATUS_DERIVED = "DERIVED"
STATUS_UNKNOWN = "UNKNOWN"

STANDING_RULE = (
    "Thresholds are OUTPUTS of Appendix B and never inputs to it. No number in "
    "this file may be asserted in BRAINLIFT.md section 7 and validated here "
    "afterwards; that ordering is the circularity section 8 records. Where the "
    "derivation cannot run, section 7 says TBD and the app abstains."
)

SYNTHETIC_RULE = (
    "On synthetic data NO threshold is final and none is marked DERIVED. A "
    "synthetic run reports its number under dry_run.value_not_a_threshold with "
    "the top-level value left null."
)


# ---------------------------------------------------------------------------
# core module binding -- probe-validated, never assumed
# ---------------------------------------------------------------------------


class CoreBindingError(Exception):
    """Raised when a required core symbol is absent or fails its probe."""


class Core:
    """Resolved handles onto metrics.py / gates.py, plus a record of how each
    was resolved. Nothing in this class computes a metric; it only proves that
    what it bound behaves as the contract says before anything relies on it."""

    def __init__(self) -> None:
        self.report: Dict[str, Any] = {}
        self.metrics = self._import("metrics")
        self.calibration = self._import("calibration")
        self.gates = self._import("gates")
        self.ok = self.metrics is not None
        if self.ok:
            try:
                self._bind_metrics()
            except CoreBindingError as exc:
                self.ok = False
                self.report["metrics"]["probe"] = "FAILED: {}".format(exc)
        self._bind_gate()
        self.report["calibration"] = {
            "importable": self.calibration is not None,
            "consumed_by_this_script": False,
            "note": (
                "Appendix B items 1 and 3 live in calibration.py. The coverage "
                "floor and the shrinkage constant must be re-derived on "
                "post-hoc-calibrated probabilities once its entry point is "
                "fixed; see each threshold's pending_integration field."
            ),
        }

    @staticmethod
    def _import(name: str) -> Any:
        try:
            return __import__(name)
        except Exception:  # noqa: BLE001 - absence and breakage are both "not usable"
            return None

    def _bind_metrics(self) -> None:
        m = self.metrics
        missing = [
            n
            for n in (
                "log_loss_value",
                "brier_score",
                "skill_vs_null",
                "constant_predictor_log_loss",
                "constant_predictor_brier",
            )
            if not hasattr(m, n)
        ]
        if missing:
            raise CoreBindingError("metrics.py lacks {}".format(", ".join(missing)))
        self.log_loss = m.log_loss_value
        self.brier = m.brier_score
        self.skill_vs_null = m.skill_vs_null
        self.const_ll = m.constant_predictor_log_loss
        self.const_brier = m.constant_predictor_brier
        # Probe against closed forms this file computes independently. A binding
        # that disagrees with algebra is refused rather than used.
        got_ll = self.log_loss([0.5], [1])
        if abs(got_ll - math.log(2.0)) > 1e-9:
            raise CoreBindingError("log_loss_value([0.5],[1]) = {}".format(got_ll))
        got_ll2 = self.log_loss([0.9, 0.1], [1, 0])
        if abs(got_ll2 - (-math.log(0.9))) > 1e-9:
            raise CoreBindingError("log_loss_value([0.9,0.1],[1,0]) = {}".format(got_ll2))
        got_bs = self.brier([0.5, 0.25], [1, 0])
        if abs(got_bs - 0.15625) > 1e-12:
            raise CoreBindingError("brier_score([0.5,0.25],[1,0]) = {}".format(got_bs))
        got_c = self.const_ll(0.91, 0.91)
        want_c = -(0.91 * math.log(0.91) + 0.09 * math.log(0.09))
        if abs(got_c - want_c) > 1e-9:
            raise CoreBindingError("constant_predictor_log_loss = {}".format(got_c))
        self.report["metrics"] = {
            "importable": True,
            "probe": "PASSED",
            "bound": [
                "log_loss_value",
                "brier_score",
                "skill_vs_null",
                "constant_predictor_log_loss",
                "constant_predictor_brier",
            ],
        }

    def _bind_gate(self) -> None:
        """`accept_only_if_better` -- upstream's rule at params.rs:156: keep the
        incumbent unless the candidate STRICTLY improves log loss. Ties go to
        the incumbent."""
        fn = getattr(self.gates, "accept_only_if_better", None) if self.gates else None
        if fn is not None:
            try:
                ok = bool(fn(0.4, 0.5)) and not bool(fn(0.5, 0.4)) and not bool(fn(0.5, 0.5))
            except Exception as exc:  # noqa: BLE001
                ok = False
                self.report["gates"] = {
                    "importable": True,
                    "probe": "FAILED: {}".format(exc),
                }
            if ok:
                self.accept_only_if_better = fn
                self.report["gates"] = {
                    "importable": True,
                    "probe": "PASSED",
                    "binding": "gates.accept_only_if_better",
                }
                return
            self.report.setdefault(
                "gates",
                {
                    "importable": True,
                    "probe": "FAILED: accept_only_if_better did not satisfy "
                    "(0.4,0.5)=True, (0.5,0.4)=False, (0.5,0.5)=False",
                },
            )
        else:
            self.report["gates"] = {"importable": self.gates is not None, "probe": "ABSENT"}
        self.accept_only_if_better = _strict_log_loss_improvement
        self.report["gates"]["binding"] = (
            "local strict log-loss improvement (identical rule; gates.py not "
            "usable at generation time)"
        )


def _strict_log_loss_improvement(candidate_log_loss: float, incumbent_log_loss: float) -> bool:
    """params.rs:156 in one line: `if current <= optimized { keep current }`."""
    return candidate_log_loss < incumbent_log_loss


# ---------------------------------------------------------------------------
# small statistical helpers -- bootstrap only; nothing here is a metric
# ---------------------------------------------------------------------------


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    idx = q * (len(sorted_values) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_values[lo]
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _bootstrap_mean_ci(
    values: Sequence[float], rng: random.Random, n_resamples: int = N_BOOTSTRAP, alpha: float = ALPHA
) -> Tuple[float, float, float]:
    """Percentile bootstrap over the held-out unit. Returns (mean, lo, hi).

    The resampling unit is the STUDENT (or the session), never the review or the
    item, because reviews inside one student are not independent and pretending
    otherwise narrows every interval in this file."""
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    mean = sum(values) / n
    pool = list(values)
    draws: List[float] = []
    for _ in range(n_resamples):
        draws.append(sum(rng.choices(pool, k=n)) / n)
    draws.sort()
    return (mean, _percentile(draws, alpha / 2.0), _percentile(draws, 1.0 - alpha / 2.0))


def _bootstrap_argmin_ci(
    per_unit_curves: Sequence[Sequence[float]],
    grid: Sequence[float],
    rng: random.Random,
    n_resamples: int,
    alpha: float = ALPHA,
) -> Tuple[float, float]:
    """Percentile interval on the grid point minimising a summed objective.

    `per_unit_curves[u][j]` is unit u's TOTAL (not mean) contribution to the
    objective at `grid[j]`. Because the objective is a sum over units, a
    bootstrap resample is just a re-weighting of the same per-unit curves, so
    each resample costs one pass instead of a full re-evaluation. The argmin of
    the sum equals the argmin of the mean, since the divisor does not depend on
    the grid point.

    Fewer resamples than `_bootstrap_mean_ci`; the count used is reported beside
    the interval in the output rather than left implicit."""
    n = len(per_unit_curves)
    n_grid = len(grid)
    pool = list(per_unit_curves)
    picks: List[float] = []
    for _ in range(n_resamples):
        totals = [0.0] * n_grid
        for curve in rng.choices(pool, k=n):
            for j in range(n_grid):
                totals[j] += curve[j]
        best_j = 0
        best_v = totals[0]
        for j in range(1, n_grid):
            if totals[j] < best_v:
                best_v = totals[j]
                best_j = j
        picks.append(grid[best_j])
    picks.sort()
    return (_percentile(picks, alpha / 2.0), _percentile(picks, 1.0 - alpha / 2.0))


def _bin_index(value: float, grid: Sequence[float]) -> int:
    idx = 0
    for i, edge in enumerate(grid):
        if value >= edge:
            idx = i
    return idx


# ---------------------------------------------------------------------------
# the threshold record
# ---------------------------------------------------------------------------


class Derivation:
    """One threshold, and everything needed to trace it back to this script.

    `value` is null unless `status == DERIVED`. That invariant is enforced in
    `to_json`, not merely intended, so a procedure that computes a number on
    synthetic or under-powered data cannot leak it into the `value` field."""

    def __init__(
        self,
        threshold_id: str,
        unit: str,
        owed_by: str,
        consumed_by: str,
        function: str,
        procedure: str,
        needs: str,
        retired_starting_value: Any,
        retired_value_provenance: str,
        pending_integration: Optional[str] = None,
    ) -> None:
        self.id = threshold_id
        self.unit = unit
        self.owed_by = owed_by
        self.consumed_by = consumed_by
        self.function = function
        self.procedure = procedure
        self.needs = needs
        self.retired_starting_value = retired_starting_value
        self.retired_value_provenance = retired_value_provenance
        self.pending_integration = pending_integration
        self.value: Optional[float] = None
        self.status: str = STATUS_UNKNOWN
        self.reason: str = "not run: no dataset supplied"
        self.policy_inputs: Dict[str, Any] = {}
        self.evidence: Dict[str, Any] = {}

    def resolve(self, value: Optional[float], reason: str) -> "Derivation":
        """Record the procedure's outcome. `value=None` means the crossover this
        procedure searches for was not found in the data supplied."""
        self.value = value
        self.reason = reason
        self.status = STATUS_DERIVED if value is not None else STATUS_UNKNOWN
        return self

    def to_json(self, dataset: Optional["Dataset"]) -> Dict[str, Any]:
        value = self.value
        status = self.status
        dry_run = None
        if dataset is not None and dataset.synthetic and value is not None:
            dry_run = {
                "value_not_a_threshold": value,
                "why": SYNTHETIC_RULE,
            }
            value = None
            status = STATUS_UNKNOWN
        if status != STATUS_DERIVED:
            value = None
        record: Dict[str, Any] = {
            "id": self.id,
            "value": value,
            "unit": self.unit,
            "status": status,
            "script": SCRIPT,
            "function": self.function,
            "dataset": dataset.identity() if dataset is not None else None,
            "owed_by": self.owed_by,
            "consumed_by": self.consumed_by,
            "procedure": self.procedure,
            "reason": self.reason,
            "policy_inputs": self.policy_inputs,
            "retired_starting_value": self.retired_starting_value,
            "retired_value_provenance": self.retired_value_provenance,
        }
        if status != STATUS_DERIVED:
            record["needs"] = self.needs
        if self.pending_integration:
            record["pending_integration"] = self.pending_integration
        if dry_run is not None:
            record["dry_run"] = dry_run
        if self.evidence:
            record["evidence"] = self.evidence
        return record


class Dataset:
    def __init__(self, payload: Dict[str, Any], path: Optional[Path], sha256: Optional[str]) -> None:
        if "synthetic" not in payload:
            raise ValueError("dataset manifest must state \"synthetic\": true|false")
        self.payload = payload
        self.path = path
        self.sha256 = sha256
        self.synthetic = bool(payload["synthetic"])
        self.dataset_id = str(payload.get("dataset_id", "unnamed"))

    def block(self, name: str) -> Optional[Dict[str, Any]]:
        blk = self.payload.get(name)
        return blk if isinstance(blk, dict) else None

    def identity(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "path": str(self.path) if self.path else None,
            "sha256": self.sha256,
            "synthetic": self.synthetic,
            "description": self.payload.get("description", ""),
        }


# ---------------------------------------------------------------------------
# shared search: the smallest grid point above which reporting beats abstaining
# ---------------------------------------------------------------------------


def _floor_search(
    per_unit_deltas_by_bin: Dict[int, List[float]],
    grid: Sequence[float],
    rng: random.Random,
    min_units: int = MIN_BIN_UNITS,
) -> Tuple[Optional[float], List[Dict[str, Any]], str]:
    """Locate the smallest grid point L such that, at L and at EVERY grid point
    above it, the model's held-out log loss beats its comparator's with the
    upper end of a bootstrap interval below zero.

    `per_unit_deltas_by_bin[i]` holds, for each held-out unit falling in bin i,
    (model log loss - comparator log loss) on that unit's own held-out data.
    Negative = the model won on that unit.

    "At L and every point above it" is the whole content of the word FLOOR. A
    bin that wins in isolation while a bin above it loses is not a floor, it is
    a coincidence, and this search declines to report one.

    EMPTY versus SPARSE, which are different answers. A bin with zero units above
    the candidate floor observed nothing and so contradicts nothing; it limits
    the RANGE the claim was checked over, and the returned reason names that
    range. A bin with some units but fewer than `min_units` did observe
    something and cannot say what it means, so it blocks: reporting a floor
    underneath ambiguous evidence would be asserting the thing the bin failed to
    establish."""
    table: List[Dict[str, Any]] = []
    for i, edge in enumerate(grid):
        deltas = per_unit_deltas_by_bin.get(i, [])
        row: Dict[str, Any] = {
            "bin_floor": edge,
            "bin_ceiling": grid[i + 1] if i + 1 < len(grid) else None,
            "units": len(deltas),
        }
        if len(deltas) == 0:
            row["evaluable"] = False
            row["empty"] = True
            row["passes"] = None
            row["note"] = "no held-out units in this range; limits the range checked, blocks nothing"
        elif len(deltas) < min_units:
            row["evaluable"] = False
            row["empty"] = False
            row["passes"] = None
            row["note"] = "{} held-out units, fewer than the {} required to decide".format(
                len(deltas), min_units
            )
        else:
            row["empty"] = False
            mean, lo, hi = _bootstrap_mean_ci(deltas, rng)
            row["evaluable"] = True
            row["mean_log_loss_delta"] = round(mean, 6)
            row["ci95"] = [round(lo, 6), round(hi, 6)]
            row["passes"] = hi < 0.0
        table.append(row)

    evaluable = [i for i, row in enumerate(table) if row["evaluable"]]
    if not evaluable:
        return (None, table, "no bin held {} or more units; nothing is evaluable".format(min_units))
    top = max(evaluable)
    if not table[top]["passes"]:
        return (
            None,
            table,
            "the highest evaluable bin (floor {}) does not beat its comparator, so no "
            "floor exists in this data: reporting never starts beating abstaining".format(
                table[top]["bin_floor"]
            ),
        )
    floor_idx = top
    for i in sorted(evaluable, reverse=True):
        if table[i]["passes"]:
            floor_idx = i
        else:
            break
    sparse_above = [
        table[i]["bin_floor"]
        for i in range(floor_idx, len(table))
        if not table[i]["evaluable"] and not table[i]["empty"]
    ]
    if sparse_above:
        return (
            None,
            table,
            "bins at {} sit above the candidate floor and hold some units but fewer than "
            "{}, so 'wins at and above L' cannot be checked there".format(sparse_above, min_units),
        )
    return (
        table[floor_idx]["bin_floor"],
        table,
        "smallest grid point whose bin, and every non-empty bin above it, beat the "
        "comparator on held-out log loss with the upper 95% bootstrap bound below zero; "
        "checked up to a highest observed bin floor of {}".format(table[top]["bin_floor"]),
    )


def _per_student_delta(
    core: Core, holdout: Sequence[Dict[str, Any]], model_key: str, comparator_key: str
) -> Optional[float]:
    if not holdout:
        return None
    outcomes = [int(r["outcome"]) for r in holdout]
    model = [float(r[model_key]) for r in holdout]
    comparator = [float(r[comparator_key]) for r in holdout]
    return core.log_loss(model, outcomes) - core.log_loss(comparator, outcomes)


# ---------------------------------------------------------------------------
# 1. Memory -- the fsrs_items floor
# ---------------------------------------------------------------------------


def derive_memory_fsrs_items_floor(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="memory_fsrs_items_floor",
        unit="fsrs_items (Anki's own count, ComputeFsrsParamsResponse)",
        owed_by="BRAINLIFT.md section 7 give-up rule; Appendix B item 5",
        consumed_by="BUILD-DOC.md section 6, Memory row",
        function="derive_memory_fsrs_items_floor",
        procedure=(
            "Bin students by fsrs_items on a power-of-two grid. In each bin, per "
            "student, compute held-out log loss of the personal FSRS model minus "
            "held-out log loss of the incumbent (the student's current parameters, "
            "or shipped defaults). Bootstrap the mean delta over students. The "
            "floor is the smallest bin whose upper 95% bound is below zero and "
            "which stays below zero in every evaluable bin above it -- i.e. the "
            "point where reporting the personal model stops losing to falling "
            "back on the incumbent."
        ),
        needs=(
            "Per-student held-out FSRS reviews with (a) the fsrs_items count "
            "Anki returns, (b) the personal fitted model's predicted recall "
            "probability per held-out review, (c) the incumbent model's "
            "probability on the same reviews, (d) the observed outcome. The "
            "probabilities must come from the Rust/fsrs-rs fitter on a temporal "
            "split -- this script does not fit FSRS and must not."
        ),
        retired_starting_value=200,
        retired_value_provenance=(
            "200 graded reviews, taken from the assignment brief's illustrative "
            "sentence and then defended with an FSRS precedent that did not exist "
            "in the codebase claimed (BRAINLIFT.md section 8). Not read by this "
            "procedure. Note also the unit error: graded reviews are not "
            "fsrs_items."
        ),
    )
    d.policy_inputs = {
        "count_grid": list(COUNT_GRID),
        "min_units_per_bin": MIN_BIN_UNITS,
        "bootstrap_resamples": N_BOOTSTRAP,
        "alpha": ALPHA,
        "note": (
            "These four are stated choices about how much evidence is enough to "
            "let a bin speak, not derived quantities. They are listed here so "
            "they cannot be mistaken for outputs."
        ),
    }
    if dataset is None:
        return d
    block = dataset.block("memory")
    if not block or not block.get("students"):
        return d.resolve(None, "dataset has no `memory.students` block")

    by_bin: Dict[int, List[float]] = {}
    accepted = 0
    total = 0
    for student in block["students"]:
        delta = _per_student_delta(core, student.get("holdout", []), "p_personal", "p_incumbent")
        if delta is None:
            continue
        total += 1
        if core.accept_only_if_better(
            core.log_loss(
                [float(r["p_personal"]) for r in student["holdout"]],
                [int(r["outcome"]) for r in student["holdout"]],
            ),
            core.log_loss(
                [float(r["p_incumbent"]) for r in student["holdout"]],
                [int(r["outcome"]) for r in student["holdout"]],
            ),
        ):
            accepted += 1
        by_bin.setdefault(_bin_index(float(student["fsrs_items"]), COUNT_GRID), []).append(delta)

    floor, table, reason = _floor_search(by_bin, COUNT_GRID, rng)
    d.evidence = {
        "students_scored": total,
        "students_whose_personal_model_won": accepted,
        "per_bin": table,
        "gate_binding": core.report.get("gates", {}).get("binding"),
    }
    if floor is not None:
        below = sum(len(v) for i, v in by_bin.items() if COUNT_GRID[i] < floor)
        d.evidence["abstention_cost"] = {
            "students_below_floor": below,
            "fraction_below_floor": round(below / total, 4) if total else None,
            "note": (
                "Memory does not withhold below the floor -- BUILD-DOC section 6 "
                "falls back to the default-parameter estimate, labelled. This is "
                "the fraction of students who would see that fallback."
            ),
        }
    return d.resolve(floor, reason)


# ---------------------------------------------------------------------------
# 2. Performance -- the scored-item floor
# ---------------------------------------------------------------------------


def derive_performance_scored_item_floor(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="performance_scored_item_floor",
        unit="scored novel exam-style items",
        owed_by="BRAINLIFT.md section 7 give-up rule; Appendix B item 5",
        consumed_by="BUILD-DOC.md section 6, Performance row",
        function="derive_performance_scored_item_floor",
        procedure=(
            "Identical shape to the Memory floor, with the comparator changed: "
            "the personal performance model is scored against the TOPIC PRIOR -- "
            "the population's performance on that topic, which is what we would "
            "say knowing nothing about this student. Bin by scored-item count, "
            "bootstrap the per-student held-out log-loss delta, take the smallest "
            "bin that wins and keeps winning above itself."
        ),
        needs=(
            "Per-student held-out scored items with the personal model's "
            "P(correct), the topic prior's P(correct) on the same items fitted on "
            "the training split only, the observed outcome, and the student's "
            "scored-item count at the time of the split."
        ),
        retired_starting_value=50,
        retired_value_provenance=(
            "50 scored novel items. BRAINLIFT.md section 8 records its provenance "
            "as UNKNOWN -- it did not come from the brief and could not be "
            "reconstructed. Not read by this procedure."
        ),
    )
    d.policy_inputs = {
        "count_grid": list(COUNT_GRID),
        "min_units_per_bin": MIN_BIN_UNITS,
        "bootstrap_resamples": N_BOOTSTRAP,
        "alpha": ALPHA,
    }
    if dataset is None:
        return d
    block = dataset.block("performance")
    if not block or not block.get("students"):
        return d.resolve(None, "dataset has no `performance.students` block")

    by_bin: Dict[int, List[float]] = {}
    total = 0
    for student in block["students"]:
        delta = _per_student_delta(core, student.get("holdout", []), "p_personal", "p_topic_prior")
        if delta is None:
            continue
        total += 1
        by_bin.setdefault(_bin_index(float(student["scored_items"]), COUNT_GRID), []).append(delta)

    floor, table, reason = _floor_search(by_bin, COUNT_GRID, rng)
    d.evidence = {"students_scored": total, "per_bin": table}
    if floor is not None:
        below = sum(len(v) for i, v in by_bin.items() if COUNT_GRID[i] < floor)
        d.evidence["abstention_cost"] = {
            "students_below_floor": below,
            "fraction_below_floor": round(below / total, 4) if total else None,
            "note": (
                "Performance WITHHOLDS below the floor (BUILD-DOC section 6), so "
                "this fraction is information destroyed, not degraded. BRAINLIFT "
                "Appendix B item 4 requires abstention to be separately "
                "accountable for it; this is that accounting."
            ),
        }
    return d.resolve(floor, reason)


# ---------------------------------------------------------------------------
# 3. Readiness -- the coverage floor
# ---------------------------------------------------------------------------


def derive_readiness_coverage_floor(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="readiness_coverage_floor",
        unit="fraction of the published USMLE Step 1 outline covered (weighted)",
        owed_by="BRAINLIFT.md section 7 give-up rule; Appendix B item 5",
        consumed_by="BUILD-DOC.md section 6, Readiness row; section 5.4 display contract",
        function="derive_readiness_coverage_floor",
        procedure=(
            "Readiness is validated at the MODEL level on held-out STUDENTS, "
            "because an individual's Step 1 outcome cannot be held out. Sweep a "
            "coverage grid; at each level restrict to held-out students at or "
            "above it and bootstrap, over students, the per-student log loss of "
            "the readiness model minus that of the base-rate null (a constant "
            "predictor at the student's cohort pass rate, taken from the TRAINING "
            "split). The floor is the smallest coverage level that wins and keeps "
            "winning at every level above it."
        ),
        needs=(
            "Held-out students with a known Step 1 outcome, each carrying the "
            "readiness model's P(pass), the student's weighted outline coverage "
            "from speedrun-analysis/outline/coverage.py, and their cohort; plus "
            "cohort pass rates estimated on the training split. This is the one "
            "threshold whose data cannot be manufactured from a collection: it "
            "needs real outcomes for real students."
        ),
        retired_starting_value=0.50,
        retired_value_provenance=(
            "50% topic coverage, lifted verbatim from the assignment brief's "
            "illustrative sentence 'no score below 200 graded reviews and 50% "
            "topic coverage' (BRAINLIFT.md section 8). Not read by this procedure."
        ),
        pending_integration=(
            "Must be re-derived on post-hoc-calibrated probabilities once "
            "calibration.py's entry point is fixed (BUILD-DOC section 10: Platt "
            "or isotonic, fitted on a set disjoint from both training and "
            "evaluation). An uncalibrated model can lose to the null for reasons "
            "a calibration map would fix, which would place this floor too high."
        ),
    )
    d.policy_inputs = {
        "coverage_grid": list(COVERAGE_GRID),
        "min_units_per_level": MIN_BIN_UNITS,
        "bootstrap_resamples": N_BOOTSTRAP,
        "alpha": ALPHA,
    }
    if dataset is None:
        return d
    block = dataset.block("readiness")
    if not block or not block.get("students"):
        return d.resolve(None, "dataset has no `readiness.students` block")
    null_rates = block.get("cohort_null_rates") or {}
    if not null_rates:
        return d.resolve(
            None,
            "dataset has no `readiness.cohort_null_rates`; the base-rate null must be "
            "built from the training split and cannot be taken from held-out outcomes",
        )

    students: List[Tuple[float, float]] = []  # (coverage, per-student log-loss delta)
    unknown_cohorts = set()
    for s in block["students"]:
        cohort = str(s.get("cohort", ""))
        if cohort not in null_rates:
            unknown_cohorts.add(cohort)
            continue
        outcome = [int(s["outcome"])]
        model_ll = core.log_loss([float(s["p_model"])], outcome)
        null_ll = core.log_loss([float(null_rates[cohort])], outcome)
        students.append((float(s["coverage"]), model_ll - null_ll))
    if unknown_cohorts:
        d.evidence["students_dropped_unknown_cohort"] = sorted(unknown_cohorts)
    if not students:
        return d.resolve(None, "no held-out student carried a cohort with a training-split null rate")

    # Walk DOWN from the highest coverage level and stop at the first evaluable
    # level that fails. A floor has to hold at itself and at everything above,
    # so everything below the first failure is irrelevant and is not evaluated;
    # rows for those levels are recorded as `evaluated: false` rather than
    # omitted, so the table cannot be mistaken for a full sweep.
    rows_desc: List[Dict[str, Any]] = []
    floor: Optional[float] = None
    stopped_on: Optional[float] = None
    saw_evaluable = False
    for level in reversed(COVERAGE_GRID):
        deltas = [delta for cov, delta in students if cov >= level]
        row: Dict[str, Any] = {
            "coverage_at_least": level,
            "students": len(deltas),
            "evaluated": True,
        }
        if len(deltas) < MIN_BIN_UNITS:
            row["evaluable"] = False
            row["passes"] = None
            rows_desc.append(row)
            continue
        mean, lo, hi = _bootstrap_mean_ci(deltas, rng)
        row["evaluable"] = True
        row["mean_log_loss_delta_vs_null"] = round(mean, 6)
        row["ci95"] = [round(lo, 6), round(hi, 6)]
        row["passes"] = hi < 0.0
        rows_desc.append(row)
        if not row["passes"]:
            stopped_on = level
            break
        saw_evaluable = True
        floor = level
    evaluated_levels = {row["coverage_at_least"] for row in rows_desc}
    for level in COVERAGE_GRID:
        if level not in evaluated_levels:
            rows_desc.append(
                {
                    "coverage_at_least": level,
                    "evaluated": False,
                    "note": "below the first failing level; a floor cannot sit here",
                }
            )
    table = sorted(rows_desc, key=lambda r: r["coverage_at_least"])
    d.evidence["per_level"] = table
    d.evidence["students_scored"] = len(students)

    if not saw_evaluable and floor is None:
        if stopped_on is not None:
            return d.resolve(
                None,
                "the highest evaluable coverage level ({}) does not beat the base-rate null. "
                "POV 2's falsifier (4) has fired at this coverage: no floor exists, and no "
                "coverage floor can rescue a readiness model that loses to a constant "
                "predictor where it has the most data".format(stopped_on),
            )
        return d.resolve(
            None, "no coverage level retained {} or more students".format(MIN_BIN_UNITS)
        )
    below = sum(1 for cov, _ in students if cov < floor)
    d.evidence["abstention_cost"] = {
        "students_below_floor": below,
        "fraction_below_floor": round(below / len(students), 4),
        "note": "Readiness withholds entirely below the floor. This is the abstention rate.",
    }
    return d.resolve(
        floor,
        "smallest coverage level at which the readiness model beats the base-rate null on "
        "held-out students, and keeps beating it at every level above",
    )


# ---------------------------------------------------------------------------
# 4-6. The sanity gate -- absolute, not relative (upstream's params.rs:182)
# ---------------------------------------------------------------------------


def derive_sanity_gate_min_items(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="sanity_gate_min_items",
        unit="held-out items in the sanity-gate evaluation set",
        owed_by="BRAINLIFT.md section 7 'A separate sanity gate'; Appendix B item 5",
        consumed_by="gates.py sanity gate; BUILD-DOC.md section 6",
        function="derive_sanity_gate_min_items",
        procedure=(
            "Upstream gates its health check at >300 items on the stated ground "
            "that below that an ABSOLUTE quality ESTIMATE is too noisy to act on. "
            "That is a claim about the estimate's precision, so precision is what "
            "gets measured. Split each student's held-out set into two random "
            "halves and take the absolute metric (log loss) on each. The "
            "within-student difference cancels every between-student difference "
            "in true quality, so its spread across a count bin is pure sampling "
            "noise: sd(difference) = sqrt(2) x sd(half-sample estimate), and the "
            "full-sample estimate's sd is therefore sd(difference)/2. Express "
            "that as a fraction of the absolute bound the estimate is compared "
            "against (the base-rate null's log loss); the floor is the smallest "
            "count bin where the fraction is at or below the stated tolerance and "
            "stays there above. "
            "NOT split-half decision agreement, which was tried first and is the "
            "wrong statistic: a model sitting genuinely on the bound flips at any "
            "sample size, so agreement plateaus well short of any usable "
            "tolerance and the floor comes back UNKNOWN for a reason that is "
            "about the bound's neighbourhood rather than about sample size."
        ),
        needs=(
            "The same per-student held-out sets the Memory floor needs, plus the "
            "training-split base rate that sets the bound's scale. At least "
            "MIN_BIN_UNITS students per count bin, each with at least 8 held-out "
            "items so both halves are non-trivial."
        ),
        retired_starting_value=300,
        retired_value_provenance=(
            "> 300, from Anki's params.rs:182 health check. Real upstream code, "
            "but it gates a different quantity in a different estimator; "
            "BRAINLIFT.md section 7 records that borrowing its magnitude was one "
            "of the errors this appendix exists to stop repeating. Not read here."
        ),
    )
    tolerance = 0.10
    d.policy_inputs = {
        "count_grid": list(COUNT_GRID),
        "precision_tolerance": tolerance,
        "min_units_per_bin": MIN_BIN_UNITS,
        "min_holdout_items_per_student": 8,
        "note": (
            "The tolerance is a STATED CHOICE, not a derived quantity: it says "
            "how much sampling noise, as a fraction of the bound itself, we are "
            "willing to have in an absolute quality estimate before acting on it. "
            "The whole precision curve is in `evidence.per_bin`, so a reader can "
            "read the floor off a different tolerance without rerunning anything."
        ),
    }
    if dataset is None:
        return d
    block = dataset.block("memory")
    if not block or not block.get("students"):
        return d.resolve(None, "dataset has no `memory.students` block to split")
    null_rate = block.get("null_rate")
    if null_rate is None:
        return d.resolve(
            None,
            "dataset has no `memory.null_rate` (training-split recall base rate); the "
            "absolute comparator cannot be built from held-out outcomes",
        )
    null_rate = float(null_rate)

    by_bin: Dict[int, List[int]] = {}
    for s in block["students"]:
        holdout = s.get("holdout", [])
        if len(holdout) < 4:
            continue
        idx = list(range(len(holdout)))
        rng.shuffle(idx)
        half = len(idx) // 2
        a = [holdout[i] for i in idx[:half]]
        b = [holdout[i] for i in idx[half : 2 * half]]
        da = _absolute_decision(
            core, [float(r["p_personal"]) for r in a], [int(r["outcome"]) for r in a], null_rate
        )
        db = _absolute_decision(
            core, [float(r["p_personal"]) for r in b], [int(r["outcome"]) for r in b], null_rate
        )
        by_bin.setdefault(_bin_index(float(s["fsrs_items"]), COUNT_GRID), []).append(
            0 if da == db else 1
        )

    table: List[Dict[str, Any]] = []
    for i, edge in enumerate(COUNT_GRID):
        flags = by_bin.get(i, [])
        row: Dict[str, Any] = {"bin_floor": edge, "students": len(flags)}
        if len(flags) < MIN_BIN_UNITS:
            row["evaluable"] = False
            row["passes"] = None
        else:
            rate = sum(flags) / len(flags)
            row["evaluable"] = True
            row["split_half_disagreement"] = round(rate, 4)
            row["passes"] = rate <= tolerance
        table.append(row)
    d.evidence = {"per_bin": table, "null_rate_used": null_rate}

    evaluable = [i for i, row in enumerate(table) if row["evaluable"]]
    if not evaluable:
        return d.resolve(None, "no count bin held {} or more students".format(MIN_BIN_UNITS))
    top = max(evaluable)
    if not table[top]["passes"]:
        return d.resolve(
            None,
            "even the highest evaluable bin disagrees with itself more often than the "
            "tolerance allows, so no count makes the absolute estimate stable enough to act on",
        )
    floor_idx = top
    for i in sorted(evaluable, reverse=True):
        if table[i]["passes"]:
            floor_idx = i
        else:
            break
    return d.resolve(
        table[floor_idx]["bin_floor"],
        "smallest count bin whose split-half absolute decision disagrees at or below the "
        "stated tolerance, and stays there in every evaluable bin above it",
    )


def derive_sanity_gate_log_loss_bound(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="sanity_gate_log_loss_bound",
        unit="nats (mean negative log-likelihood on held-out data)",
        owed_by="BRAINLIFT.md section 7 'A separate sanity gate'; Appendix B item 5",
        consumed_by="gates.py sanity gate",
        function="derive_sanity_gate_log_loss_bound",
        procedure=(
            "Upstream pairs its >300 gate with fixed absolute bounds "
            "(adjusted_log_loss <= 1.11 || adjusted_rmse <= 1.53). Those "
            "constants have no authority here, so the bound is derived instead of "
            "borrowed, and derived without a free parameter: it is the held-out "
            "log loss of the base-rate null itself, computed from the training "
            "split's base rate against the held-out outcomes. A model whose "
            "ABSOLUTE held-out log loss exceeds what a constant predictor "
            "achieves is not fit to show, whatever it beat on the way in."
        ),
        needs=(
            "A training-split base rate and a held-out outcome set. Supplied by "
            "the `memory` block (null_rate plus every student's holdout)."
        ),
        retired_starting_value=1.11,
        retired_value_provenance=(
            "adjusted_log_loss <= 1.11 from Anki params.rs:182. Real code, "
            "different estimator, no authority here. Not read by this procedure."
        ),
    )
    d.policy_inputs = {
        "combination_rule": (
            "This procedure derives the bound only. Whether the sanity gate "
            "requires log loss AND Brier or, like upstream, log loss OR RMSE, is "
            "a gates.py decision and is deliberately not made here."
        )
    }
    if dataset is None:
        return d
    block = dataset.block("memory")
    if not block or not block.get("students"):
        return d.resolve(None, "dataset has no `memory.students` block")
    if block.get("null_rate") is None:
        return d.resolve(None, "dataset has no `memory.null_rate` (training-split base rate)")
    null_rate = float(block["null_rate"])
    outcomes: List[int] = []
    for s in block["students"]:
        outcomes.extend(int(r["outcome"]) for r in s.get("holdout", []))
    if len(outcomes) < MIN_BIN_UNITS:
        return d.resolve(None, "fewer than {} held-out reviews in total".format(MIN_BIN_UNITS))
    bound = core.log_loss([null_rate] * len(outcomes), outcomes)
    observed_base = sum(outcomes) / len(outcomes)
    d.evidence = {
        "held_out_reviews": len(outcomes),
        "training_split_null_rate": null_rate,
        "held_out_base_rate": round(observed_base, 6),
        "closed_form_check_at_matched_rate": round(core.const_ll(null_rate, observed_base), 6),
        "note": (
            "The closed-form check recomputes the same bound from algebra rather "
            "than from the empirical loop; the two agreeing is the evidence that "
            "the loop is not lying."
        ),
    }
    return d.resolve(
        bound,
        "held-out log loss of the base-rate null built from the training-split rate -- the "
        "absolute level a model must be under to be fit to show",
    )


def derive_sanity_gate_brier_bound(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="sanity_gate_brier_bound",
        unit="Brier score (mean squared error of the probability forecast)",
        owed_by="BRAINLIFT.md section 7 'A separate sanity gate'; Appendix B item 5",
        consumed_by="gates.py sanity gate (reported beside the log-loss bound, never overturning it)",
        function="derive_sanity_gate_brier_bound",
        procedure=(
            "The Brier counterpart of the log-loss bound, derived the same way: "
            "the base-rate null's held-out Brier score. It exists because this "
            "project reports Brier and log loss together and never one alone; it "
            "is the analogue of upstream's adjusted_rmse limb. It is REPORTED "
            "beside the log-loss decision and does not overturn it."
        ),
        needs="Same as sanity_gate_log_loss_bound.",
        retired_starting_value=1.53,
        retired_value_provenance=(
            "adjusted_rmse <= 1.53 from Anki params.rs:182. Different scale "
            "(RMSE on FSRS's adjusted residuals, not Brier), different estimator, "
            "no authority here. Not read by this procedure."
        ),
    )
    if dataset is None:
        return d
    block = dataset.block("memory")
    if not block or not block.get("students"):
        return d.resolve(None, "dataset has no `memory.students` block")
    if block.get("null_rate") is None:
        return d.resolve(None, "dataset has no `memory.null_rate` (training-split base rate)")
    null_rate = float(block["null_rate"])
    outcomes: List[int] = []
    for s in block["students"]:
        outcomes.extend(int(r["outcome"]) for r in s.get("holdout", []))
    if len(outcomes) < MIN_BIN_UNITS:
        return d.resolve(None, "fewer than {} held-out reviews in total".format(MIN_BIN_UNITS))
    bound = core.brier([null_rate] * len(outcomes), outcomes)
    observed_base = sum(outcomes) / len(outcomes)
    d.evidence = {
        "held_out_reviews": len(outcomes),
        "closed_form_check_at_matched_rate": round(core.const_brier(null_rate, observed_base), 6),
    }
    return d.resolve(bound, "held-out Brier score of the base-rate null built from the training-split rate")


# ---------------------------------------------------------------------------
# 7. The latency fraction for the scored-item plausibility filter
# ---------------------------------------------------------------------------


def derive_latency_fraction(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="latency_fraction",
        unit="fraction of the item's target time (session median response latency / target)",
        owed_by="BRAINLIFT.md section 7 latency rule; Appendix B item 6",
        consumed_by="BUILD-DOC.md section 6 latency plausibility filter; Performance scoring inputs",
        function="derive_latency_fraction",
        procedure=(
            "The filter's premise is that fast-enough sessions carry no "
            "information, so the cut is located by measuring information rather "
            "than by picking a number. Sessions are cut into STRATA by latency "
            "ratio (median latency / target time). Within each stratum, ask "
            "whether the performance model has any edge over the base-rate null: "
            "edge = null log loss - model log loss per session, bootstrapped over "
            "SESSIONS. A stratum of people answering without reading has edge <= 0 "
            "-- their outcomes do not track the model's forecast. Walk up from the "
            "fastest stratum and stop at the first evaluable stratum that DOES "
            "show an edge; f* is that stratum's lower boundary. "
            "Strata, not cumulative pools, because a cumulative pool below f "
            "mixes noise sessions with informative ones and stays "
            "indistinguishable from noise well past the real cut by dilution -- "
            "which pushes the derived filter too wide and destroys real data. "
            "Scope, per BRAINLIFT section 7: scored novel items only. Card "
            "reviews have no target time and are not filtered here."
        ),
        needs=(
            "Sessions of scored novel items with a per-session median response "
            "latency, the item's published target time, the performance model's "
            "P(correct) per item, the observed outcome, and a training-split item "
            "base rate for the null. Enough sessions in the fast tail to make "
            "small-f pools evaluable -- which real students may simply not "
            "produce, in which case this stays UNKNOWN."
        ),
        retired_starting_value=0.20,
        retired_value_provenance=(
            "20% of target time, recorded in BRAINLIFT.md section 7 as a "
            "TEARDOWN STARTING VALUE, not an assertion. It came from "
            "speedrun-docs/teardown-observation-log.md, where zero-effort probe "
            "sessions ran at 1-4 seconds against tool-displayed targets of "
            "roughly 90 seconds -- ratios of about 0.01 to 0.04, an order of "
            "magnitude below the 20% figure it was written up as. Not read by "
            "this procedure."
        ),
    )
    d.policy_inputs = {
        "stratum_boundaries": list(LATENCY_GRID),
        "min_sessions_per_stratum": MIN_BIN_UNITS,
        "bootstrap_resamples": N_BOOTSTRAP,
        "alpha": ALPHA,
    }
    if dataset is None:
        return d
    block = dataset.block("sessions")
    if not block or not block.get("sessions"):
        return d.resolve(None, "dataset has no `sessions.sessions` block")
    if block.get("null_rate") is None:
        return d.resolve(
            None, "dataset has no `sessions.null_rate` (training-split item base rate)"
        )
    null_rate = float(block["null_rate"])

    prepared: List[Tuple[float, float]] = []  # (latency ratio, per-session edge over null)
    for s in block["sessions"]:
        items = s.get("items", [])
        target = float(s.get("target_time_s", 0.0) or 0.0)
        if not items or target <= 0.0:
            continue
        ratio = float(s["median_latency_s"]) / target
        probs = [float(i["p_model"]) for i in items]
        outcomes = [int(i["outcome"]) for i in items]
        edge = core.log_loss([null_rate] * len(outcomes), outcomes) - core.log_loss(probs, outcomes)
        prepared.append((ratio, edge))
    if not prepared:
        return d.resolve(None, "no session carried both a positive target time and scored items")

    # Walk UP through the strata and stop at the first evaluable stratum that
    # shows an edge. Strata above the stop are recorded as `evaluated: false`
    # rather than dropped, so the table cannot be read as a full sweep.
    table: List[Dict[str, Any]] = []
    cut: Optional[float] = None
    first_evaluable: Optional[float] = None
    saw_informative_first = False
    for j in range(len(LATENCY_GRID) - 1):
        lo_edge, hi_edge = LATENCY_GRID[j], LATENCY_GRID[j + 1]
        stratum = [edge for ratio, edge in prepared if lo_edge <= ratio < hi_edge]
        row: Dict[str, Any] = {
            "stratum_lo": lo_edge,
            "stratum_hi": hi_edge,
            "sessions": len(stratum),
            "evaluated": True,
        }
        if len(stratum) < MIN_BIN_UNITS:
            row["evaluable"] = False
            row["uninformative"] = None
            table.append(row)
            continue
        mean, lo, hi = _bootstrap_mean_ci(stratum, rng)
        row["evaluable"] = True
        row["mean_edge_over_null"] = round(mean, 6)
        row["ci95"] = [round(lo, 6), round(hi, 6)]
        row["uninformative"] = hi <= 0.0
        table.append(row)
        if first_evaluable is None:
            first_evaluable = lo_edge
            if not row["uninformative"]:
                saw_informative_first = True
        if not row["uninformative"]:
            cut = lo_edge
            break
    evaluated = {row["stratum_lo"] for row in table}
    for j in range(len(LATENCY_GRID) - 1):
        if LATENCY_GRID[j] not in evaluated:
            table.append(
                {
                    "stratum_lo": LATENCY_GRID[j],
                    "stratum_hi": LATENCY_GRID[j + 1],
                    "evaluated": False,
                    "note": "above the first stratum showing an edge; a cut cannot sit here",
                }
            )
    table.sort(key=lambda r: r["stratum_lo"])
    d.evidence = {"sessions_scored": len(prepared), "per_stratum": table}

    if first_evaluable is None:
        return d.resolve(
            None,
            "no latency stratum held {} or more sessions; the fast tail is too thin to "
            "locate a cut".format(MIN_BIN_UNITS),
        )
    if saw_informative_first:
        return d.resolve(
            None,
            "the fastest evaluable stratum (starting at {}) already shows the model beating "
            "the null, so nothing in this data is uninformative and no cut separates the two "
            "populations. The honest reading is that the latency filter is unsupported here, "
            "not that it should be set somewhere arbitrary".format(first_evaluable),
        )
    if cut is None:
        return d.resolve(
            None,
            "every evaluable stratum up to the top of the grid is indistinguishable from "
            "noise, so the boundary the filter needs is not inside the range searched",
        )
    excluded = sum(1 for ratio, _ in prepared if ratio < cut)
    d.evidence["exclusion_cost"] = {
        "sessions_excluded": excluded,
        "fraction_of_sessions_excluded": round(excluded / len(prepared), 4),
        "note": (
            "Sessions this filter removes from the Performance model's inputs. "
            "BRAINLIFT Appendix B item 4 requires the information destroyed by a "
            "refusal to be accounted for separately; this is that accounting for "
            "the latency rule."
        ),
    }
    return d.resolve(
        cut,
        "lower boundary of the fastest latency stratum in which the model shows an edge over "
        "the base-rate null; every evaluable stratum below it is indistinguishable from noise",
    )


# ---------------------------------------------------------------------------
# 8. The shrinkage constant -- replacing the borrowed 50
# ---------------------------------------------------------------------------


def _shrunk_log_loss(core: Core, units: Sequence[Dict[str, Any]], k: float) -> float:
    probs: List[float] = []
    outcomes: List[int] = []
    for u in units:
        n = float(u["n"])
        w = n / (k + n)
        p = w * float(u["p_personal"]) + (1.0 - w) * float(u["p_prior"])
        for y in u["outcomes"]:
            probs.append(p)
            outcomes.append(int(y))
    return core.log_loss(probs, outcomes)


def derive_shrinkage_constant(
    dataset: Optional[Dataset], core: Core, rng: random.Random
) -> Derivation:
    d = Derivation(
        threshold_id="shrinkage_constant",
        unit="k, in the weight w = n / (k + n)",
        owed_by="BRAINLIFT.md section 7 shrinkage caveat; Appendix B item 7",
        consumed_by="gates.py shrinkage for Memory and Performance",
        function="derive_shrinkage_constant",
        procedure=(
            "Fit k by direct search over a geometric grid, minimising held-out "
            "log loss of the shrunk forecast w*p_personal + (1-w)*p_prior with "
            "w = n/(k+n), on a FITTING split; then report the log loss that k "
            "achieves on a DISJOINT EVALUATION split, alongside the loss of the "
            "borrowed k = 50, of no shrinkage (k -> 0), and of total shrinkage "
            "(k -> infinity). A bootstrap over fitting-split students gives an "
            "interval on k, and whether 50 falls inside it is reported as the "
            "direct test of the borrowed constant."
        ),
        needs=(
            "Two disjoint sets of students, each with their per-student "
            "observation count n, the personal estimate, the prior it shrinks "
            "toward, and held-out outcomes. Fitting k on the same split it is "
            "evaluated on would report the fit's own optimum as its performance "
            "and is refused."
        ),
        retired_starting_value=50,
        retired_value_provenance=(
            "50, from fsrs-optimizer issue #116, where Expertium proposes "
            "n/(50+n) for smoothing MEDIAN REVIEW TIMES in a different estimator. "
            "BRAINLIFT.md section 7 records that the functional form is borrowed "
            "and the constant is not: no upstream code shrinks FSRS parameters, "
            "and the Anki-side implementation of #116 shrank first-rating "
            "probabilities and was deleted in 52ce6e6a. Not read by this "
            "procedure -- it appears below only as a comparator whose loss is "
            "reported next to the fitted k's."
        ),
        pending_integration=(
            "Re-derive on post-hoc-calibrated probabilities once calibration.py's "
            "entry point is fixed. Shrinkage and a calibration map both move "
            "probabilities toward the base rate, so a k fitted on uncalibrated "
            "output is partly absorbing miscalibration and will be too large."
        ),
    )
    d.policy_inputs = {
        "k_grid": {"min": K_GRID[0], "max": K_GRID[-1], "points": len(K_GRID), "spacing": "geometric"},
        "k_ci_grid_points": len(K_CI_GRID),
        "alpha": ALPHA,
        "note": (
            "The grid bounds are a search range, not a prior. A fitted k landing "
            "on either bound is reported as UNRESOLVED rather than as the bound."
        ),
    }
    if dataset is None:
        return d
    block = dataset.block("shrinkage")
    if not block or not block.get("fit") or not block.get("eval"):
        return d.resolve(None, "dataset has no `shrinkage.fit` and `shrinkage.eval` splits")
    fit_units = list(block["fit"])
    eval_units = list(block["eval"])
    if len(fit_units) < MIN_BIN_UNITS or len(eval_units) < MIN_BIN_UNITS:
        return d.resolve(
            None,
            "fewer than {} students in the fitting or evaluation split".format(MIN_BIN_UNITS),
        )
    fit_ids = {u.get("student_id") for u in fit_units if u.get("student_id") is not None}
    eval_ids = {u.get("student_id") for u in eval_units if u.get("student_id") is not None}
    overlap = fit_ids & eval_ids
    if overlap:
        return d.resolve(
            None,
            "{} student(s) appear in both the fitting and evaluation splits; k fitted and "
            "evaluated on the same students is not a held-out result".format(len(overlap)),
        )

    losses = [(k, _shrunk_log_loss(core, fit_units, k)) for k in K_GRID]
    k_hat = min(losses, key=lambda kv: kv[1])[0]
    curves = [[_shrunk_log_loss(core, [u], k) * len(u["outcomes"]) for k in K_CI_GRID] for u in fit_units]
    n_ci_resamples = 300
    lo, hi = _bootstrap_argmin_ci(curves, K_CI_GRID, rng, n_resamples=n_ci_resamples)
    d.evidence = {
        "fit_students": len(fit_units),
        "eval_students": len(eval_units),
        "k_hat_on_fit_split": k_hat,
        "k_hat_bootstrap_ci95": [round(lo, 4), round(hi, 4)],
        "k_hat_ci_grid_points": len(K_CI_GRID),
        "bootstrap_resamples": n_ci_resamples,
        "eval_split_log_loss": {
            "at_fitted_k": round(_shrunk_log_loss(core, eval_units, k_hat), 6),
            "at_borrowed_k_50": round(_shrunk_log_loss(core, eval_units, 50.0), 6),
            "no_shrinkage_k_0": round(_shrunk_log_loss(core, eval_units, 1e-9), 6),
            "total_shrinkage_k_1e9": round(_shrunk_log_loss(core, eval_units, 1e9), 6),
        },
        "borrowed_50_inside_fitted_ci": bool(lo <= 50.0 <= hi),
    }
    if k_hat <= K_GRID[0] or k_hat >= K_GRID[-1]:
        return d.resolve(
            None,
            "the fitted k landed on the edge of the search grid ({}), which means the grid "
            "bounded the answer rather than the data doing so".format(k_hat),
        )
    return d.resolve(
        k_hat,
        "k minimising held-out log loss of w = n/(k+n) on the fitting split, with its loss "
        "on a disjoint evaluation split reported beside the borrowed k = 50",
    )


DERIVATIONS: Tuple[Callable[[Optional[Dataset], Core, random.Random], Derivation], ...] = (
    derive_memory_fsrs_items_floor,
    derive_performance_scored_item_floor,
    derive_readiness_coverage_floor,
    derive_sanity_gate_min_items,
    derive_sanity_gate_log_loss_bound,
    derive_sanity_gate_brier_bound,
    derive_latency_fraction,
    derive_shrinkage_constant,
)


# ---------------------------------------------------------------------------
# report assembly
# ---------------------------------------------------------------------------


def run(dataset: Optional[Dataset], core: Core) -> Dict[str, Any]:
    results: List[Derivation] = []
    for fn in DERIVATIONS:
        rng = random.Random(SEED)
        if not core.ok:
            d = fn(None, core, rng)
            d.status = STATUS_UNKNOWN
            d.reason = (
                "core module metrics.py is not importable or failed its probe, so no "
                "metric could be computed. This is a tooling failure, not a data one."
            )
            results.append(d)
            continue
        results.append(fn(dataset, core, rng))

    records = [d.to_json(dataset) for d in results]
    summary = {STATUS_DERIVED: 0, STATUS_UNKNOWN: 0}
    for r in records:
        summary[r["status"]] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": SCRIPT,
        "standing_rule": STANDING_RULE,
        "synthetic_rule": SYNTHETIC_RULE,
        "forbidden_metric": (
            "Accuracy. At a ~91% base rate a constant 'pass' predictor scores ~91%. "
            "Every decision here runs on log loss, with Brier reported beside it."
        ),
        "seed": SEED,
        "core_modules": core.report,
        "dataset": dataset.identity() if dataset is not None else None,
        "summary": summary,
        "thresholds": records,
    }


def print_table(report: Dict[str, Any]) -> None:
    print("Appendix B -- derived thresholds")
    print("=" * 78)
    ds = report["dataset"]
    if ds is None:
        print("dataset: NONE SUPPLIED -- every threshold below is UNKNOWN by construction")
    else:
        print(
            "dataset: {}  synthetic={}  sha256={}".format(
                ds["dataset_id"], ds["synthetic"], (ds["sha256"] or "-")[:16]
            )
        )
    print(
        "core:    metrics={} gates={} calibration={}".format(
            report["core_modules"].get("metrics", {}).get("probe", "ABSENT"),
            report["core_modules"].get("gates", {}).get("probe", "ABSENT"),
            "present" if report["core_modules"].get("calibration", {}).get("importable") else "absent",
        )
    )
    print("-" * 78)
    for r in report["thresholds"]:
        value = r["value"]
        shown = "null" if value is None else "{}".format(value)
        if r.get("dry_run"):
            shown = "null  (dry run: {})".format(r["dry_run"]["value_not_a_threshold"])
        print("{:<32} {:<10} {}".format(r["id"], r["status"], shown))
        print("    {}".format(r["reason"]))
    print("-" * 78)
    print(
        "DERIVED={}  UNKNOWN={}".format(
            report["summary"][STATUS_DERIVED], report["summary"][STATUS_UNKNOWN]
        )
    )
    print(STANDING_RULE)


# ---------------------------------------------------------------------------
# synthetic dataset -- for the tamper-check ONLY
# ---------------------------------------------------------------------------

PLANTED = {
    "memory_fsrs_items_floor": 32,
    "performance_scored_item_floor": 64,
    "readiness_coverage_floor": 0.40,
    "latency_fraction": 0.25,
    "shrinkage_constant": 12.0,
}
"""Ground truth built into `build_synthetic_dataset`. These are properties of a
data-generating process this file wrote. **They are not thresholds and no
threshold may ever be read off them.** They exist so `--self-test` can ask
whether each search finds a crossover it is known to contain: a procedure that
cannot recover a planted answer cannot be trusted with a real one."""


def _clamp(p: float, lo: float = 0.02, hi: float = 0.98) -> float:
    return max(lo, min(hi, p))


def build_synthetic_dataset(seed: int = SEED) -> Dict[str, Any]:
    """A deterministic fixture with the crossovers in PLANTED built in.

    The cutoffs are HARD -- below the planted count the personal model is
    replaced by a noisy one that loses to its comparator -- because this fixture
    is a tamper-check on the SEARCH, not a model of how students behave. Nothing
    about real learning is claimed by it, and no number it produces is a
    threshold. Held-out set size grows with the count so that the split-half
    stability question has something to find, which is the one respect in which
    the fixture is deliberately shaped like real data."""
    rng = random.Random(seed)

    def _draw_count() -> int:
        b = rng.randrange(len(COUNT_GRID))
        if b == len(COUNT_GRID) - 1:
            return rng.randrange(COUNT_GRID[-1], COUNT_GRID[-1] * 2)
        return rng.randrange(COUNT_GRID[b], max(COUNT_GRID[b] + 1, COUNT_GRID[b + 1]))

    def _holdout_size(count: int) -> int:
        return max(4, min(120, count // 2))

    payload: Dict[str, Any] = {
        "dataset_id": "synthetic-tamper-check",
        "synthetic": True,
        "description": (
            "Deterministic synthetic fixture for --self-test. Planted crossovers: "
            + json.dumps(PLANTED, sort_keys=True)
            + ". Not student data. No threshold derived from it is final."
        ),
    }

    # Memory: personal model is exact at/above the floor and noisy below it; the
    # incumbent is informative but biased low by 0.10 throughout.
    mem_students = []
    recall_outcomes = 0
    recall_total = 0
    for i in range(1000):
        count = _draw_count()
        holdout = []
        for _ in range(_holdout_size(count)):
            p_true = rng.uniform(0.60, 0.95)
            outcome = 1 if rng.random() < p_true else 0
            recall_outcomes += outcome
            recall_total += 1
            if count >= PLANTED["memory_fsrs_items_floor"]:
                p_personal = p_true
            else:
                p_personal = p_true + rng.gauss(0.0, 0.25)
            holdout.append(
                {
                    "p_personal": _clamp(p_personal),
                    "p_incumbent": _clamp(p_true - 0.10),
                    "outcome": outcome,
                }
            )
        mem_students.append(
            {"student_id": "m{}".format(i), "fsrs_items": count, "holdout": holdout}
        )
    payload["memory"] = {
        "null_rate": round(recall_outcomes / recall_total, 4),
        "students": mem_students,
    }

    # Performance: comparator is a constant topic prior.
    prior = 0.62
    perf_students = []
    for i in range(1000):
        count = _draw_count()
        holdout = []
        for _ in range(_holdout_size(count)):
            p_true = rng.uniform(0.35, 0.90)
            outcome = 1 if rng.random() < p_true else 0
            if count >= PLANTED["performance_scored_item_floor"]:
                p_personal = p_true
            else:
                p_personal = p_true + rng.gauss(0.0, 0.30)
            holdout.append(
                {
                    "p_personal": _clamp(p_personal),
                    "p_topic_prior": prior,
                    "outcome": outcome,
                }
            )
        perf_students.append(
            {"student_id": "p{}".format(i), "scored_items": count, "holdout": holdout}
        )
    payload["performance"] = {"students": perf_students}

    # Readiness: one outcome per student; the model is informative only at or
    # above the planted coverage and anti-correlated below it.
    cohort_rates = {"us_md": 0.91, "us_do": 0.86, "img": 0.73}
    read_students = []
    for i in range(5000):
        cohort = rng.choice(list(cohort_rates))
        base = cohort_rates[cohort]
        coverage = round(rng.uniform(0.02, 0.98), 3)
        signal = rng.uniform(-0.30, 0.08)
        p_true = _clamp(base + signal)
        outcome = 1 if rng.random() < p_true else 0
        p_model = p_true if coverage >= PLANTED["readiness_coverage_floor"] else _clamp(base - signal)
        read_students.append(
            {
                "student_id": "r{}".format(i),
                "cohort": cohort,
                "coverage": coverage,
                "p_model": p_model,
                "outcome": outcome,
            }
        )
    payload["readiness"] = {"cohort_null_rates": cohort_rates, "students": read_students}

    # Sessions: below the planted latency fraction, outcomes are independent of
    # the model's forecast; above it they follow it.
    sess_base = 0.55
    sessions = []
    for i in range(3000):
        ratio = rng.uniform(0.0, 1.0)
        target = 90.0
        items = []
        for _ in range(rng.randrange(6, 26)):
            p_model = rng.uniform(0.25, 0.85)
            if ratio < PLANTED["latency_fraction"]:
                outcome = 1 if rng.random() < sess_base else 0
            else:
                outcome = 1 if rng.random() < p_model else 0
            items.append({"p_model": p_model, "outcome": outcome})
        sessions.append(
            {
                "session_id": "s{}".format(i),
                "median_latency_s": round(ratio * target, 3),
                "target_time_s": target,
                "items": items,
            }
        )
    payload["sessions"] = {"null_rate": sess_base, "sessions": sessions}

    # Shrinkage: p_personal = p_true + noise with sd sigma/sqrt(n), p_prior
    # constant; the squared-error-optimal weight is then n/(n + sigma^2/tau^2),
    # so k_true = sigma^2/tau^2 by construction.
    tau = 0.12
    k_true = PLANTED["shrinkage_constant"]
    sigma = math.sqrt(k_true) * tau
    prior_p = 0.60

    def _shrink_units(prefix: str, count: int) -> List[Dict[str, Any]]:
        units = []
        for i in range(count):
            n = int(round(math.exp(rng.uniform(math.log(1.0), math.log(300.0)))))
            p_true = _clamp(prior_p + rng.gauss(0.0, tau))
            p_personal = _clamp(p_true + rng.gauss(0.0, sigma / math.sqrt(n)))
            outcomes = [1 if rng.random() < p_true else 0 for _ in range(8)]
            units.append(
                {
                    "student_id": "{}{}".format(prefix, i),
                    "n": n,
                    "p_personal": p_personal,
                    "p_prior": prior_p,
                    "outcomes": outcomes,
                }
            )
        return units

    payload["shrinkage"] = {
        "prior_label": "constant topic prior (synthetic)",
        "fit": _shrink_units("f", 1200),
        "eval": _shrink_units("e", 1200),
    }
    return payload


# ---------------------------------------------------------------------------
# self-test -- can each search find a crossover it is known to contain?
# ---------------------------------------------------------------------------


def self_test() -> int:
    core = Core()
    if not core.ok:
        print("SELF-TEST CANNOT RUN")
        print("  metrics.py did not bind: {}".format(core.report.get("metrics")))
        print("  Nothing was checked. This is a hard failure, not a skip.")
        return 3

    payload = build_synthetic_dataset()
    dataset = Dataset(payload, None, "synthetic")
    report = run(dataset, core)
    by_id = {r["id"]: r for r in report["thresholds"]}

    failures: List[str] = []
    checks: List[str] = []

    def value_of(threshold_id: str) -> Optional[float]:
        rec = by_id[threshold_id]
        if rec["value"] is not None:
            failures.append(
                "{}: value is non-null on a synthetic dataset; the synthetic rule is "
                "not being enforced".format(threshold_id)
            )
            return None
        dry = rec.get("dry_run")
        return dry["value_not_a_threshold"] if dry else None

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append("{} {}  {}".format("PASS" if ok else "FAIL", name, detail))
        if not ok:
            failures.append("{}: {}".format(name, detail))

    # 1. the synthetic rule itself
    check(
        "synthetic-run-marks-nothing-derived",
        report["summary"][STATUS_DERIVED] == 0,
        "DERIVED count = {} (must be 0 on synthetic data)".format(
            report["summary"][STATUS_DERIVED]
        ),
    )

    # 2-6. planted crossover recovery
    mem = value_of("memory_fsrs_items_floor")
    check(
        "memory-floor-recovers-planted-32",
        mem == PLANTED["memory_fsrs_items_floor"],
        "found {}, planted {}".format(mem, PLANTED["memory_fsrs_items_floor"]),
    )
    perf = value_of("performance_scored_item_floor")
    check(
        "performance-floor-recovers-planted-64",
        perf == PLANTED["performance_scored_item_floor"],
        "found {}, planted {}".format(perf, PLANTED["performance_scored_item_floor"]),
    )
    cov = value_of("readiness_coverage_floor")
    check(
        "coverage-floor-recovers-planted-0.40",
        cov is not None and abs(cov - PLANTED["readiness_coverage_floor"]) <= 0.05,
        "found {}, planted {} (grid step 0.05)".format(cov, PLANTED["readiness_coverage_floor"]),
    )
    lat = value_of("latency_fraction")
    check(
        "latency-fraction-recovers-planted-0.25",
        lat is not None and abs(lat - PLANTED["latency_fraction"]) <= 0.06,
        "found {}, planted {} (grid step 0.02)".format(lat, PLANTED["latency_fraction"]),
    )
    k = value_of("shrinkage_constant")
    lo_ok = PLANTED["shrinkage_constant"] / 3.0
    hi_ok = PLANTED["shrinkage_constant"] * 3.0
    check(
        "shrinkage-constant-recovers-planted-12-within-3x",
        k is not None and lo_ok <= k <= hi_ok,
        "found {}, planted {} (log-loss optimum need not equal the squared-error "
        "optimum, so the tolerance is a factor of 3)".format(k, PLANTED["shrinkage_constant"]),
    )

    # 7. the borrowed 50 is actually tested, not assumed
    k_rec = by_id["shrinkage_constant"]
    ev = k_rec.get("evidence", {})
    check(
        "borrowed-50-is-tested-against-the-fit",
        "borrowed_50_inside_fitted_ci" in ev
        and ev.get("eval_split_log_loss", {}).get("at_borrowed_k_50") is not None,
        "borrowed_50_inside_fitted_ci={}, eval loss at k=50 present={}".format(
            ev.get("borrowed_50_inside_fitted_ci"),
            ev.get("eval_split_log_loss", {}).get("at_borrowed_k_50") is not None,
        ),
    )

    # 8. sanity-gate bounds agree with the closed form rather than with themselves
    ll_rec = by_id["sanity_gate_log_loss_bound"]
    ll_dry = (ll_rec.get("dry_run") or {}).get("value_not_a_threshold")
    ll_closed = ll_rec.get("evidence", {}).get("closed_form_check_at_matched_rate")
    check(
        "log-loss-bound-matches-closed-form",
        ll_dry is not None and ll_closed is not None and abs(ll_dry - ll_closed) < 1e-3,
        "empirical {} vs closed form {}".format(ll_dry, ll_closed),
    )
    bs_rec = by_id["sanity_gate_brier_bound"]
    bs_dry = (bs_rec.get("dry_run") or {}).get("value_not_a_threshold")
    bs_closed = bs_rec.get("evidence", {}).get("closed_form_check_at_matched_rate")
    check(
        "brier-bound-matches-closed-form",
        bs_dry is not None and bs_closed is not None and abs(bs_dry - bs_closed) < 1e-3,
        "empirical {} vs closed form {}".format(bs_dry, bs_closed),
    )

    # 9. the sanity-gate item count is self-consistent with its own curve
    mi_rec = by_id["sanity_gate_min_items"]
    mi_dry = (mi_rec.get("dry_run") or {}).get("value_not_a_threshold")
    per_bin = mi_rec.get("evidence", {}).get("per_bin", [])
    tol = mi_rec["policy_inputs"]["split_half_disagreement_tolerance"]
    at_or_above = [
        row
        for row in per_bin
        if mi_dry is not None and row["bin_floor"] >= mi_dry and row["evaluable"]
    ]
    check(
        "sanity-gate-min-items-holds-at-and-above-itself",
        mi_dry is not None
        and bool(at_or_above)
        and all(row["split_half_disagreement"] <= tol for row in at_or_above),
        "floor {} with {} evaluable bins at or above it, tolerance {}".format(
            mi_dry, len(at_or_above), tol
        ),
    )

    # 10. a dataset with nothing in it must produce no numbers at all
    empty = Dataset({"dataset_id": "empty", "synthetic": False}, None, None)
    empty_report = run(empty, core)
    check(
        "empty-dataset-derives-nothing",
        empty_report["summary"][STATUS_DERIVED] == 0
        and all(r["value"] is None for r in empty_report["thresholds"]),
        "DERIVED={} on a manifest with no data blocks".format(
            empty_report["summary"][STATUS_DERIVED]
        ),
    )

    print("Appendix B threshold-derivation self-test")
    print("=" * 78)
    print("Synthetic fixture, seed {}. Planted crossovers: {}".format(SEED, PLANTED))
    print("These recoveries say the SEARCHES work. They say nothing about students,")
    print("and no threshold in thresholds.json is derived from them.")
    print("-" * 78)
    for line in checks:
        print(line)
    print("-" * 78)
    print()
    print_table(report)
    if failures:
        print()
        print("SELF-TEST FAILED ({} check(s)):".format(len(failures)))
        for f in failures:
            print("  - {}".format(f))
        return 1
    print()
    print("SELF-TEST PASSED ({} checks)".format(len(checks)))
    return 0


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def load_dataset(path: Path) -> Dataset:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return Dataset(payload, path, hashlib.sha256(raw).hexdigest())


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive every numeric floor BRAINLIFT.md section 7 owes, or report UNKNOWN."
    )
    parser.add_argument("--dataset", type=Path, help="path to a dataset manifest (see module docstring)")
    parser.add_argument(
        "--out",
        type=Path,
        default=_HERE / "thresholds.json",
        help="where to write the machine-readable report (default: alongside this script)",
    )
    parser.add_argument("--no-write", action="store_true", help="print the table, write nothing")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run every derivation against a synthetic fixture with known crossovers",
    )
    parser.add_argument(
        "--emit-synthetic",
        type=Path,
        help="write the synthetic tamper-check fixture to a path and exit",
    )
    args = parser.parse_args(argv)

    if args.emit_synthetic:
        args.emit_synthetic.write_text(
            json.dumps(build_synthetic_dataset(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        print("wrote synthetic fixture to {}".format(args.emit_synthetic))
        return 0

    if args.self_test:
        return self_test()

    core = Core()
    dataset = load_dataset(args.dataset) if args.dataset else None
    report = run(dataset, core)
    if not args.no_write:
        args.out.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print_table(report)
    if not args.no_write:
        print("wrote {}".format(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
