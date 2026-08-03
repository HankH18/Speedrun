# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Retrieval comparison, three arms (BUILD-DOC 7.3). Standard library only.

    "Report precision@k for all three on a held-out query set. If the AI method
     does not win, report that and use the baseline."

    python3 speedrun-analysis/evals/retrieval_compare.py
    python3 speedrun-analysis/evals/retrieval_compare.py --k 3 --json
    python3 speedrun-analysis/evals/retrieval_compare.py --plant-leak

THE COMPARISON IS BUILT TO LOSE
-------------------------------
The three arms are entries in one list. Nothing in the scoring or ranking code
knows which of them is "ours": every arm is asked for a ranking, scored by the
same function, and sorted by the same key. The AI arm wins only by having a
**strictly higher** precision@k than **both** baselines. Anything else --
losing, tying, or being unable to run -- prints:

    SHIP THE BASELINE

Today the AI arm is NOT YET RUN (no API key, no real source corpus), so it
scores nothing and cannot win. That is the honest current state and it is what
the harness prints.

THE LEAKAGE GATE
----------------
BUILD-DOC 7.5 gates every eval number, so this harness runs the leakage check
on its own inputs first and **refuses to print any precision@k** if it is not
clean (exit 3).

What is compared matters, and it is easy to get backwards: the gate compares
the **held-out query set against the dev/tuning query set**, not against the
corpus. A held-out query overlapping the corpus is not leakage -- the corpus is
the thing being retrieved from, and a query that matched nothing in it would be
unanswerable. Leakage here is a held-out query that is a near-copy of one the
method was tuned on, because then the held-out set is not independent and its
precision@k is inflated.

`--plant-leak` injects a near-copy of a held-out query into the dev split to
prove the gate actually blocks. It must exit 3 with no numbers printed.

WHAT THESE NUMBERS ARE, AND ARE NOT
-----------------------------------
The bundled corpus in `fixtures/retrieval_fixture.json` is **synthetic**,
written by the project author, with relevance labels written by the same person
at the same time. Precision@k on it is HARNESS VALIDATION -- evidence that the
arms are wired up, scored symmetrically, and that a loss is reportable. It is
not the BUILD-DOC 7.3 result, which needs a real source corpus and a real
held-out query set. The report says so every time it runs.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

_HERE = Path(__file__).resolve().parent
_ANALYSIS_ROOT = _HERE.parent
if str(_ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS_ROOT))

import leakage  # noqa: E402  (sibling module, same directory)
from ai.retrieval import ArmNotRunnable  # noqa: E402
from ai.retrieval import Passage  # noqa: E402
from ai.retrieval import RetrievalArm  # noqa: E402
from ai.retrieval import build_arms  # noqa: E402

DEFAULT_FIXTURE = _HERE / "fixtures" / "retrieval_fixture.json"

#: Fixed so the dev/held-out split is reproducible by anyone rerunning this.
SPLIT_SEED = 1729
#: Fraction of queries held out for reporting. The rest are the dev/tuning
#: split -- which nothing currently tunes on, since both baselines use their
#: textbook default parameters.
HELDOUT_FRACTION = 0.5

DEFAULT_K = 3

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_LEAKAGE = 3


@dataclass(frozen=True)
class Query:
    query_id: str
    text: str
    relevant: Tuple[str, ...]


@dataclass
class ArmResult:
    name: str
    kind: str
    status: str
    note: str
    precision_at_k: Optional[float] = None
    recall_at_k: Optional[float] = None
    unavailable_reason: Optional[str] = None
    per_query: Dict[str, float] = field(default_factory=dict)

    @property
    def scored(self) -> bool:
        return self.precision_at_k is not None

    def to_dict(self) -> Dict[str, object]:
        return {
            "arm": self.name,
            "kind": self.kind,
            "status": self.status,
            "note": self.note,
            "precision_at_k": (
                None if self.precision_at_k is None else round(self.precision_at_k, 6)
            ),
            "recall_at_k": (
                None if self.recall_at_k is None else round(self.recall_at_k, 6)
            ),
            "unavailable_reason": self.unavailable_reason,
            "per_query_precision": {
                qid: round(value, 6) for qid, value in sorted(self.per_query.items())
            },
        }


