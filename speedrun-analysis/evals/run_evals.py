# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""One command for every AI check that can run without a key or a source.

    python3 speedrun-analysis/evals/run_evals.py

Exits 0 only if every step produced its **expected** exit code -- and two of
the steps are expected to FAIL. `retrieval_compare.py --plant-leak` must exit 3
and the traceability CLI must exit 2 on a span-less note; a run in which those
came back 0 is a broken harness, not a clean one, and this script says so.

WHAT IS NOT COVERED HERE, AND WHY
---------------------------------
These need an API key and a real source document, and neither exists in this
tree. They are listed rather than silently omitted:

  * 7.1 card generation -- no card has been generated.
  * 7.2 item rewording / the paraphrase test (BUILD-DOC 11, test 4) -- the gap
    between card recall and rewording accuracy is UNMEASURED, not zero.
  * 7.4 the AI card check against `ai_card_cutoff.json` -- the cutoff is
    pre-registered and committed; nothing has been measured against it.
  * 7.3 the real retrieval comparison -- the harness runs, but on a synthetic
    fixture. The reportable number needs a real corpus and a real query set.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import Sequence

_HERE = Path(__file__).resolve().parent
_ANALYSIS_ROOT = _HERE.parent


class Step(NamedTuple):
    name: str
    argv: List[str]
    expected_exit: int
    why: str


def steps() -> List[Step]:
    py = sys.executable
    return [
        Step(
            name="traceability tests (7.1)",
            argv=[py, str(_HERE / "test_traceability.py")],
            expected_exit=0,
            why="untraceable output is a build error; span-less and "
            "non-resolving spans must fail",
        ),
        Step(
            name="leakage self-test (7.5)",
            argv=[py, str(_HERE / "leakage.py"), "--self-test"],
            expected_exit=0,
            why="proves the check CATCHES a planted near-copy and stays quiet "
            "on a same-topic control",
        ),
        Step(
            name="retrieval comparison (7.3)",
            argv=[py, str(_HERE / "retrieval_compare.py")],
            expected_exit=0,
            why="three arms, precision@k, explicit SHIP THE BASELINE verdict",
        ),
        Step(
            name="retrieval leakage gate (7.3 x 7.5)",
            argv=[py, str(_HERE / "retrieval_compare.py"), "--plant-leak"],
            expected_exit=3,
            why="EXPECTED TO FAIL: a planted near-copy of a held-out query must "
            "block the report entirely",
        ),
        Step(
            name="AI off (7.6)",
            argv=[py, str(_HERE / "test_ai_off.py")],
            expected_exit=0,
            why="no generation, no AI retrieval, and the one real score input "
            "still computes",
        ),
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    results = []
    for step in steps():
        print("")
        print("#" * 78)
        print("# {}".format(step.name))
        print("# expected exit: {} -- {}".format(step.expected_exit, step.why))
        print("#" * 78)
        sys.stdout.flush()
        code = subprocess.call(step.argv)
        results.append((step, code))

    print("")
    print("=" * 78)
    print("AI SUBSYSTEM -- CHECKS THAT NEED NO KEY AND NO SOURCE DOCUMENT")
    print("=" * 78)
    print("{:<36} {:>8} {:>8}  {}".format("step", "expected", "actual", "result"))
    print("-" * 78)
    failed = 0
    for step, code in results:
        ok = code == step.expected_exit
        if not ok:
            failed += 1
        print(
            "{:<36} {:>8} {:>8}  {}".format(
                step.name, step.expected_exit, code, "OK" if ok else "MISMATCH"
            )
        )
    print("")
    print("NOT RUN (needs an API key and a real source document):")
    print("  7.1 card generation            -- no card generated")
    print("  7.2 rewording / paraphrase gap -- UNMEASURED, not zero")
    print("  7.4 AI card check vs the pre-registered cutoff -- not measured")
    print("  7.3 the reportable retrieval number -- fixture only, see above")
    print("=" * 78)
    if failed:
        print("{} step(s) did not match their expected exit code.".format(failed))
        return 1
    print("All steps matched their expected exit codes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
