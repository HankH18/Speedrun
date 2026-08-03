# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Traceability enforcement -- a BUILD ERROR, not a lint (BUILD-DOC 7.1).

    "A card with no traceable span is a build error, not a warning."
    "AI claims with no traceable source -> AI section zero."  (BUILD-DOC 17)

The difference between a lint and a build error is not the wording of the
message. It is whether the artefact can exist while the condition is violated.
So the enforcement lives at the *emission boundary*: `generation.emit_notes()`
routes every generated note through `enforce()` before anything is written, and
`enforce()` raises. There is no flag to downgrade it, no `--warn-only`, and no
code path that emits an unchecked note. Running this module as a script over an
already-written notes file exits **2**, non-zero and loud, so a build step that
calls it cannot pass by accident.

WHAT COUNTS AS TRACEABLE
------------------------
All five, on every note:

1. `source_id` present, and registered in the `SourceStore` -- a citation to a
   document nobody can produce is not a citation.
2. `span_start` / `span_end` present, integral, non-negative, `end > start`,
   and inside the document's length.
3. `quote` present and **character-identical** to `source.text[start:end]`.
   This is the check that makes a span *resolve into the cited source* rather
   than merely being a pair of numbers of the right shape. Without it, a note
   citing the right document with arbitrary offsets passes every structural
   test while pointing at unrelated words.
4. `source_sha256` equal to the checksum of the registered document. Offsets
   are only meaningful against one exact version of a text; if the document has
   been re-fetched, re-encoded, or edited, every stored span has shifted and
   the note is no longer traceable even though it still looks well-formed.
5. The `speedrun::ai::generated` tag, so AI content can be excluded wholesale
   (BUILD-DOC 7.1).

Every violation is collected before failing, because fixing them one
error-per-run is how people give up and add a `--warn-only`.

CLI
---
    python3 speedrun-analysis/ai/traceability.py \
        --notes NOTES.json --sources MANIFEST.json [--json]

Exit codes: 0 every note traceable; 2 at least one is not; 3 bad usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterable
from typing import List
from typing import NoReturn
from typing import Optional
from typing import Sequence
from typing import TextIO
from typing import Tuple

if __package__ in (None, ""):  # invoked as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.sources import SourceStore  # noqa: E402
from ai.sources import UnknownSource  # noqa: E402

#: Required on every AI-generated note (BUILD-DOC 7.1).
AI_TAG = "speedrun::ai::generated"

#: Process exit code for untraceable output. Non-zero on purpose.
EXIT_UNTRACEABLE = 2
EXIT_USAGE = 3

# -- violation codes -------------------------------------------------------

MISSING_SOURCE_ID = "MISSING_SOURCE_ID"
UNRESOLVABLE_SOURCE_ID = "UNRESOLVABLE_SOURCE_ID"
MISSING_SPAN = "MISSING_SPAN"
MALFORMED_SPAN = "MALFORMED_SPAN"
SPAN_OUT_OF_RANGE = "SPAN_OUT_OF_RANGE"
MISSING_QUOTE = "MISSING_QUOTE"
SPAN_TEXT_MISMATCH = "SPAN_TEXT_MISMATCH"
MISSING_SOURCE_CHECKSUM = "MISSING_SOURCE_CHECKSUM"
SOURCE_CHANGED = "SOURCE_CHANGED"
MISSING_AI_TAG = "MISSING_AI_TAG"

ALL_CODES: Tuple[str, ...] = (
    MISSING_SOURCE_ID,
    UNRESOLVABLE_SOURCE_ID,
    MISSING_SPAN,
    MALFORMED_SPAN,
    SPAN_OUT_OF_RANGE,
    MISSING_QUOTE,
    SPAN_TEXT_MISMATCH,
    MISSING_SOURCE_CHECKSUM,
    SOURCE_CHANGED,
    MISSING_AI_TAG,
)