# -- fixture ---------------------------------------------------------------


def load_fixture(path: Path) -> Tuple[List[Passage], List[Query], Dict[str, object]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    passages = [
        Passage(passage_id=str(record["passage_id"]), text=str(record["text"]))
        for record in data["corpus"]
    ]
    queries = [
        Query(
            query_id=str(record["query_id"]),
            text=str(record["text"]),
            relevant=tuple(str(pid) for pid in record["relevant_passage_ids"]),
        )
        for record in data["queries"]
    ]
    known = {p.passage_id for p in passages}
    for query in queries:
        missing = [pid for pid in query.relevant if pid not in known]
        if missing:
            raise ValueError(
                "query {} labels passages that are not in the corpus: {}".format(
                    query.query_id, missing
                )
            )
    meta = {key: value for key, value in data.items() if key.startswith("_")}
    meta["labelling_rule"] = data.get("labelling_rule", "")
    return passages, queries, meta


def split_queries(
    queries: Sequence[Query], seed: int = SPLIT_SEED, fraction: float = HELDOUT_FRACTION
) -> Tuple[List[Query], List[Query]]:
    """`(dev, heldout)`, reproducibly. The split is by query, never by passage."""
    ordered = sorted(queries, key=lambda q: q.query_id)
    rng = random.Random(seed)
    indices = list(range(len(ordered)))
    rng.shuffle(indices)
    cut = int(round(len(ordered) * (1.0 - fraction)))
    dev_idx = sorted(indices[:cut])
    held_idx = sorted(indices[cut:])
    return [ordered[i] for i in dev_idx], [ordered[i] for i in held_idx]


# -- scoring ---------------------------------------------------------------


def precision_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in set(relevant))
    return hits / k


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for pid in retrieved[:k] if pid in set(relevant))
    return hits / len(relevant)


def precision_ceiling(queries: Sequence[Query], k: int) -> float:
    """The best precision@k any perfect ranker could reach on this query set.

    With k=3 and a query that has one relevant passage, a perfect ranker still
    scores 1/3. Printing P@k without its ceiling invites reading 0.33 as bad.
    """
    if not queries:
        return 0.0
    return sum(min(k, len(q.relevant)) / k for q in queries) / len(queries)


def score_arm(arm: RetrievalArm, queries: Sequence[Query], k: int) -> ArmResult:
    """Score one arm. Identical treatment for every arm, AI included."""
    result = ArmResult(
        name=arm.name, kind=arm.kind, status=arm.status, note=arm.note
    )
    precisions: List[float] = []
    recalls: List[float] = []
    for query in queries:
        try:
            retrieved = arm.search(query.text, k)
        except Exception as exc:  # noqa: BLE001 - an arm that cannot run scores nothing
            result.unavailable_reason = "{}: {}".format(type(exc).__name__, exc)
            result.precision_at_k = None
            result.recall_at_k = None
            result.per_query = {}
            return result
        p = precision_at_k(retrieved, query.relevant, k)
        precisions.append(p)
        recalls.append(recall_at_k(retrieved, query.relevant, k))
        result.per_query[query.query_id] = p
    result.precision_at_k = sum(precisions) / len(precisions) if precisions else 0.0
    result.recall_at_k = sum(recalls) / len(recalls) if recalls else 0.0
    return result


# -- verdict ---------------------------------------------------------------


def discriminates(results: Sequence[ArmResult]) -> bool:
    """Did the query set separate the scoring arms at all?

    If every scored arm lands on the same precision@k, the query set cannot
    tell the arms apart -- and a comparison that cannot separate two baselines
    could not have detected an AI win either. That is a property of the
    fixture, not of the arms, and it is reported rather than left for a reader
    to notice.
    """
    scores = {round(r.precision_at_k or 0.0, 9) for r in results if r.scored}
    return len(scores) > 1


@dataclass
class Verdict:
    headline: str
    winner: Optional[str]
    detail: str

    def to_dict(self) -> Dict[str, object]:
        return {"headline": self.headline, "winner": self.winner, "detail": self.detail}


