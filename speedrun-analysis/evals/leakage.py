# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Leakage check (BUILD-DOC 7.5). Standard library only. Runs standalone.

    "Script flagging any held-out test item or near-copy present in
     training/generation inputs. Near-copy via normalized n-gram overlap,
     threshold stated. Must show clean. Leaked test data zeroes that score."

Every eval number in this project is downstream of this script, so it is a
single file with no imports outside the standard library and no dependency on
the rest of the tree:

    python3 speedrun-analysis/evals/leakage.py --self-test
    python3 speedrun-analysis/evals/leakage.py --heldout H.json --inputs I.json

Exit codes: **0 clean, 1 LEAKAGE FOUND, 2 usage error.** Non-zero on leakage is
the contract; a caller that ignores the exit code is the only way to report a
leaked number.

THE METHOD, AND THE THRESHOLD
-----------------------------
Normalisation: Unicode NFKC, casefold, every non-alphanumeric character
becomes a space, whitespace collapsed. This is deliberately aggressive --
punctuation, capitalisation, and markup differences are exactly how a copy
disguises itself, and none of them change what a student would read.

Comparison: word n-grams with **n = 5** (`DEFAULT_NGRAM`), scored by
**containment**, not Jaccard:

    containment(H, I) = |ngrams(H) & ngrams(I)| / |ngrams(H)|

Containment because Jaccard punishes length asymmetry, and the realistic
leak IS asymmetric: one 30-word held-out item pasted inside a 5,000-word
generation input has a Jaccard near zero and a containment near one. Using
Jaccard here would produce a check that reliably misses the case it exists to
catch. Jaccard is still reported alongside, for context.

**Threshold: containment >= 0.30** (`DEFAULT_THRESHOLD`), on n = 5.

Why 0.30 and not something safer-sounding:

  * Unrelated English prose of this length shares essentially no 5-grams. In
    the self-test's negative control -- same topic, same technical vocabulary,
    independently worded -- containment measures 0.000. The floor is not near
    0.30; it is at 0.
  * 0.30 means roughly a third of the held-out item's distinctive 5-word runs
    appear verbatim in an input. Reaching that by coincidence requires shared
    phrasing, not shared subject matter.
  * It is low enough to catch a paraphrased copy. A 30-word item with three
    words changed still lands around 0.4-0.6, above the line -- which the
    self-test measures rather than assumes.

Exact matches after normalisation are flagged regardless of the threshold.

Short items: an item with fewer than n words produces no 5-grams, so n falls
back to the item's own word count (minimum 1) and the finding is marked
`SHORT_ITEM_FALLBACK`. Without this, a short held-out item would be
unconditionally "clean" -- silently exempt from the check.

Cost is O(|heldout| x |inputs|) set intersections. At eval scale (hundreds of
items) that is nothing, and an exact pairwise answer is worth more here than a
faster approximate one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Dict
from typing import FrozenSet
from typing import Iterable
from typing import List
from typing import Optional
from typing import Sequence
from typing import Set
from typing import Tuple

DEFAULT_NGRAM = 5
DEFAULT_THRESHOLD = 0.30

EXIT_CLEAN = 0
EXIT_LEAKAGE = 1
EXIT_USAGE = 2

EXACT_COPY = "EXACT_COPY"
NEAR_COPY = "NEAR_COPY"

Ngram = Tuple[str, ...]


# -- normalisation ---------------------------------------------------------


