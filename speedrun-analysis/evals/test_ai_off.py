# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""AI OFF, as a test rather than a config option (BUILD-DOC 7.6).

    python3 speedrun-analysis/evals/test_ai_off.py

    "Feature flag. With AI disabled: no generation, no AI retrieval, all three
     scores still computed and displayed. This is a required test, not a config
     nicety."

WHAT THIS TEST CAN HONESTLY ASSERT TODAY
----------------------------------------
Two of the three clauses are testable now and are tested:

  * **no generation** -- every generation entry point refuses, with the network
    poisoned so a refusal cannot be a silent success;
  * **no AI retrieval** -- the AI arm refuses, and retrieval still returns
    results by falling back to BM25.

The third clause, "all three scores still computed", is **not fully testable,
because two of the three scores do not exist yet.** This test does not pretend
otherwise. What it does instead:

  * Memory -- its INPUT is real: `mean_retrievability` and the per-topic counts
    come from the Rust `topic_mastery` query, which is implemented and is
    called here for real, through the actual backend, with AI off. The score
    ASSEMBLY around it (bootstrap interval, accept-only-if-better gate,
    BUILD-DOC 5.1) is NOT built, and this test says so rather than reporting a
    Memory score.
  * Performance (BUILD-DOC 5.2) and Readiness (5.3) -- **NOT BUILT.** There is
    no logistic-regression model, no calibration, and no `speedrun/scoring`
    module. A test asserting they "work with AI off" would be asserting
    something about code that does not exist.

`test_unbuilt_score_paths_are_still_unbuilt` is a tripwire: it asserts the
score-assembly paths are still absent, and **fails the day someone builds
one**. That failure is the reminder to extend this test to cover the new score
with AI off, which is precisely the requirement that would otherwise be
quietly dropped.

If `anki` is not importable, this test re-runs itself under the built
interpreter (`out/pyenv/bin/python` with `out/pylib` on the path). If that is
not available either it exits **4** -- never 0. An AI-off test that silently
skips the only real score path it has is worse than no test.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from typing import List
from typing import Tuple

_ANALYSIS_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _ANALYSIS_ROOT.parent
if str(_ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS_ROOT))

EXIT_NO_BACKEND = 4
_REEXEC_GUARD = "SPEEDRUN_AI_OFF_TEST_REEXEC"


def _ensure_backend_importable() -> None:
    """Re-run under the built interpreter if `anki` is not importable here."""
    try:
        import anki.speedrun_pb2  # noqa: F401
        from anki.collection import Collection  # noqa: F401

        return
    except ImportError:
        pass

    if os.environ.get(_REEXEC_GUARD):
        sys.stderr.write(
            "the built anki package is still not importable after re-exec; "
            "refusing to report a pass\n"
        )
        raise SystemExit(EXIT_NO_BACKEND)

    if os.name == "nt":
        interpreter = _REPO_ROOT / "out" / "pyenv" / "Scripts" / "python.exe"
    else:
        interpreter = _REPO_ROOT / "out" / "pyenv" / "bin" / "python"
    generated = _REPO_ROOT / "out" / "pylib"

    if not interpreter.exists() or not generated.exists():
        sys.stderr.write(
            "cannot run the AI-off test: the Rust backend is not built.\n"
            "  expected interpreter: {}\n"
            "  expected generated protos: {}\n"
            "Build first (`just build`), then rerun. Exiting {} rather than "
            "reporting a pass without exercising the real query.\n".format(
                interpreter, generated, EXIT_NO_BACKEND
            )
        )
        raise SystemExit(EXIT_NO_BACKEND)

    env = dict(os.environ)
    env[_REEXEC_GUARD] = "1"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(generated) + (os.pathsep + existing if existing else "")
    )
    # Never inherit an AI flag into the AI-off test.
    env.pop("SPEEDRUN_AI", None)
    print(
        "anki is not importable under {}; re-running under {}".format(
            sys.executable, interpreter
        )
    )
    sys.stdout.flush()
    raise SystemExit(
        subprocess.call([str(interpreter), str(Path(__file__).resolve())], env=env)
    )


_ensure_backend_importable()

from ai import generation  # noqa: E402
from ai import retrieval  # noqa: E402
from ai.flags import AI_FLAG_ENV  # noqa: E402
from ai.flags import AiDisabled  # noqa: E402
from ai.flags import AiNotConfigured  # noqa: E402
from ai.flags import ai_enabled  # noqa: E402
from ai.sources import SourceStore  # noqa: E402
from ai.traceability import AI_TAG  # noqa: E402
from ai.traceability import GeneratedNote  # noqa: E402

# The AI-off environment. Not the real `os.environ`: the test states the
# condition it is testing instead of depending on the shell it was launched in.
AI_OFF_ENV = {}
AI_ON_NO_KEY_ENV = {AI_FLAG_ENV: "1"}