def decide(results: Sequence[ArmResult]) -> Verdict:
    """Pure function of the scores. It has no idea which arm is 'ours'.

    The AI arm wins only by strictly beating BOTH baselines. A tie is not a
    win: BUILD-DOC 7.3 says to use the simpler method unless the AI method
    wins, and equal precision at higher cost and lower auditability is a loss.
    """
    scored = [r for r in results if r.scored]
    ai = next((r for r in results if r.kind == "ai"), None)
    baselines = [r for r in scored if r.kind == "baseline"]

    if not baselines:
        return Verdict(
            headline="NO RESULT",
            winner=None,
            detail="no baseline arm produced a score; there is nothing to compare",
        )

    best_baseline = max(baselines, key=lambda r: (r.precision_at_k or 0.0, r.name))
    baseline_best = best_baseline.precision_at_k or 0.0

    if ai is None or not ai.scored:
        reason = (
            ai.unavailable_reason
            if ai is not None and ai.unavailable_reason
            else "the AI arm produced no score"
        )
        return Verdict(
            headline="SHIP THE BASELINE",
            winner=best_baseline.name,
            detail=(
                "The AI arm did not score, so it did not beat anything.\n"
                "Reason: {}\n"
                "Best scoring arm: {} at precision@k {:.4f}.".format(
                    reason.rstrip("."), best_baseline.name, baseline_best
                )
            ),
        )

    ai_score = ai.precision_at_k or 0.0
    if ai_score > baseline_best:
        return Verdict(
            headline="AI WINS",
            winner=ai.name,
            detail=(
                "AI precision@k {:.4f} strictly beats the best baseline ({} at "
                "{:.4f}).".format(ai_score, best_baseline.name, baseline_best)
            ),
        )
    relation = "ties" if abs(ai_score - baseline_best) < 1e-12 else "loses to"
    return Verdict(
        headline="SHIP THE BASELINE",
        winner=best_baseline.name,
        detail=(
            "AI precision@k {:.4f} {} the best baseline ({} at {:.4f}). A tie is "
            "not a win: BUILD-DOC 7.3 says use the simpler method unless the AI "
            "method wins.".format(ai_score, relation, best_baseline.name, baseline_best)
        ),
    )


# -- leakage gate ----------------------------------------------------------

def plant_near_copy(heldout: Sequence[Query]) -> Query:
    """Derive a near-copy of a real held-out query, for `--plant-leak`.

    Derived at runtime rather than hardcoded. A hardcoded planted string stops
    being a near-copy of anything the moment the query set or the split
    changes -- and then the "proof" that the gate blocks silently becomes a
    proof of nothing. This one is a near-copy by construction: one interior
    word replaced, one clause appended, everything else verbatim.
    """
    if not heldout:
        raise ValueError("nothing to plant a near-copy of")
    target = heldout[0]
    tokens = target.text.split()
    index = min(2, len(tokens) - 1)
    tokens[index] = "precisely"
    text = " ".join(tokens) + " in a clinical context"
    return Query(
        query_id="planted_leak_of_{}".format(target.query_id),
        text=text,
        relevant=target.relevant,
    )


def run_leakage_gate(
    dev: Sequence[Query], heldout: Sequence[Query]
) -> "leakage.LeakageReport":
    return leakage.gate(
        heldout=[leakage.Item(q.query_id, q.text) for q in heldout],
        inputs=[leakage.Item(q.query_id, q.text) for q in dev],
        label="held-out query set vs dev/tuning query set",
    )


# -- report ----------------------------------------------------------------


