# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Proof that untraceable AI output is a BUILD ERROR (BUILD-DOC 7.1).

    python3 speedrun-analysis/evals/test_traceability.py

Standard library `unittest`; exits non-zero on any failure.

The two tests the brief names explicitly are
`test_note_with_no_span_fails` and `test_span_that_does_not_resolve_into_the_
cited_source_fails`. The rest close the gaps that would otherwise let an
untraceable note through a check that only looked like it was working: an
out-of-range span, a span pointing into a *different* registered document, a
citation to a document nobody has, a document that changed after generation,
and a note missing the exclusion tag.

Two of them are about the difference between a lint and a build error:

  * `test_emission_boundary_refuses_to_emit_and_exits_2` -- the enforcement
    sits on the only path out of generation, so an untraceable note cannot be
    written even by a caller who never runs the checker.
  * `test_cli_exits_2_and_prints_loudly` -- run as a build step, it fails the
    process with a non-zero code and a banner, not a warning line.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

_ANALYSIS_ROOT = Path(__file__).resolve().parent.parent
if str(_ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS_ROOT))

from ai import generation  # noqa: E402
from ai import traceability  # noqa: E402
from ai.sources import SourceStore  # noqa: E402
from ai.sources import sha256_of_text  # noqa: E402
from ai.traceability import AI_TAG  # noqa: E402
from ai.traceability import GeneratedNote  # noqa: E402
from ai.traceability import TraceabilityError  # noqa: E402

SOURCE_A = (
    "The pulmonary artery leaves the right ventricle and carries blood with a "
    "low oxygen content towards the lungs."
)
SOURCE_B = (
    "Antidiuretic hormone increases water permeability of the collecting duct "
    "by inserting aquaporin channels into the apical membrane."
)

#: A span inside SOURCE_A, chosen so the quote is checkable by eye.
SPAN_A = (4, 20)  # "pulmonary artery"


def make_store() -> SourceStore:
    return SourceStore.from_texts({"src-a": SOURCE_A, "src-b": SOURCE_B})


def good_note(**overrides: Any) -> GeneratedNote:
    """A fully traceable note. Tests break exactly one thing about it."""
    fields: Dict[str, Any] = {
        "note_id": "n1",
        "front": "Which vessel leaves the right ventricle?",
        "back": "The pulmonary artery.",
        "source_id": "src-a",
        "span_start": SPAN_A[0],
        "span_end": SPAN_A[1],
        "quote": SOURCE_A[SPAN_A[0] : SPAN_A[1]],
        "source_sha256": sha256_of_text(SOURCE_A),
        "tags": (AI_TAG, "speedrun::topic::cardio"),
    }
    fields.update(overrides)
    return GeneratedNote(**fields)


class TraceabilityChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.store = make_store()

    def codes_for(self, note: GeneratedNote) -> List[str]:
        return [v.code for v in traceability.check_note(note, self.store)]

    # -- the baseline: a good note must pass, or nothing below means anything

    def test_fully_traceable_note_passes(self) -> None:
        note = good_note()
        self.assertEqual(self.codes_for(note), [])
        self.assertEqual(traceability.enforce([note], self.store), [note])
        # The quote really is what the span addresses.
        self.assertEqual(note.quote, "pulmonary artery")

    # -- required by the brief: no span -> FAIL

    def test_note_with_no_span_fails(self) -> None:
        for missing in ({"span_start": None}, {"span_end": None},
                        {"span_start": None, "span_end": None}):
            with self.subTest(missing=sorted(missing)):
                note = good_note(**missing)
                self.assertIn(traceability.MISSING_SPAN, self.codes_for(note))
                with self.assertRaises(TraceabilityError):
                    traceability.enforce([note], self.store)

    # -- required by the brief: a span that does not resolve into the cited
    #    source -> FAIL. Three separate ways it can fail to resolve.

    def test_span_that_does_not_resolve_into_the_cited_source_fails(self) -> None:
        # The offsets are in range and well-formed, but they address different
        # text than the note claims. Structurally perfect, substantively a lie.
        note = good_note(span_start=0, span_end=3)  # "The", not "pulmonary artery"
        codes = self.codes_for(note)
        self.assertIn(traceability.SPAN_TEXT_MISMATCH, codes)
        with self.assertRaises(TraceabilityError):
            traceability.enforce([note], self.store)

    def test_span_belonging_to_a_different_source_fails(self) -> None:
        # The quote is real text -- from src-b. The note cites src-a. A checker
        # that only asked "does this text exist somewhere?" would pass it.
        quote_from_b = SOURCE_B[0:19]
        note = good_note(source_id="src-a", quote=quote_from_b)
        self.assertIn(traceability.SPAN_TEXT_MISMATCH, self.codes_for(note))

    def test_span_out_of_range_fails(self) -> None:
        note = good_note(span_start=4, span_end=len(SOURCE_A) + 50)
        self.assertIn(traceability.SPAN_OUT_OF_RANGE, self.codes_for(note))

    def test_empty_and_inverted_spans_fail(self) -> None:
        for start, end in ((10, 10), (20, 4), (-1, 5)):
            with self.subTest(span=(start, end)):
                note = good_note(span_start=start, span_end=end)
                self.assertIn(traceability.MALFORMED_SPAN, self.codes_for(note))

    def test_non_integer_span_fails(self) -> None:
        for bad in ("4", 4.5, True):
            with self.subTest(bound=repr(bad)):
                note = good_note(span_start=bad)
                self.assertIn(traceability.MALFORMED_SPAN, self.codes_for(note))

    # -- the citation itself

    def test_missing_source_id_fails(self) -> None:
        note = good_note(source_id=None)
        self.assertIn(traceability.MISSING_SOURCE_ID, self.codes_for(note))

    def test_unregistered_source_id_fails(self) -> None:
        note = good_note(source_id="src-nobody-has")
        self.assertIn(traceability.UNRESOLVABLE_SOURCE_ID, self.codes_for(note))

    def test_missing_quote_fails(self) -> None:
        note = good_note(quote=None)
        self.assertIn(traceability.MISSING_QUOTE, self.codes_for(note))

    # -- the span must be against THIS version of the document

    def test_source_changed_since_generation_fails(self) -> None:
        note = good_note(source_sha256=sha256_of_text("some earlier text"))
        self.assertIn(traceability.SOURCE_CHANGED, self.codes_for(note))

    def test_missing_source_checksum_fails(self) -> None:
        note = good_note(source_sha256=None)
        self.assertIn(traceability.MISSING_SOURCE_CHECKSUM, self.codes_for(note))

    # -- wholesale exclusion (BUILD-DOC 7.1)

    def test_missing_ai_tag_fails(self) -> None:
        note = good_note(tags=("speedrun::topic::cardio",))
        self.assertIn(traceability.MISSING_AI_TAG, self.codes_for(note))

    # -- every violation is reported, not just the first

    def test_all_violations_are_collected(self) -> None:
        note = good_note(source_id=None, span_start=None, tags=())
        codes = set(self.codes_for(note))
        self.assertIn(traceability.MISSING_SOURCE_ID, codes)
        self.assertIn(traceability.MISSING_SPAN, codes)
        self.assertIn(traceability.MISSING_AI_TAG, codes)

    def test_one_bad_note_fails_the_whole_batch(self) -> None:
        notes = [good_note(note_id="ok1"), good_note(note_id="bad", span_end=None)]
        with self.assertRaises(TraceabilityError) as caught:
            traceability.enforce(notes, self.store)
        self.assertEqual(
            {v.note_id for v in caught.exception.violations}, {"bad"}
        )


class BuildErrorSemantics(unittest.TestCase):
    """A lint can be ignored. These prove this one cannot be."""

    def setUp(self) -> None:
        self.store = make_store()

    def test_emission_boundary_refuses_to_emit_and_exits_2(self) -> None:
        # emit_notes() is the only sanctioned way generated notes leave the
        # generator. A span-less note does not come back with a warning
        # attached -- the process ends.
        import io

        stream = io.StringIO()
        with self.assertRaises(SystemExit) as caught:
            generation.emit_notes(
                [good_note(span_start=None, span_end=None)], self.store, stream
            )
        self.assertEqual(caught.exception.code, traceability.EXIT_UNTRACEABLE)
        message = stream.getvalue()
        self.assertIn("BUILD ERROR: UNTRACEABLE AI OUTPUT", message)
        self.assertIn(traceability.MISSING_SPAN, message)

    def test_emission_boundary_passes_good_notes_through(self) -> None:
        notes = [good_note()]
        self.assertEqual(generation.emit_notes(notes, self.store), notes)

    def test_enforce_has_no_warn_only_switch(self) -> None:
        # If someone adds one, this fails. The absence of the escape hatch is
        # the mechanism, so it is asserted rather than assumed.
        import inspect

        params = set(inspect.signature(traceability.enforce).parameters)
        self.assertEqual(params, {"notes", "store"})
        emit_params = set(inspect.signature(generation.emit_notes).parameters)
        self.assertEqual(emit_params, {"notes", "store", "stream"})