def normalize(text: str) -> str:
    """NFKC, casefold, non-alphanumeric -> space, whitespace collapsed."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    kept = [ch if ch.isalnum() else " " for ch in folded]
    return " ".join("".join(kept).split())


def words(text: str) -> List[str]:
    return normalize(text).split()


def ngrams(tokens: Sequence[str], n: int) -> Set[Ngram]:
    if n <= 0:
        return set()
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def longest_common_run(a: Sequence[str], b: Sequence[str]) -> int:
    """Longest run of identical consecutive words. Reported for context.

    Not a decision input -- the threshold decides -- but "17 words verbatim"
    tells a reader what kind of leak they are looking at far faster than a
    ratio does.
    """
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        current = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                current[j] = previous[j - 1] + 1
                if current[j] > best:
                    best = current[j]
        previous = current
    return best


# -- items and findings ----------------------------------------------------


@dataclass(frozen=True)
class Item:
    item_id: str
    text: str

    @property
    def tokens(self) -> List[str]:
        return words(self.text)


@dataclass(frozen=True)
class Finding:
    kind: str
    heldout_id: str
    input_id: str
    containment: float
    jaccard: float
    longest_verbatim_run: int
    effective_ngram: int
    short_item_fallback: bool
    excerpt: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "heldout_id": self.heldout_id,
            "input_id": self.input_id,
            "containment": round(self.containment, 6),
            "jaccard": round(self.jaccard, 6),
            "longest_verbatim_run_words": self.longest_verbatim_run,
            "effective_ngram": self.effective_ngram,
            "short_item_fallback": self.short_item_fallback,
            "excerpt": self.excerpt,
        }


@dataclass
class LeakageReport:
    threshold: float
    ngram: int
    heldout_count: int
    input_count: int
    #: What was compared against what, for the report header.
    label: str = ""
    findings: List[Finding] = field(default_factory=list)
    #: Best containment seen per held-out item, including the clean ones. Kept
    #: because "nothing crossed the line" is much weaker evidence than
    #: "the worst pair in the set measured 0.02".
    max_containment_by_heldout: Dict[str, float] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def worst_containment(self) -> float:
        if not self.max_containment_by_heldout:
            return 0.0
        return max(self.max_containment_by_heldout.values())

    def to_dict(self) -> Dict[str, object]:
        return {
            "label": self.label,
            "method": "normalized word {}-gram containment".format(self.ngram),
            "threshold_containment": self.threshold,
            "ngram": self.ngram,
            "heldout_items": self.heldout_count,
            "input_items": self.input_count,
            "clean": self.clean,
            "worst_containment_observed": round(self.worst_containment, 6),
            "findings": [f.to_dict() for f in self.findings],
        }


# -- the check -------------------------------------------------------------


def _effective_ngram(tokens: Sequence[str], n: int) -> Tuple[int, bool]:
    """`(n_to_use, fell_back)` -- short items are never silently exempt."""
    if len(tokens) >= n:
        return n, False
    return max(1, len(tokens)), True


def _jaccard(a: FrozenSet[Ngram], b: FrozenSet[Ngram]) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def check_leakage(
    heldout: Sequence[Item],
    inputs: Sequence[Item],
    ngram: int = DEFAULT_NGRAM,
    threshold: float = DEFAULT_THRESHOLD,
) -> LeakageReport:
    """Flag every held-out item present, exactly or as a near-copy, in inputs."""
    report = LeakageReport(
        threshold=threshold,
        ngram=ngram,
        heldout_count=len(heldout),
        input_count=len(inputs),
    )
    normalised_inputs = [(item, normalize(item.text), item.tokens) for item in inputs]

    for held in heldout:
        held_tokens = held.tokens
        held_norm = normalize(held.text)
        n_eff, fell_back = _effective_ngram(held_tokens, ngram)
        held_grams = frozenset(ngrams(held_tokens, n_eff))
        best_containment = 0.0

        for item, item_norm, item_tokens in normalised_inputs:
            item_grams = frozenset(ngrams(item_tokens, n_eff))
            if held_grams:
                containment = len(held_grams & item_grams) / len(held_grams)
            else:
                containment = 1.0 if held_norm and held_norm in item_norm else 0.0
            jaccard = _jaccard(held_grams, item_grams)
            best_containment = max(best_containment, containment)

            exact = bool(held_norm) and (
                held_norm == item_norm or held_norm in item_norm
            )
            if exact:
                kind: Optional[str] = EXACT_COPY
            elif containment >= threshold:
                kind = NEAR_COPY
            else:
                kind = None

            if kind is not None:
                run = longest_common_run(held_tokens, item_tokens)
                report.findings.append(
                    Finding(
                        kind=kind,
                        heldout_id=held.item_id,
                        input_id=item.item_id,
                        containment=1.0 if exact else containment,
                        jaccard=jaccard,
                        longest_verbatim_run=run,
                        effective_ngram=n_eff,
                        short_item_fallback=fell_back,
                        excerpt=_excerpt(held.text),
                    )
                )
        report.max_containment_by_heldout[held.item_id] = best_containment

    report.findings.sort(key=lambda f: (-f.containment, f.heldout_id, f.input_id))
    return report


def _excerpt(text: str, limit: int = 90) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


# -- io --------------------------------------------------------------------


def load_items(path: Path, label: str) -> List[Item]:
    """Load `[{"id","text"}, ...]`, `{"items": [...]}`, or `["text", ...]`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("items", [])
    items: List[Item] = []
    for index, record in enumerate(data):
        if isinstance(record, str):
            items.append(Item(item_id="{}[{}]".format(label, index), text=record))
        else:
            item_id = str(
                record.get("id", record.get("item_id", "{}[{}]".format(label, index)))
            )
            items.append(Item(item_id=item_id, text=str(record["text"])))
    return items