def format_report(
    results: Sequence[ArmResult],
    verdict: Verdict,
    queries: Sequence[Query],
    dev: Sequence[Query],
    k: int,
    fixture: Path,
    synthetic: bool,
) -> str:
    lines = [
        "=" * 78,
        "RETRIEVAL COMPARISON -- three arms, precision@{} (BUILD-DOC 7.3)".format(k),
        "=" * 78,
        "corpus:        {}".format(fixture),
        "held-out queries: {}   dev/tuning queries: {}   (seed {}, "
        "split by query)".format(len(queries), len(dev), SPLIT_SEED),
        "precision@{} ceiling on this held-out set: {:.4f}".format(
            k, precision_ceiling(queries, k)
        ),
        "",
    ]
    if synthetic:
        lines += [
            "*" * 78,
            "HARNESS VALIDATION ONLY. This corpus is SYNTHETIC -- passages and",
            "relevance labels were written by the project author. These numbers",
            "describe the fixture, not the product. The BUILD-DOC 7.3 result",
            "needs a real source corpus and a real held-out query set, and does",
            "not exist yet.",
            "*" * 78,
            "",
        ]
    lines += [
        "{:<16} {:<9} {:<12} {:>12} {:>10}".format(
            "arm", "kind", "status", "precision@{}".format(k), "recall@{}".format(k)
        ),
        "-" * 78,
    ]
    for result in results:
        if result.scored:
            p = "{:.4f}".format(result.precision_at_k or 0.0)
            r = "{:.4f}".format(result.recall_at_k or 0.0)
        else:
            p = "--"
            r = "--"
        lines.append(
            "{:<16} {:<9} {:<12} {:>12} {:>10}".format(
                result.name, result.kind, result.status, p, r
            )
        )
    lines.append("")
    for result in results:
        lines.append("  {}: {}".format(result.name, result.note))
        if result.unavailable_reason:
            lines.append("      NOT SCORED -- {}".format(result.unavailable_reason))
    if not discriminates(results):
        lines += [
            "",
            "CAUTION: every scored arm returned the same precision@{}. This "
            "query set".format(k),
            "does not separate the arms, so it could not have detected an AI "
            "win either.",
            "That is a limitation of the fixture, not a result about the arms.",
        ]
    lines += [
        "",
        "-" * 78,
        "VERDICT: {}".format(verdict.headline),
        "-" * 78,
        verdict.detail,
    ]
    if verdict.winner:
        lines.append("Winning arm: {}".format(verdict.winner))
    lines.append("=" * 78)
    return "\n".join(lines)


# -- CLI -------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare BM25, a hashing vector baseline, and the AI arm by "
            "precision@k on a held-out query set (BUILD-DOC 7.3)."
        )
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="fixture JSON (default: the bundled synthetic fixture)",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, help="cutoff k")
    parser.add_argument("--json", action="store_true", help="JSON report on stdout")
    parser.add_argument(
        "--plant-leak",
        action="store_true",
        help=(
            "inject a near-copy of a held-out query into the dev split, to "
            "prove the leakage gate blocks the report (must exit 3)"
        ),
    )
    args = parser.parse_args(argv)

    try:
        passages, queries, meta = load_fixture(args.corpus)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("cannot load the corpus: {}\n".format(exc))
        return EXIT_USAGE

    synthetic = any(str(value).startswith("SYNTHETIC") for value in meta.values())
    dev, heldout = split_queries(queries)
    if args.plant_leak:
        dev = list(dev) + [plant_near_copy(heldout)]

    report = run_leakage_gate(dev, heldout)
    if not report.clean:
        sys.stderr.write(leakage.format_report(report))
        sys.stderr.write(
            "\n\nRETRIEVAL COMPARISON ABORTED. No precision@k is printed, "
            "because a held-out query is a near-copy of a dev/tuning query and "
            "the held-out set is therefore not independent (BUILD-DOC 7.5).\n"
        )
        return EXIT_LEAKAGE

    arms = build_arms(passages)
    results = [score_arm(arm, heldout, args.k) for arm in arms]
    verdict = decide(results)

    if args.json:
        print(
            json.dumps(
                {
                    "corpus": str(args.corpus),
                    "synthetic_fixture": synthetic,
                    "k": args.k,
                    "split_seed": SPLIT_SEED,
                    "heldout_query_ids": [q.query_id for q in heldout],
                    "dev_query_ids": [q.query_id for q in dev],
                    "leakage_gate": report.to_dict(),
                    "precision_ceiling": round(precision_ceiling(heldout, args.k), 6),
                    "query_set_separates_arms": discriminates(results),
                    "arms": [r.to_dict() for r in results],
                    "verdict": verdict.to_dict(),
                },
                indent=4,
                sort_keys=True,
            )
        )
    else:
        print("leakage gate: CLEAN ({})".format(report.label))
        print(
            "  worst containment among held-out queries: {:.3f} "
            "(threshold {:.2f})".format(
                report.worst_containment, report.threshold
            )
        )
        print("")
        print(
            format_report(
                results, verdict, heldout, dev, args.k, args.corpus, synthetic
            )
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
