# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The source registry -- what a `source_id` on a generated note resolves to.

BUILD-DOC 7.1 requires every generated note to carry a `source_id` and a
character span. A span is only meaningful against a specific byte-for-byte
version of a specific document, so this module carries three things together
and refuses to separate them:

  * the `source_id`,
  * the document text,
  * the SHA-256 of that text.

If the document changes, every stored offset silently shifts and every note
that cites it starts pointing at the wrong words. That failure is invisible at
read time, which is exactly why the checksum is stored on the note as well as
here, and why a mismatch is an error rather than a warning
(`traceability.SOURCE_CHANGED`).

**No real source document is registered in this tree.** BUILD-DOC 7.1 wants one
real document; obtaining and licence-clearing it is a separate task. The store
therefore exists, is fully tested, and is empty. That is stated rather than
papered over with a placeholder corpus: an empty registry makes every
generation attempt fail loudly, which is the correct behaviour today.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping


class SourceError(RuntimeError):
    """Base class for every failure to resolve a citation."""


class UnknownSource(SourceError):
    """The cited `source_id` is not registered. The citation is unresolvable."""


class SourceChanged(SourceError):
    """The document on disk no longer matches the checksum recorded for it."""


class SpanUnresolvable(SourceError):
    """The span does not address real text inside the cited source."""


def sha256_of_text(text: str) -> str:
    """SHA-256 of the UTF-8 encoding of `text`."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Source:
    """One registered source document, with the checksum of its exact text."""

    source_id: str
    text: str
    sha256: str
    origin: str

    @classmethod
    def from_text(cls, source_id: str, text: str, origin: str = "<in-memory>") -> "Source":
        return cls(
            source_id=source_id,
            text=text,
            sha256=sha256_of_text(text),
            origin=origin,
        )


class SourceStore:
    """A resolvable set of sources. Empty is a legitimate -- and current -- state."""

    def __init__(self, sources: Iterable[Source]) -> None:
        self._by_id: Dict[str, Source] = {}
        for source in sources:
            if source.source_id in self._by_id:
                raise SourceError(
                    "duplicate source_id {!r}: a citation to it would be "
                    "ambiguous".format(source.source_id)
                )
            self._by_id[source.source_id] = source

    # -- construction ----------------------------------------------------

    @classmethod
    def from_texts(cls, mapping: Mapping[str, str]) -> "SourceStore":
        """Build from `{source_id: text}`. Used by tests and fixtures."""
        return cls(Source.from_text(sid, text) for sid, text in mapping.items())

    @classmethod
    def from_directory(
        cls, directory: Path, pattern: str = "*.txt"
    ) -> "SourceStore":
        """Register every matching file in `directory`, keyed by filename stem.

        Deliberately schema-free: it reads the text files and computes the
        checksums itself, so it does not depend on the shape of any sidecar
        metadata. That keeps the traceability machinery usable against the
        licence-vetted documents in `speedrun-analysis/sources/` without
        coupling to how their provenance records happen to be written.

        A missing directory yields an empty store rather than an error -- an
        empty registry already makes every generation attempt fail loudly.
        """
        directory = Path(directory)
        if not directory.is_dir():
            return cls([])
        sources: List[Source] = []
        for path in sorted(directory.glob(pattern)):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            sources.append(
                Source(
                    source_id=path.stem,
                    text=text,
                    sha256=sha256_of_text(text),
                    origin=str(path),
                )
            )
        return cls(sources)

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> "SourceStore":
        """Build from a manifest JSON file.

        Manifest shape::

            {"sources": [{"source_id": "...", "path": "...", "sha256": "..."}]}

        `path` is resolved relative to the manifest. The declared checksum is
        verified against the file on disk; a mismatch raises `SourceChanged`
        rather than loading text whose offsets can no longer be trusted.
        """
        manifest_path = Path(manifest_path)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = data.get("sources", [])
        sources: List[Source] = []
        for entry in entries:
            source_id = entry["source_id"]
            path = (manifest_path.parent / entry["path"]).resolve()
            text = path.read_text(encoding="utf-8")
            actual = sha256_of_text(text)
            declared = entry.get("sha256")
            if declared and declared != actual:
                raise SourceChanged(
                    "source {!r} at {} has sha256 {} but the manifest declares "
                    "{}. Every character span recorded against this document is "
                    "now suspect; refusing to load.".format(
                        source_id, path, actual, declared
                    )
                )
            sources.append(
                Source(source_id=source_id, text=text, sha256=actual, origin=str(path))
            )
        return cls(sources)

    # -- lookup ----------------------------------------------------------

    def ids(self) -> List[str]:
        return sorted(self._by_id)

    def __len__(self) -> int:
        return len(self._by_id)

    def has(self, source_id: str) -> bool:
        return source_id in self._by_id

    def get(self, source_id: str) -> Source:
        try:
            return self._by_id[source_id]
        except KeyError:
            raise UnknownSource(
                "no source registered under {!r}; registered ids: {}".format(
                    source_id, self.ids() or "(none)"
                )
            ) from None

    def resolve(self, source_id: str, start: int, end: int) -> str:
        """Return the exact text of `[start, end)` in the cited source.

        Raises `UnknownSource` if the citation names nothing, and
        `SpanUnresolvable` if the offsets do not address real text.
        """
        source = self.get(source_id)
        length = len(source.text)
        if not isinstance(start, int) or not isinstance(end, int):
            raise SpanUnresolvable(
                "span bounds must be integers, got {!r} and {!r}".format(start, end)
            )
        if start < 0 or end < 0:
            raise SpanUnresolvable("negative span bound: [{}, {})".format(start, end))
        if end <= start:
            raise SpanUnresolvable(
                "empty or inverted span [{}, {}): a zero-width span cites "
                "nothing".format(start, end)
            )
        if end > length:
            raise SpanUnresolvable(
                "span [{}, {}) runs past the end of source {!r}, which is {} "
                "characters".format(start, end, source_id, length)
            )
        return source.text[start:end]