def format_report(report: LeakageReport) -> str:
    lines = [
        "=" * 78,
        "LEAKAGE CHECK (BUILD-DOC 7.5)",
        "=" * 78,
        "comparing:   {}".format(report.label or "held-out items vs inputs"),
        "method:      normalized word {}-gram containment".format(report.ngram),
        "             (NFKC, casefold, non-alphanumeric -> space, collapsed)",
        "threshold:   containment >= {:.2f}  -> flagged as a near-copy".format(
            report.threshold
        ),
        "             exact match after normalisation -> flagged regardless",
        "held-out:    {} item(s)".format(report.heldout_count),
        "inputs:      {} item(s)".format(report.input_count),
        "worst containment observed: {:.3f}".format(report.worst_containment),
        "",
    ]
    if report.clean:
        lines += [
            "RESULT: CLEAN -- no held-out item, and no near-copy of one, is",
            "present in the training/generation inputs at or above the stated",
            "threshold.",
        ]
    else:
        lines += [
            "RESULT: LEAKAGE FOUND -- {} finding(s).".format(len(report.findings)),
            "Every eval number downstream of these inputs is void until this is",
            "resolved (BUILD-DOC 17: leaked test data zeroes that score).",
            "",
        ]
        for finding in report.findings:
            lines.append(
                "  [{}] heldout {!r} <- input {!r}".format(
                    finding.kind, finding.heldout_id, finding.input_id
                )
            )
            lines.append(
                "      containment={:.3f}  jaccard={:.3f}  longest verbatim run="
                "{} words  n={}{}".format(
                    finding.containment,
                    finding.jaccard,
                    finding.longest_verbatim_run,
                    finding.effective_ngram,
                    "  (SHORT_ITEM_FALLBACK)" if finding.short_item_fallback else "",
                )
            )
            lines.append("      held-out text: {}".format(finding.excerpt))
    lines.append("=" * 78)
    return "\n".join(lines)


# -- self-test -------------------------------------------------------------

_CLEAN_HELDOUT = [
    {
        "id": "h1",
        "text": (
            "A held-out question asking which vessel carries deoxygenated "
            "blood from the right ventricle towards the lungs, with four "
            "answer options and a single best answer."
        ),
    },
    {
        "id": "h2",
        "text": (
            "A held-out question about the effect of decreasing plasma "
            "osmolality on antidiuretic hormone release, phrased as a short "
            "clinical vignette with laboratory values."
        ),
    },
]

_CLEAN_INPUTS = [
    {
        "id": "i1",
        "text": (
            "Generation input describing the mechanics of ventilation: the "
            "diaphragm contracts, thoracic volume rises, and pressure inside "
            "the pleural space becomes more negative."
        ),
    },
    {
        "id": "i2",
        "text": (
            "Generation input covering the countercurrent multiplier and how "
            "the loop of Henle establishes a medullary gradient."
        ),
    },
]