@dataclass(frozen=True)
class Violation:
    note_id: str
    code: str
    detail: str

    def __str__(self) -> str:
        return "note {}: {}: {}".format(self.note_id, self.code, self.detail)

    def to_dict(self) -> Dict[str, str]:
        return {"note_id": self.note_id, "code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class GeneratedNote:
    """One AI-generated note and its provenance.

    Fields are `Optional` so that a malformed note can be *represented* and
    then rejected with a specific reason. Making them required at construction
    would move the failure to a `TypeError` with no note id in it, which is
    worse to debug and untestable as a policy.
    """

    note_id: str
    front: str = ""
    back: str = ""
    source_id: Optional[str] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    quote: Optional[str] = None
    source_sha256: Optional[str] = None
    tags: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratedNote":
        if "note_id" not in data:
            raise ValueError("note record has no note_id: {!r}".format(data))
        return cls(
            note_id=str(data["note_id"]),
            front=str(data.get("front", "")),
            back=str(data.get("back", "")),
            source_id=data.get("source_id"),
            span_start=data.get("span_start"),
            span_end=data.get("span_end"),
            quote=data.get("quote"),
            source_sha256=data.get("source_sha256"),
            tags=tuple(data.get("tags", ())),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "note_id": self.note_id,
            "front": self.front,
            "back": self.back,
            "source_id": self.source_id,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "quote": self.quote,
            "source_sha256": self.source_sha256,
            "tags": list(self.tags),
        }


class TraceabilityError(Exception):
    """Raised by `enforce()`. Carries every violation, not just the first."""

    def __init__(self, violations: Sequence[Violation]) -> None:
        self.violations: Tuple[Violation, ...] = tuple(violations)
        super().__init__(
            "{} untraceable note(s); {} violation(s)".format(
                len({v.note_id for v in self.violations}), len(self.violations)
            )
        )

    def codes(self) -> Tuple[str, ...]:
        return tuple(v.code for v in self.violations)


def _is_int(value: Any) -> bool:
    # bool is a subclass of int; True as an offset is a bug, not an offset.
    return isinstance(value, int) and not isinstance(value, bool)


def check_note(note: GeneratedNote, store: SourceStore) -> List[Violation]:
    """Every way `note` fails to be traceable. Empty list means traceable."""
    out: List[Violation] = []

    def add(code: str, detail: str) -> None:
        out.append(Violation(note_id=note.note_id, code=code, detail=detail))

    if AI_TAG not in note.tags:
        add(
            MISSING_AI_TAG,
            "missing {!r}; AI notes must be excludable wholesale "
            "(BUILD-DOC 7.1). tags={}".format(AI_TAG, list(note.tags)),
        )

    # -- the citation ----------------------------------------------------
    if not note.source_id:
        add(MISSING_SOURCE_ID, "no source_id: the claim traces to nothing")
        source = None
    else:
        try:
            source = store.get(note.source_id)
        except UnknownSource as exc:
            add(UNRESOLVABLE_SOURCE_ID, str(exc))
            source = None

    # -- the span --------------------------------------------------------
    start, end = note.span_start, note.span_end
    if start is None or end is None:
        add(
            MISSING_SPAN,
            "span_start={!r} span_end={!r}; a note with no character span is a "
            "BUILD ERROR, not a warning (BUILD-DOC 7.1)".format(start, end),
        )
        return out
    if not _is_int(start) or not _is_int(end):
        add(
            MALFORMED_SPAN,
            "span bounds must be integers, got {!r} and {!r}".format(start, end),
        )
        return out
    if start < 0 or end <= start:
        add(
            MALFORMED_SPAN,
            "span [{}, {}) is empty, inverted, or negative and cites "
            "nothing".format(start, end),
        )
        return out

    if source is None:
        # The span cannot be checked against a document we do not have. The
        # unresolvable citation is already reported; do not invent a second
        # failure mode for it.
        return out

    if end > len(source.text):
        add(
            SPAN_OUT_OF_RANGE,
            "span [{}, {}) runs past source {!r}, which is {} characters".format(
                start, end, note.source_id, len(source.text)
            ),
        )
        return out

    # -- the span must resolve INTO the cited source ----------------------
    actual = source.text[start:end]
    if note.quote is None:
        add(
            MISSING_QUOTE,
            "no quote recorded, so the span cannot be shown to resolve into "
            "source {!r}; offsets alone are unverifiable".format(note.source_id),
        )
    elif note.quote != actual:
        add(
            SPAN_TEXT_MISMATCH,
            "span [{}, {}) of source {!r} contains {!r}, but the note cites "
            "{!r}; the span does not resolve into the cited source".format(
                start, end, note.source_id, _clip(actual), _clip(note.quote)
            ),
        )

    # -- the span must be against THIS version of the source --------------
    if not note.source_sha256:
        add(
            MISSING_SOURCE_CHECKSUM,
            "no source_sha256; a character span is only meaningful against one "
            "exact version of a document",
        )
    elif note.source_sha256 != source.sha256:
        add(
            SOURCE_CHANGED,
            "note was generated against source {!r} with sha256 {}, but the "
            "registered document has sha256 {}; every offset recorded against "
            "the old text has shifted".format(
                note.source_id, note.source_sha256, source.sha256
            ),
        )

    return out


def _clip(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def check_notes(
    notes: Iterable[GeneratedNote], store: SourceStore
) -> List[Violation]:
    """Every violation across every note. Never stops at the first."""
    violations: List[Violation] = []
    for note in notes:
        violations.extend(check_note(note, store))
    return violations


def enforce(
    notes: Iterable[GeneratedNote], store: SourceStore
) -> List[GeneratedNote]:
    """Return the notes, or raise `TraceabilityError`. There is no third option.

    No `strict=` parameter and no warn mode: the whole point of BUILD-DOC 7.1
    is that this cannot be downgraded.
    """
    materialised = list(notes)
    violations = check_notes(materialised, store)
    if violations:
        raise TraceabilityError(violations)
    return materialised


def format_failure(violations: Sequence[Violation]) -> str:
    """The loud message. Deliberately hard to mistake for a warning."""
    bad_notes = sorted({v.note_id for v in violations})
    lines = [
        "",
        "=" * 78,
        "BUILD ERROR: UNTRACEABLE AI OUTPUT",
        "=" * 78,
        "{} note(s) failed traceability with {} violation(s).".format(
            len(bad_notes), len(violations)
        ),
        "",
        "BUILD-DOC 7.1: a card with no traceable span is a build error, not a",
        "warning. BUILD-DOC 17: AI claims with no traceable source score zero",
        "for the entire AI section. Nothing is emitted.",
        "",
    ]
    for violation in violations:
        lines.append("  - {}".format(violation))
    lines.extend(["", "=" * 78, ""])
    return "\n".join(lines)


def fail_build(
    violations: Sequence[Violation], stream: Optional[TextIO] = None
) -> NoReturn:
    """Print the failure and exit non-zero. Does not return."""
    (stream or sys.stderr).write(format_failure(violations))
    raise SystemExit(EXIT_UNTRACEABLE)


# -- CLI -------------------------------------------------------------------


def load_notes(path: Path) -> List[GeneratedNote]:
    """Load `[{...}, ...]` or `{"notes": [...]}` from JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    records = data["notes"] if isinstance(data, dict) else data
    return [GeneratedNote.from_dict(record) for record in records]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail the build if any AI-generated note lacks a resolvable "
            "source_id and character span (BUILD-DOC 7.1)."
        )
    )
    parser.add_argument("--notes", required=True, type=Path, help="notes JSON")
    parser.add_argument(
        "--sources", required=True, type=Path, help="source manifest JSON"
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable report on stdout"
    )
    args = parser.parse_args(argv)

    try:
        notes = load_notes(args.notes)
        store = SourceStore.from_manifest(args.sources)
    except Exception as exc:  # noqa: BLE001 - report and exit, never proceed
        sys.stderr.write("cannot run the traceability check: {}\n".format(exc))
        return EXIT_USAGE

    violations = check_notes(notes, store)

    if args.json:
        print(
            json.dumps(
                {
                    "checked_notes": len(notes),
                    "registered_sources": store.ids(),
                    "violations": [v.to_dict() for v in violations],
                    "traceable": not violations,
                },
                indent=4,
                sort_keys=True,
            )
        )
    if violations:
        sys.stderr.write(format_failure(violations))
        return EXIT_UNTRACEABLE
    if not args.json:
        print(
            "traceability OK: {} note(s), all with a resolvable source_id, an "
            "in-range character span whose text matches the cited source, a "
            "matching source checksum, and the {} tag.".format(len(notes), AI_TAG)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