CARDIO = "speedrun::topic::cardio"
RENAL = "speedrun::topic::renal"


class _PoisonedSocket:
    """Any attempt to open a socket is a test failure, not a network call."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError(
            "the AI-off path tried to open a network socket; with AI off "
            "nothing may reach out (BUILD-DOC 7.6)"
        )


@contextmanager
def network_poisoned() -> Iterator[None]:
    """Make any outbound connection raise, loudly, for the duration."""
    real_socket = socket.socket
    real_connect = socket.create_connection
    socket.socket = _PoisonedSocket  # type: ignore[assignment,misc]

    def _no_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("the AI-off path tried to open a connection")

    socket.create_connection = _no_connect  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = real_socket  # type: ignore[misc]
        socket.create_connection = real_connect  # type: ignore[assignment]


PASSAGES = [
    retrieval.Passage("p1", "The pulmonary artery leaves the right ventricle."),
    retrieval.Passage("p2", "Gas exchange occurs across the alveolar membrane."),
    retrieval.Passage("p3", "The loop of Henle builds a medullary gradient."),
]


class TheGuardItself(unittest.TestCase):
    """The network poison must bite, or every test using it passes vacuously."""

    def test_the_network_poison_actually_bites(self) -> None:
        with network_poisoned():
            with self.assertRaises(AssertionError):
                socket.socket()
            with self.assertRaises(AssertionError):
                socket.create_connection(("127.0.0.1", 9))
        # ...and is fully restored afterwards, so it cannot leak into other
        # tests and make them pass for the wrong reason.
        sock = socket.socket()
        sock.close()


class NoGenerationWithAiOff(unittest.TestCase):
    def test_flag_defaults_to_off(self) -> None:
        self.assertFalse(ai_enabled({}))
        self.assertFalse(ai_enabled({AI_FLAG_ENV: "0"}))
        self.assertFalse(ai_enabled({AI_FLAG_ENV: ""}))
        self.assertTrue(ai_enabled({AI_FLAG_ENV: "1"}))

    def test_card_generation_refuses_and_touches_no_network(self) -> None:
        store = SourceStore.from_texts({"src": "some source text"})
        with network_poisoned():
            with self.assertRaises(AiDisabled):
                generation.generate_cards("src", store, count=5, env=AI_OFF_ENV)

    def test_item_rewording_refuses_and_touches_no_network(self) -> None:
        store = SourceStore.from_texts({"src": "some source text"})
        note = GeneratedNote(note_id="n1", tags=(AI_TAG,))
        with network_poisoned():
            with self.assertRaises(AiDisabled):
                generation.reword_items(note, store, env=AI_OFF_ENV)

    def test_flag_on_without_a_key_still_produces_no_card(self) -> None:
        # Turning the flag on does not conjure a generator. The failure moves
        # from "off" to "not configured"; it never becomes a card.
        store = SourceStore.from_texts({"src": "some source text"})
        with network_poisoned():
            with self.assertRaises(AiNotConfigured):
                generation.generate_cards("src", store, env=AI_ON_NO_KEY_ENV)

    def test_no_key_is_ever_echoed(self) -> None:
        store = SourceStore.from_texts({"src": "text"})
        env = {AI_FLAG_ENV: "1", "ANTHROPIC_API_KEY": ""}
        with self.assertRaises(AiNotConfigured) as caught:
            generation.generate_cards("src", store, env=env)
        self.assertNotIn("sk-", str(caught.exception))


class NoAiRetrievalWithAiOff(unittest.TestCase):
    def test_ai_arm_refuses(self) -> None:
        with network_poisoned():
            with self.assertRaises(AiDisabled):
                retrieval.retrieve("pulmonary artery", PASSAGES, arm="ai",
                                   env=AI_OFF_ENV)

    def test_retrieval_still_works_by_falling_back_to_bm25(self) -> None:
        with network_poisoned():
            arm, hits = retrieval.retrieve(
                "which vessel leaves the right ventricle", PASSAGES, k=2,
                env=AI_OFF_ENV
            )
        self.assertEqual(arm, "bm25")
        self.assertEqual(hits[0], "p1")

    def test_ai_arm_is_unscored_not_zero(self) -> None:
        # An arm that cannot run must not be recorded as scoring 0.0 -- that
        # would be a measurement, and no measurement was taken.
        arm = retrieval.AiRetrievalArm(PASSAGES, env=AI_OFF_ENV)
        self.assertEqual(arm.status, "NOT_YET_RUN")
        with self.assertRaises(AiDisabled):
            arm.search("anything", 3)


class ScorePathsWithAiOff(unittest.TestCase):
    """The one score input that exists, exercised for real with AI off."""

    def _collection(self, tmpdir: str):
        from anki.collection import Collection

        col = Collection(os.path.join(tmpdir, "aioff.anki2"))
        for front, tags in (
            ("a", [CARDIO]),
            ("b", [CARDIO, RENAL]),
            ("c", [RENAL]),
            ("untagged", []),
        ):
            note = col.newNote()
            note["Front"] = front
            note["Back"] = "back"
            for tag in tags:
                note.tags.append(tag)
            col.add_note(note, col.decks.selected())
        return col

    def test_memory_score_input_computes_with_ai_off(self) -> None:
        """The Rust `topic_mastery` query, called for real, AI off.

        This is the Memory score's INPUT (BUILD-DOC 5.1), not the Memory score.
        The score assembly is unbuilt; see the tripwire below.
        """
        self.assertFalse(ai_enabled({}))
        with tempfile.TemporaryDirectory() as tmpdir:
            col = self._collection(tmpdir)
            try:
                with network_poisoned():
                    resp = col._backend.topic_mastery(
                        topic_tags=[], as_of_unix_secs=0
                    )
                tags = [t.topic_tag for t in resp.topics]
                self.assertEqual(tags, [CARDIO, RENAL])
                by_tag = {t.topic_tag: t for t in resp.topics}
                # The card carrying both tags is counted under each.
                self.assertEqual(by_tag[CARDIO].card_count, 2)
                self.assertEqual(by_tag[RENAL].card_count, 2)
                # Nothing reviewed, so nothing has a memory state; the query
                # says so rather than reporting a mean over an unstated subset.
                # Three, not four: the untagged card is outside every topic and
                # is not counted here either. Matches
                # pylib/tests/test_speedrun.py -- "only the tagged card counts".
                self.assertEqual(resp.cards_without_memory_state, 3)
                for topic in resp.topics:
                    self.assertEqual(topic.reviewed_count, 0)
                    self.assertEqual(topic.review_count, 0)
                    self.assertEqual(topic.fsrs_item_count, 0)
            finally:
                col.close()

    def test_unbuilt_score_paths_are_still_unbuilt(self) -> None:
        """TRIPWIRE. Fails the day Performance or Readiness is built.

        BUILD-DOC 7.6 requires all three scores to compute with AI off. Two of
        them do not exist, so there is nothing to test yet -- and the moment
        one does exist, this test must be extended to exercise it with AI off.
        Asserting their absence is what forces that.
        """
        scoring_module = _REPO_ROOT / "rslib" / "src" / "speedrun" / "scoring.rs"
        self.assertFalse(
            scoring_module.exists(),
            "rslib/src/speedrun/scoring.rs now exists. Extend "
            "test_ai_off.py to assert the Performance and Readiness scores "
            "still compute with AI off, then update this tripwire.",
        )
        proto = (_REPO_ROOT / "proto" / "anki" / "speedrun.proto").read_text(
            encoding="utf-8"
        )
        for absent in ("Performance", "Readiness"):
            self.assertNotIn(
                absent,
                proto,
                "speedrun.proto now mentions {}. Extend test_ai_off.py to "
                "cover that score with AI off.".format(absent),
            )


def score_path_status() -> List[Tuple[str, str, str]]:
    """`(score, status, evidence)` -- printed so nothing is implied silently."""
    return [
        (
            "Memory (5.1)",
            "INPUT REAL / ASSEMBLY NOT BUILT",
            "mean_retrievability and per-topic counts come from the Rust "
            "topic_mastery query, called for real above with AI off. The "
            "bootstrap interval and the accept-only-if-better gate are not "
            "built, so no Memory score is reported.",
        ),
        (
            "Performance (5.2)",
            "NOT BUILT",
            "no logistic-regression model, no scored items, no code. Nothing "
            "here claims it works with AI off, because there is no it.",
        ),
        (
            "Readiness (5.3)",
            "NOT BUILT",
            "no calibration, no base-rate null comparison, no code. "
            "Appendix B has not been run.",
        ),
    ]


def print_status() -> None:
    print("")
    print("=" * 78)
    print("AI OFF -- SCORE PATH STATUS (BUILD-DOC 7.6, 5.1-5.3)")
    print("=" * 78)
    print("BUILD-DOC 7.6 requires all three scores to compute with AI off.")
    print("One of the three has a real, exercised input. Two do not exist.")
    print("")
    for name, status, evidence in score_path_status():
        print("  {:<18} {}".format(name, status))
        print("      {}".format(evidence))
    print("")
    print("Generation with AI off:    REFUSES (AiDisabled), network poisoned")
    print("AI retrieval with AI off:  REFUSES (AiDisabled)")
    print("Retrieval with AI off:     WORKS, falls back to bm25")
    print("=" * 78)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False).result
    print_status()
    sys.exit(0 if result.wasSuccessful() else 1)