#: h1, three words changed, embedded inside a longer document. This is the
#: planted leak the self-test must catch.
_PLANTED_NEAR_COPY = (
    "Introductory material that has nothing to do with the item follows, and "
    "then, buried in the middle of a much longer generation input, sits this: "
    "A held-out question asking which vessel carries deoxygenated blood from "
    "the right ventricle toward the lung, with four answer choices and a "
    "single best answer. After that the document continues with unrelated "
    "notes about study scheduling and review intervals, which is what makes "
    "this the realistic shape of a leak: a short item hidden in a long input."
)

#: Same topic and vocabulary as h1, independently worded. This must NOT fire.
#: A check that flags this is not a leakage check, it is a topic detector.
_NEGATIVE_CONTROL = (
    "The pulmonary artery is unusual in carrying blood low in oxygen. Its "
    "origin is the right side of the heart, and its destination is the "
    "capillary bed surrounding the alveoli, where gas exchange occurs."
)


def _write_json(directory: Path, name: str, payload: object) -> Path:
    path = directory / name
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    return path


def self_test() -> int:
    """Build fixtures and prove the check both fires and stays quiet.

    Four cases. A leakage check that never fires is worthless, and one that
    always fires is equally worthless, so both directions are asserted.
    """
    print("=" * 78)
    print("LEAKAGE CHECK SELF-TEST")
    print("=" * 78)
    print("Builds its own fixtures, then asserts the check fires on a planted")
    print("near-copy and an exact copy, and does NOT fire on a clean set or on")
    print("a same-topic independently-worded control.")
    print("threshold = {:.2f} containment on normalized word {}-grams".format(
        DEFAULT_THRESHOLD, DEFAULT_NGRAM
    ))
    print("")

    failures: List[str] = []

    def case(name: str, ok: bool, detail: str) -> None:
        print("  [{}] {}".format("PASS" if ok else "FAIL", name))
        print("        {}".format(detail))
        if not ok:
            failures.append(name)

    heldout = [Item(r["id"], r["text"]) for r in _CLEAN_HELDOUT]
    clean_inputs = [Item(r["id"], r["text"]) for r in _CLEAN_INPUTS]

    # 1. clean
    clean = check_leakage(heldout, clean_inputs)
    case(
        "clean set is reported clean",
        clean.clean,
        "0 findings; worst containment observed {:.3f}".format(
            clean.worst_containment
        ),
    )

    # 2. planted near-copy
    leaked_inputs = clean_inputs + [Item("i3_planted", _PLANTED_NEAR_COPY)]
    leaked = check_leakage(heldout, leaked_inputs)
    near = [f for f in leaked.findings if f.heldout_id == "h1"]
    detected = bool(near)
    detail = (
        "containment={:.3f} (threshold {:.2f}), longest verbatim run={} words, "
        "kind={}".format(
            near[0].containment,
            DEFAULT_THRESHOLD,
            near[0].longest_verbatim_run,
            near[0].kind,
        )
        if detected
        else "NOT DETECTED -- the planted leak passed through"
    )
    case("planted near-copy is CAUGHT", detected, detail)

    # 3. exact copy
    exact_inputs = clean_inputs + [Item("i4_exact", _CLEAN_HELDOUT[1]["text"])]
    exact = check_leakage(heldout, exact_inputs)
    exact_hits = [f for f in exact.findings if f.kind == EXACT_COPY]
    case(
        "exact copy is CAUGHT",
        bool(exact_hits),
        "kind={} containment={:.3f}".format(
            exact_hits[0].kind, exact_hits[0].containment
        )
        if exact_hits
        else "NOT DETECTED",
    )

    # 4. negative control: same topic, independent wording
    control_item = Item("i5_control", _NEGATIVE_CONTROL)
    control_inputs = clean_inputs + [control_item]
    control = check_leakage(heldout, control_inputs)
    h1_grams = frozenset(ngrams(heldout[0].tokens, DEFAULT_NGRAM))
    control_grams = frozenset(ngrams(control_item.tokens, DEFAULT_NGRAM))
    control_containment = len(h1_grams & control_grams) / max(1, len(h1_grams))
    case(
        "same-topic control does NOT fire",
        control.clean,
        "0 findings; containment of the control against h1 = {:.3f}, below the "
        "{:.2f} line".format(control_containment, DEFAULT_THRESHOLD),
    )

    # 5. exit codes, through the real CLI, in a subprocess
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        h_path = _write_json(tmpdir, "heldout.json", _CLEAN_HELDOUT)
        clean_path = _write_json(tmpdir, "inputs_clean.json", _CLEAN_INPUTS)
        leak_path = _write_json(
            tmpdir,
            "inputs_leaked.json",
            _CLEAN_INPUTS + [{"id": "i3_planted", "text": _PLANTED_NEAR_COPY}],
        )
        script = str(Path(__file__).resolve())
        clean_rc = subprocess.call(
            [sys.executable, script, "--heldout", str(h_path), "--inputs",
             str(clean_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        leak_rc = subprocess.call(
            [sys.executable, script, "--heldout", str(h_path), "--inputs",
             str(leak_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    case(
        "CLI exits 0 on a clean set",
        clean_rc == EXIT_CLEAN,
        "exit code {}".format(clean_rc),
    )
    case(
        "CLI exits NON-ZERO on leakage",
        leak_rc == EXIT_LEAKAGE,
        "exit code {} (expected {})".format(leak_rc, EXIT_LEAKAGE),
    )

    print("")
    if failures:
        print("SELF-TEST FAILED: {}".format(", ".join(failures)))
        print("=" * 78)
        return EXIT_USAGE
    print("SELF-TEST PASSED: the check fires on copies and stays quiet on a")
    print("same-topic control, and the CLI's exit codes match the contract.")
    print("=" * 78)
    return EXIT_CLEAN


# -- CLI -------------------------------------------------------------------


def gate(
    heldout: Iterable[Item],
    inputs: Iterable[Item],
    label: str,
    ngram: int = DEFAULT_NGRAM,
    threshold: float = DEFAULT_THRESHOLD,
) -> LeakageReport:
    """Programmatic gate for other evals. Returns the report; caller decides.

    `retrieval_compare.py` uses this and refuses to print numbers when the
    report is not clean.
    """
    report = check_leakage(list(heldout), list(inputs), ngram, threshold)
    report.label = label
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Flag any held-out test item, or near-copy of one, present in the "
            "training/generation inputs (BUILD-DOC 7.5). Exits 1 on leakage."
        )
    )
    parser.add_argument("--heldout", type=Path, help="held-out items JSON")
    parser.add_argument("--inputs", type=Path, help="training/generation inputs JSON")
    parser.add_argument(
        "--ngram",
        type=int,
        default=DEFAULT_NGRAM,
        help="n for word n-grams (default {})".format(DEFAULT_NGRAM),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="containment at or above which a pair is a near-copy (default "
        "{})".format(DEFAULT_THRESHOLD),
    )
    parser.add_argument("--json", action="store_true", help="JSON report on stdout")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="build fixtures and prove the check catches a planted near-copy",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.heldout or not args.inputs:
        parser.error("--heldout and --inputs are required unless --self-test")

    try:
        heldout = load_items(args.heldout, "heldout")
        inputs = load_items(args.inputs, "input")
    except Exception as exc:  # noqa: BLE001 - report and refuse to guess
        sys.stderr.write("cannot load items: {}\n".format(exc))
        return EXIT_USAGE

    report = check_leakage(heldout, inputs, args.ngram, args.threshold)
    if args.json:
        print(json.dumps(report.to_dict(), indent=4, sort_keys=True))
    else:
        print(format_report(report))
    return EXIT_CLEAN if report.clean else EXIT_LEAKAGE


if __name__ == "__main__":
    sys.exit(main())