class CommandLineContract(unittest.TestCase):
    """The check as a build step: non-zero exit, loud message."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "a.txt").write_text(SOURCE_A, encoding="utf-8")
        manifest = {
            "sources": [
                {
                    "source_id": "src-a",
                    "path": "a.txt",
                    "sha256": sha256_of_text(SOURCE_A),
                }
            ]
        }
        self.manifest = self.dir / "sources.json"
        self.manifest.write_text(json.dumps(manifest, indent=4), encoding="utf-8")
        self.script = str(_ANALYSIS_ROOT / "ai" / "traceability.py")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, notes: List[Dict[str, Any]]) -> subprocess.CompletedProcess:
        path = self.dir / "notes.json"
        path.write_text(json.dumps(notes, indent=4), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                self.script,
                "--notes",
                str(path),
                "--sources",
                str(self.manifest),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

    def test_cli_exits_0_on_traceable_notes(self) -> None:
        result = self.run_cli([good_note().to_dict()])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("traceability OK", result.stdout)

    def test_cli_exits_2_and_prints_loudly(self) -> None:
        result = self.run_cli([good_note(span_start=None, span_end=None).to_dict()])
        self.assertEqual(result.returncode, traceability.EXIT_UNTRACEABLE)
        self.assertIn("BUILD ERROR: UNTRACEABLE AI OUTPUT", result.stderr)

    def test_cli_detects_a_source_edited_after_generation(self) -> None:
        # The note is correct against the text it was generated from. The file
        # on disk has since changed, so every offset in it has moved.
        note = good_note().to_dict()
        (self.dir / "a.txt").write_text("Preface. " + SOURCE_A, encoding="utf-8")
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        # Drop the declared checksum so the manifest itself loads, and let the
        # note-level checksum catch the change.
        manifest["sources"][0].pop("sha256")
        self.manifest.write_text(json.dumps(manifest, indent=4), encoding="utf-8")
        result = self.run_cli([note])
        self.assertEqual(result.returncode, traceability.EXIT_UNTRACEABLE)
        self.assertIn(traceability.SOURCE_CHANGED, result.stderr)


class RealSourceDocuments(unittest.TestCase):
    """The same enforcement, against real registered source text.

    Fixtures prove the logic; they do not prove it survives contact with a
    real document (multi-byte characters, newlines, tens of thousands of
    offsets). `speedrun-analysis/sources/` is populated by a separate task, so
    this skips loudly when it is empty rather than failing on someone else's
    schedule -- but it exercises real text the moment there is any.
    """

    def setUp(self) -> None:
        self.store = SourceStore.from_directory(_ANALYSIS_ROOT / "sources")
        if len(self.store) == 0:
            self.skipTest(
                "no documents in speedrun-analysis/sources/ yet; the "
                "traceability machinery is proven on fixtures only"
            )

    def test_spans_resolve_against_a_real_document(self) -> None:
        source_id = self.store.ids()[0]
        source = self.store.get(source_id)
        self.assertGreater(len(source.text), 100)
        start = len(source.text) // 3
        end = start + 40
        quote = source.text[start:end]

        note = GeneratedNote(
            note_id="real-1",
            front="(demonstration note, not AI-generated)",
            back="(demonstration note, not AI-generated)",
            source_id=source_id,
            span_start=start,
            span_end=end,
            quote=quote,
            source_sha256=source.sha256,
            tags=(AI_TAG,),
        )
        self.assertEqual(traceability.check_note(note, self.store), [])

    def test_off_by_one_against_a_real_document_is_caught(self) -> None:
        # The failure mode that matters at scale: offsets that drifted by a
        # single character still look entirely well-formed.
        source_id = self.store.ids()[0]
        source = self.store.get(source_id)
        start = len(source.text) // 3
        end = start + 40
        note = GeneratedNote(
            note_id="real-2",
            source_id=source_id,
            span_start=start + 1,
            span_end=end + 1,
            quote=source.text[start:end],
            source_sha256=source.sha256,
            tags=(AI_TAG,),
        )
        codes = [v.code for v in traceability.check_note(note, self.store)]
        self.assertIn(traceability.SPAN_TEXT_MISMATCH, codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
