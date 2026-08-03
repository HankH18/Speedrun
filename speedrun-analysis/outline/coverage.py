# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun coverage map -- BUILD-DOC section 4.

    python3 speedrun-analysis/outline/coverage.py --collection <collection.anki2>
    python3 speedrun-analysis/outline/coverage.py --self-test

Reads `outline.json` (the published USMLE Step 1 outline plus its published
weight ranges) and an Anki collection, and answers one question: **what percent
of the exam outline is covered by at least one card**, weighted by the published
item weights rather than by raw topic count.

Three honesty rules are wired into the code, not just the prose:

1.  No weight is ever invented. A topic whose `weight_source` is the literal
    string `UNKNOWN` is EXCLUDED from every weighted figure and reported
    separately as unweightable. It is never silently counted as zero.
2.  The published weights are RANGES, so the covered fraction is reported as a
    range. `Sum(covered w) / Sum(all w)` is monotone in every `w`, so its exact
    minimum over the published boxes puts each covered topic at its published
    low and each uncovered topic at its published high, and its exact maximum
    does the reverse. Those two endpoints are the reported range -- an exact
    bound, not an approximation, and not a midpoint dressed up as a point
    estimate.
3.  The outline's three axes (system / task / discipline) are independent
    classifications of the SAME item pool. Weights are never added across axes,
    so there is deliberately no single blended "percent of exam covered"
    number -- one figure per axis, or nothing.

The collection is opened READ-ONLY and is never written to. `--self-test`
proves it: it hashes the fixture collection before and after a full run and
fails if a single byte moved.

Standard library only. No third-party dependencies, by project rule.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

TAG_PREFIX = "speedrun::topic::"
UNKNOWN = "UNKNOWN"

EXIT_OK = 0
EXIT_OUTLINE = 2  # outline.json missing or malformed
EXIT_COLLECTION = 3  # collection missing, unreadable, or not an Anki collection
EXIT_ASSERT = 4  # covered/uncovered lists failed to account for every topic
EXIT_SELFTEST = 5  # --self-test found a real defect
EXIT_THRESHOLD = 6  # --fail-under not met
EXIT_USAGE = 64  # bad command line (EX_USAGE)

REQUIRED_TOPIC_KEYS = ("id", "name", "path", "weight_low", "weight_high", "weight_source")


class OutlineError(Exception):
    """outline.json is missing, unreadable, or does not satisfy the schema."""


class CollectionError(Exception):
    """The collection is missing, unreadable, or is not an Anki collection."""


class ExhaustivenessError(Exception):
    """The covered/uncovered split failed to account for every outline topic."""


# --------------------------------------------------------------------------
# Outline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Topic:
    id: str
    name: str
    axis: str
    level: Optional[int]
    path: Tuple[str, ...]
    tag: str
    weight_low: Optional[int]
    weight_high: Optional[int]
    weight_source: str

    @property
    def weighted(self) -> bool:
        return self.weight_source != UNKNOWN

    @property
    def tag_lower(self) -> str:
        return self.tag.lower()


@dataclass(frozen=True)
class Outline:
    path: Path
    sha256: str
    schema_version: str
    generated: str
    topics: Tuple[Topic, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bad(where: str, why: str) -> OutlineError:
    return OutlineError("{}: {}".format(where, why))


def _validate_weight(where: str, low: object, high: object, source: object) -> Tuple[Optional[int], Optional[int], str]:
    """Enforce the outline's own weight/provenance contract.

    Either the weight is published (both ends are ints, low <= high, and
    `weight_source` names where they came from), or it is not published (both
    ends null and `weight_source` is exactly "UNKNOWN"). Anything in between is
    malformed, because it would let an unsourced number reach the arithmetic.
    """
    if not isinstance(source, str) or not source:
        raise _bad(where, "weight_source must be a non-empty string")
    if source == UNKNOWN:
        if low is not None or high is not None:
            raise _bad(
                where,
                "weight_source is UNKNOWN but weight_low/weight_high are not both null "
                "(an unsourced number must not carry a value)",
            )
        return None, None, source
    if isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, int) or not isinstance(high, int):
        raise _bad(where, "weight_source is {!r} but weight_low/weight_high are not both integers".format(source))
    if low < 0 or high < 0:
        raise _bad(where, "negative weight ({}-{})".format(low, high))
    if low > high:
        raise _bad(where, "weight_low {} exceeds weight_high {}".format(low, high))
    return low, high, source


def _validate_path(where: str, raw_path: object) -> Tuple[str, ...]:
    if not isinstance(raw_path, list) or not raw_path:
        raise _bad(where, "path must be a non-empty list of strings")
    for component in raw_path:
        if not isinstance(component, str) or not component or component.strip() != component:
            raise _bad(where, "path component {!r} must be a non-empty string without surrounding whitespace".format(component))
        if "::" in component or any(ch.isspace() for ch in component):
            raise _bad(where, "path component {!r} must not contain '::' or whitespace".format(component))
    return tuple(raw_path)


def load_outline(path: Path) -> Outline:
    """Load and validate outline.json. Raises OutlineError on any problem."""
    if not path.exists():
        raise OutlineError(
            "outline.json not found at {}\n"
            "  This script cannot invent an outline. Generate the file first "
            "(see speedrun-analysis/outline/README.md) or pass --outline.".format(path)
        )
    if not path.is_file():
        raise OutlineError("outline path {} is not a regular file".format(path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OutlineError("could not read {}: {}".format(path, exc)) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OutlineError("{} is not valid JSON: {} (line {}, column {})".format(path, exc.msg, exc.lineno, exc.colno)) from exc

    if not isinstance(data, dict):
        raise OutlineError("{}: top level must be a JSON object, got {}".format(path, type(data).__name__))
    raw_topics = data.get("topics")
    if raw_topics is None:
        raise OutlineError("{}: no 'topics' key".format(path))
    if not isinstance(raw_topics, list):
        raise OutlineError("{}: 'topics' must be a list, got {}".format(path, type(raw_topics).__name__))
    if not raw_topics:
        raise OutlineError("{}: 'topics' is empty -- an empty outline cannot be a coverage denominator".format(path))

    topics: List[Topic] = []
    seen_ids: Set[str] = set()
    seen_tags: Set[str] = set()
    for index, raw in enumerate(raw_topics):
        where = "{}: topics[{}]".format(path, index)
        if not isinstance(raw, dict):
            raise _bad(where, "must be a JSON object, got {}".format(type(raw).__name__))
        missing = [key for key in REQUIRED_TOPIC_KEYS if key not in raw]
        if missing:
            raise _bad(where, "missing required key(s): {}".format(", ".join(missing)))

        topic_id = raw["id"]
        if not isinstance(topic_id, str) or not topic_id:
            raise _bad(where, "'id' must be a non-empty string")
        where = "{}: topic {!r}".format(path, topic_id)
        if topic_id in seen_ids:
            raise _bad(where, "duplicate id")
        seen_ids.add(topic_id)

        name = raw["name"]
        if not isinstance(name, str) or not name:
            raise _bad(where, "'name' must be a non-empty string")

        components = _validate_path(where, raw["path"])
        derived_tag = TAG_PREFIX + "::".join(components)
        declared_tag = raw.get("tag")
        if declared_tag is not None:
            if not isinstance(declared_tag, str):
                raise _bad(where, "'tag' must be a string when present")
            if declared_tag != derived_tag:
                raise _bad(
                    where,
                    "declared tag {!r} does not match the tag derived from 'path' ({!r}); "
                    "refusing to guess which one the cards use".format(declared_tag, derived_tag),
                )
        if derived_tag in seen_tags:
            raise _bad(where, "duplicate tag {!r} -- two topics cannot share one tag".format(derived_tag))
        seen_tags.add(derived_tag)

        low, high, source = _validate_weight(where, raw["weight_low"], raw["weight_high"], raw["weight_source"])

        axis = raw.get("axis", components[0])
        if not isinstance(axis, str) or not axis:
            raise _bad(where, "'axis' must be a non-empty string when present")
        level = raw.get("level")
        if level is not None and (isinstance(level, bool) or not isinstance(level, int)):
            raise _bad(where, "'level' must be an integer when present")

        topics.append(
            Topic(
                id=topic_id,
                name=name,
                axis=axis,
                level=level,
                path=components,
                tag=derived_tag,
                weight_low=low,
                weight_high=high,
                weight_source=source,
            )
        )

    schema_version = data.get("schema_version")
    generated = data.get("generated_utc_date")
    return Outline(
        path=path,
        sha256=_sha256_file(path),
        schema_version=schema_version if isinstance(schema_version, str) else "UNKNOWN",
        generated=generated if isinstance(generated, str) else "UNKNOWN",
        topics=tuple(topics),
    )


# --------------------------------------------------------------------------
# Collection (read-only)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectionCounts:
    path: Path
    sha256: str
    open_mode: str
    total_cards: int
    total_notes: int
    cards_by_tag: Dict[str, int]  # lowercased tag -> number of cards
    notes_by_tag: Dict[str, int]  # lowercased tag -> number of notes


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open `db_path` read-only. SQLite is told twice, by URI and by pragma."""
    con = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("pragma query_only = 1")
        con.execute("select count(*) from sqlite_master").fetchone()
    except sqlite3.Error:
        con.close()
        raise
    return con


@contextlib.contextmanager
def readonly_collection(path: Path, force_snapshot: bool = False):
    """Yield (connection, description). The collection file is never written.

    Anki opens its collection with `journal_mode=wal` and `locking_mode=exclusive`
    (rslib/src/storage/sqlite.rs), so a running Anki holds the file and a
    read-only opener may be refused. The fallback copies the collection (plus any
    `-wal`/`-shm` sidecars) into a temporary directory and reads the copy, which
    keeps the original untouched either way.
    """
    tmpdir: Optional[str] = None
    con: Optional[sqlite3.Connection] = None
    try:
        first_error: Optional[Exception] = None
        if not force_snapshot:
            try:
                con = _connect_readonly(path)
                description = "opened in place, read-only (URI mode=ro + PRAGMA query_only)"
            except sqlite3.Error as exc:
                first_error = exc
        if con is None:
            tmpdir = tempfile.mkdtemp(prefix="speedrun-coverage-")
            snapshot = Path(tmpdir) / path.name
            try:
                shutil.copy2(path, snapshot)
                for suffix in ("-wal", "-shm"):
                    sidecar = path.with_name(path.name + suffix)
                    if sidecar.exists():
                        shutil.copy2(sidecar, snapshot.with_name(snapshot.name + suffix))
            except OSError as exc:
                raise CollectionError("could not snapshot {}: {}".format(path, exc)) from exc
            try:
                con = _connect_readonly(snapshot)
            except sqlite3.Error as exc:
                raise CollectionError(
                    "could not open {} as a SQLite database, in place or via a snapshot copy.\n"
                    "  in-place error : {}\n"
                    "  snapshot error : {}".format(path, first_error, exc)
                ) from exc
            if force_snapshot:
                description = "read from a byte-for-byte snapshot copy (--force-snapshot)"
            else:
                description = "in-place open failed ({}); read from a byte-for-byte snapshot copy".format(first_error)
        yield con, description
    finally:
        if con is not None:
            con.close()
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)


def analyse_collection(path: Path, force_snapshot: bool = False) -> CollectionCounts:
    """Count, per `speedrun::topic::` tag, how many CARDS carry it."""
    if not path.exists():
        raise CollectionError(
            "collection not found: {}\n"
            "  Pass the path to a real .anki2 file with --collection, or run "
            "--self-test to exercise this script against a synthetic fixture.".format(path)
        )
    if not path.is_file():
        raise CollectionError("collection path {} is not a regular file".format(path))

    sha_before = _sha256_file(path)
    cards_by_tag: Dict[str, int] = {}
    notes_by_tag: Dict[str, int] = {}
    with readonly_collection(path, force_snapshot=force_snapshot) as (con, description):
        tables = {row[0] for row in con.execute("select name from sqlite_master where type = 'table'")}
        missing = [name for name in ("notes", "cards") if name not in tables]
        if missing:
            raise CollectionError(
                "{} is a SQLite database but not an Anki collection: no {} table(s). "
                "Tables present: {}".format(path, ", ".join(missing), ", ".join(sorted(tables)) or "(none)")
            )
        try:
            total_cards = int(con.execute("select count(*) from cards").fetchone()[0])
            total_notes = int(con.execute("select count(*) from notes").fetchone()[0])
            # One row per tagged note, with the number of cards that note owns.
            # SQLite's LIKE is ASCII case-insensitive, which matches Anki's own
            # case-insensitive tag handling; the prefix contains no % or _.
            rows = con.execute(
                "select n.tags, count(c.id) from notes n join cards c on c.nid = n.id "
                "where n.tags like ? group by n.id",
                ("%" + TAG_PREFIX + "%",),
            ).fetchall()
        except sqlite3.Error as exc:
            raise CollectionError("{}: unexpected schema, query failed: {}".format(path, exc)) from exc

        for raw_tags, card_count in rows:
            if not isinstance(raw_tags, str):
                continue
            for tag in set(raw_tags.split()):
                lowered = tag.lower()
                if lowered.startswith(TAG_PREFIX):
                    cards_by_tag[lowered] = cards_by_tag.get(lowered, 0) + int(card_count)
                    notes_by_tag[lowered] = notes_by_tag.get(lowered, 0) + 1

    sha_after = _sha256_file(path)
    if sha_before != sha_after:
        raise CollectionError(
            "{} changed while it was being read (sha256 {} -> {}). "
            "Refusing to report numbers from a moving target; close Anki and retry.".format(path, sha_before, sha_after)
        )

    return CollectionCounts(
        path=path,
        sha256=sha_before,
        open_mode=description,
        total_cards=total_cards,
        total_notes=total_notes,
        cards_by_tag=cards_by_tag,
        notes_by_tag=notes_by_tag,
    )


# --------------------------------------------------------------------------
# Coverage arithmetic
# --------------------------------------------------------------------------


def _covered_share(covered: Sequence[Topic], uncovered: Sequence[Topic]) -> Tuple[Optional[float], Optional[float]]:
    """Exact min/max of Sum(covered w) / Sum(all w) over the published ranges.

    Each true weight w_i is known only to lie in [low_i, high_i]. The ratio is
    increasing in every covered w_i and decreasing in every uncovered w_i, so
    the extremes sit at the corners of the box: minimum with covered at their
    lows and uncovered at their highs, maximum the other way round. Returns
    (None, None) when there is no published weight to divide by -- never 0.0,
    which would read as "nothing is covered".
    """
    covered_low = sum(t.weight_low or 0 for t in covered)
    covered_high = sum(t.weight_high or 0 for t in covered)
    uncovered_low = sum(t.weight_low or 0 for t in uncovered)
    uncovered_high = sum(t.weight_high or 0 for t in uncovered)

    low_denominator = covered_low + uncovered_high
    high_denominator = covered_high + uncovered_low
    if low_denominator <= 0 or high_denominator <= 0:
        return None, None
    return covered_low / low_denominator, covered_high / high_denominator


def _subtree_cards(topic: Topic, cards_by_tag: Dict[str, int]) -> int:
    prefix = topic.tag_lower + "::"
    total = cards_by_tag.get(topic.tag_lower, 0)
    for tag, count in cards_by_tag.items():
        if tag.startswith(prefix):
            total += count
    return total


def build_report(outline: Outline, counts: CollectionCounts, covered_by: str) -> dict:
    """Compute the whole coverage map. Pure function of its two inputs."""
    exact: Dict[str, int] = {}
    subtree: Dict[str, int] = {}
    for topic in outline.topics:
        exact[topic.id] = counts.cards_by_tag.get(topic.tag_lower, 0)
        subtree[topic.id] = _subtree_cards(topic, counts.cards_by_tag)

    def split(mode: str) -> Tuple[List[Topic], List[Topic]]:
        source = exact if mode == "exact" else subtree
        covered = [t for t in outline.topics if source[t.id] >= 1]
        uncovered = [t for t in outline.topics if source[t.id] < 1]
        return covered, uncovered

    splits = {mode: split(mode) for mode in ("exact", "subtree")}

    # Requirement 3, enforced rather than asserted in prose: every topic lands
    # in exactly one of the two lists, under both definitions.
    all_ids = {t.id for t in outline.topics}
    for mode, (covered, uncovered) in splits.items():
        covered_ids = {t.id for t in covered}
        uncovered_ids = {t.id for t in uncovered}
        if covered_ids & uncovered_ids:
            raise ExhaustivenessError("[{}] {} topic(s) are in BOTH lists".format(mode, len(covered_ids & uncovered_ids)))
        if covered_ids | uncovered_ids != all_ids:
            missed = all_ids - (covered_ids | uncovered_ids)
            raise ExhaustivenessError(
                "[{}] {} topic(s) are in NEITHER list, e.g. {}".format(mode, len(missed), sorted(missed)[:5])
            )
        if len(covered) + len(uncovered) != len(outline.topics):
            raise ExhaustivenessError("[{}] list lengths do not sum to the topic count".format(mode))

    axes: List[str] = []
    for topic in outline.topics:
        if topic.axis not in axes:
            axes.append(topic.axis)

    axis_reports = []
    for axis in axes:
        in_axis = [t for t in outline.topics if t.axis == axis]
        weighted = [t for t in in_axis if t.weighted]
        total_low = sum(t.weight_low or 0 for t in weighted)
        total_high = sum(t.weight_high or 0 for t in weighted)
        entry = {
            "axis": axis,
            "topics": len(in_axis),
            "weighted_topics": len(weighted),
            "unweightable_topics": len(in_axis) - len(weighted),
            "published_total_low": total_low,
            "published_total_high": total_high,
            "partition_consistent": bool(weighted) and total_low <= 100 <= total_high,
            "modes": {},
        }
        for mode, (covered, _uncovered) in splits.items():
            covered_ids = {t.id for t in covered}
            weighted_covered = [t for t in weighted if t.id in covered_ids]
            weighted_uncovered = [t for t in weighted if t.id not in covered_ids]
            share_low, share_high = _covered_share(weighted_covered, weighted_uncovered)
            entry["modes"][mode] = {
                "weighted_covered": len(weighted_covered),
                "weighted_uncovered": len(weighted_uncovered),
                "covered_weight_low": sum(t.weight_low or 0 for t in weighted_covered),
                "covered_weight_high": sum(t.weight_high or 0 for t in weighted_covered),
                "share_low": share_low,
                "share_high": share_high,
                "unweightable_covered": len([t for t in in_axis if not t.weighted and t.id in covered_ids]),
                "unweightable_uncovered": len([t for t in in_axis if not t.weighted and t.id not in covered_ids]),
            }
        axis_reports.append(entry)

    outline_tags = {t.tag_lower for t in outline.topics}
    unmatched = []
    for tag in sorted(counts.cards_by_tag):
        if tag in outline_tags:
            continue
        ancestor = None
        for candidate in outline_tags:
            if tag.startswith(candidate + "::") and (ancestor is None or len(candidate) > len(ancestor)):
                ancestor = candidate
        unmatched.append({"tag": tag, "cards": counts.cards_by_tag[tag], "nearest_outline_ancestor": ancestor})

    unweightable = [t for t in outline.topics if not t.weighted]

    return {
        "covered_by": covered_by,
        "outline": {
            "path": str(outline.path),
            "sha256": outline.sha256,
            "schema_version": outline.schema_version,
            "generated_utc_date": outline.generated,
            "topics": len(outline.topics),
            "weighted_topics": len(outline.topics) - len(unweightable),
            "unweightable_topics": len(unweightable),
        },
        "collection": {
            "path": str(counts.path),
            "sha256": counts.sha256,
            "open_mode": counts.open_mode,
            "total_cards": counts.total_cards,
            "total_notes": counts.total_notes,
            "cards_with_any_topic_tag": sum(counts.cards_by_tag.values()),
            "distinct_topic_tags_present": len(counts.cards_by_tag),
        },
        "topic_counts": {
            mode: {
                "covered": len(splits[mode][0]),
                "uncovered": len(splits[mode][1]),
                "fraction": len(splits[mode][0]) / len(outline.topics),
            }
            for mode in splits
        },
        "axes": axis_reports,
        "unweightable": {
            "total": len(unweightable),
            "covered": {mode: len([t for t in unweightable if t.id in {c.id for c in splits[mode][0]}]) for mode in splits},
            "note": (
                "weight_source == UNKNOWN. USMLE publishes no figure at this level. "
                "Excluded from every weighted figure; NOT treated as zero."
            ),
        },
        "unmatched_tags": unmatched,
        "cards_exact": exact,
        "cards_subtree": subtree,
        "covered_ids": [t.id for t in splits[covered_by][0]],
        "uncovered_ids": [t.id for t in splits[covered_by][1]],
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

RULE = "=" * 78
THIN = "-" * 78


def _pct(fraction: Optional[float]) -> str:
    return "UNDEFINED" if fraction is None else "{:.2f}%".format(fraction * 100)


def _weight_label(topic: Topic) -> str:
    if not topic.weighted:
        return "UNKNOWN wt"
    return "{}-{}%".format(topic.weight_low, topic.weight_high)


def _topic_line(topic: Topic, report: dict) -> str:
    return "    {:>5} exact /{:>5} subtree  {:>10}  {}\n      {}  [{}]".format(
        report["cards_exact"][topic.id],
        report["cards_subtree"][topic.id],
        _weight_label(topic),
        topic.tag,
        topic.name,
        topic.axis,
    )


def render_report(report: dict, topics: Sequence[Topic], max_list: int) -> str:
    by_id = {t.id: t for t in topics}
    out: List[str] = []
    add = out.append

    add(RULE)
    add("SPEEDRUN COVERAGE MAP  --  percent of the published outline covered by cards")
    add(RULE)
    outline = report["outline"]
    add("outline    : {}".format(outline["path"]))
    add("  sha256          : {}".format(outline["sha256"]))
    add("  schema_version  : {}".format(outline["schema_version"]))
    add("  generated (UTC) : {}".format(outline["generated_utc_date"]))
    add("  topics          : {} ({} with a published weight, {} UNKNOWN)".format(
        outline["topics"], outline["weighted_topics"], outline["unweightable_topics"]))
    collection = report["collection"]
    add("collection : {}".format(collection["path"]))
    add("  sha256          : {}".format(collection["sha256"]))
    add("  access          : {}".format(collection["open_mode"]))
    add("  cards / notes   : {} / {}".format(collection["total_cards"], collection["total_notes"]))
    add("  cards carrying a {} tag : {} across {} distinct tags".format(
        TAG_PREFIX, collection["cards_with_any_topic_tag"], collection["distinct_topic_tags_present"]))
    add("")

    add(THIN)
    add("WHAT 'COVERED' MEANS HERE")
    add(THIN)
    add("  exact   : >=1 card carries the topic's own tag, {}<path>.".format(TAG_PREFIX))
    add("  subtree : >=1 card carries that tag OR any descendant tag ('<tag>::...').")
    add("  Both are shown everywhere. They are never blended, and the covered /")
    add("  uncovered lists at the bottom use --covered-by={}.".format(report["covered_by"]))
    add("  Which one is right depends on where the deck is tagged: every published")
    add("  weight in this outline sits at an axis root, so a deck tagged only at leaf")
    add("  level scores 0% exact and a real number subtree.")
    add("")

    add(THIN)
    add("TOPIC-COUNT COVERAGE  (context only -- NOT the headline metric)")
    add(THIN)
    for mode in ("exact", "subtree"):
        block = report["topic_counts"][mode]
        add("  {:<8}: {} / {} topics = {}".format(
            mode, block["covered"], block["covered"] + block["uncovered"], _pct(block["fraction"])))
    add("  Raw topic count treats a 1-3% topic and a 12-16% topic as equal. The")
    add("  weighted figures below are the ones BUILD-DOC section 4 asks for.")
    add("")

    add(THIN)
    add("WEIGHTED COVERAGE  (headline; per axis; NEVER summed across axes)")
    add(THIN)
    add("  Method: covered share = Sum(covered weight) / Sum(all published weight).")
    add("  Each weight is a published RANGE, so the share is a range: the low end")
    add("  puts every covered topic at its published minimum and every uncovered")
    add("  topic at its published maximum; the high end reverses that. Those are the")
    add("  exact extremes of the ratio, not a spread around a midpoint.")
    add("  Topics with weight_source == UNKNOWN are excluded from both ends.")
    add("")
    for axis in report["axes"]:
        add("  axis '{}'  --  {} topics, {} with a published weight".format(
            axis["axis"], axis["topics"], axis["weighted_topics"]))
        if axis["weighted_topics"] == 0:
            add("    published weight total : none")
            add("    WEIGHTED COVERAGE      : UNDEFINED -- no topic on this axis publishes a")
            add("                             weight, so there is no denominator. Not 0%.")
            add("")
            continue
        add("    published weight total : {}-{}%".format(axis["published_total_low"], axis["published_total_high"]))
        if axis["partition_consistent"]:
            add("                             (range brackets 100% -- consistent with a partition)")
        else:
            add("                             NOT a partition: the range does not bracket 100%,")
            add("                             so read this as share-of-published-weight, NOT as")
            add("                             share-of-exam. (USMLE's discipline table is")
            add("                             explicitly non-exclusive and sums past 100%.)")
        for mode in ("exact", "subtree"):
            block = axis["modes"][mode]
            add("    [{}] {} of {} weighted topics covered".format(
                mode, block["weighted_covered"], axis["weighted_topics"]))
            add("      covered published weight : {}-{}%".format(
                block["covered_weight_low"], block["covered_weight_high"]))
            add("      COVERED SHARE            : {} - {}".format(_pct(block["share_low"]), _pct(block["share_high"])))
        add("")

    add(THIN)
    add("UNWEIGHTABLE TOPICS  (weight_source == UNKNOWN -- reported, never zeroed)")
    add(THIN)
    add("  {} of {} topics publish no weight. USMLE publishes percentages only at the".format(
        report["unweightable"]["total"], outline["topics"]))
    add("  levels named in outline.json's own weight_source values; nothing deeper has")
    add("  a figure. These topics are EXCLUDED from every weighted figure above. They")
    add("  are NOT counted as 0% covered and NOT counted as 100% covered.")
    for mode in ("exact", "subtree"):
        covered = report["unweightable"]["covered"][mode]
        add("  [{}] {} covered, {} uncovered".format(mode, covered, report["unweightable"]["total"] - covered))
    for axis in report["axes"]:
        add("    axis '{}': {} unweightable of {}".format(axis["axis"], axis["unweightable_topics"], axis["topics"]))
    add("")

    for heading, ids in (
        ("COVERED TOPICS (>=1 card, --covered-by={})".format(report["covered_by"]), report["covered_ids"]),
        ("UNCOVERED TOPICS (0 cards, --covered-by={})".format(report["covered_by"]), report["uncovered_ids"]),
    ):
        add(THIN)
        add("{}  --  {} topic(s)".format(heading, len(ids)))
        add(THIN)
        if not ids:
            add("  (none)")
        shown = ids if max_list <= 0 else ids[:max_list]
        for topic_id in shown:
            add(_topic_line(by_id[topic_id], report))
        if len(shown) < len(ids):
            add("  ... {} more suppressed by --max-list={} (the full split is in --json)".format(len(ids) - len(shown), max_list))
        add("")

    add(THIN)
    add("TAGS IN THE COLLECTION THAT ARE NOT OUTLINE TOPICS")
    add(THIN)
    if not report["unmatched_tags"]:
        add("  (none -- every {} tag in the collection is an outline topic)".format(TAG_PREFIX))
    else:
        for item in report["unmatched_tags"]:
            ancestor = item["nearest_outline_ancestor"]
            add("  {:>5} cards  {}".format(item["cards"], item["tag"]))
            if ancestor:
                add("               -> descendant of {} (counted in subtree mode only)".format(ancestor))
            else:
                add("               -> NO outline ancestor; counted nowhere. Likely a typo or a")
                add("                  stale tag. It contributes to no coverage figure.")
    add("")

    add(THIN)
    add("ASSERTION")
    add(THIN)
    add("  Every one of the {} outline topics is in exactly one of the two lists above,".format(outline["topics"]))
    add("  under BOTH the exact and subtree definitions. Checked, not assumed; this")
    add("  script exits {} if the split ever fails to account for a topic.".format(EXIT_ASSERT))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def _fixture_outline() -> dict:
    """A seven-topic outline with hand-checkable weights.

    axis 'sys'  : alpha 20-30 (weighted), alpha.leaf UNKNOWN, beta 10-20
                  (weighted), gamma UNKNOWN, delta UNKNOWN
    axis 'disc' : path 5-5 (weighted), pharm 5-5 (weighted)
    """

    def topic(topic_id, name, axis, level, path, low, high, source):
        return {
            "id": topic_id,
            "name": name,
            "axis": axis,
            "level": level,
            "path": path,
            "tag": TAG_PREFIX + "::".join(path),
            "weight_low": low,
            "weight_high": high,
            "weight_source": source,
        }

    fixture_src = "fixture#synthetic_table"
    return {
        "schema_version": "1.0.0",
        "generated_utc_date": "self-test",
        "topics": [
            topic("sys.alpha", "Alpha", "sys", 1, ["sys", "alpha"], 20, 30, fixture_src),
            topic("sys.alpha.leaf", "Alpha leaf", "sys", 2, ["sys", "alpha", "leaf"], None, None, UNKNOWN),
            topic("sys.beta", "Beta", "sys", 1, ["sys", "beta"], 10, 20, fixture_src),
            topic("sys.gamma", "Gamma", "sys", 1, ["sys", "gamma"], None, None, UNKNOWN),
            topic("sys.delta", "Delta", "sys", 1, ["sys", "delta"], None, None, UNKNOWN),
            topic("disc.path", "Pathology", "disc", 1, ["disc", "path"], 5, 5, fixture_src),
            topic("disc.pharm", "Pharmacology", "disc", 1, ["disc", "pharm"], 5, 5, fixture_src),
        ],
    }


# (tags stored on the note, number of cards that note owns)
FIXTURE_NOTES: Tuple[Tuple[str, int], ...] = (
    (" speedrun::topic::sys::alpha::leaf ", 2),
    (" SPEEDRUN::TOPIC::SYS::ALPHA::LEAF ", 1),  # Anki tags are case-insensitive
    (" speedrun::topic::sys::gamma ", 1),
    (" speedrun::topic::disc::path ", 3),
    (" speedrun::topic::sys::not_in_outline ", 1),  # orphan tag
    (" leech marked ", 4),  # untagged noise, must not be counted
)


def _build_fixture_collection(db_path: Path) -> None:
    """Write a minimal but schema-faithful .anki2 fixture."""
    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(
            """
            create table col (id integer primary key, crt integer not null, mod integer not null,
                scm integer not null, ver integer not null, dty integer not null, usn integer not null,
                ls integer not null, conf text not null, models text not null, decks text not null,
                dconf text not null, tags text not null);
            create table notes (id integer primary key, guid text not null, mid integer not null,
                mod integer not null, usn integer not null, tags text not null, flds text not null,
                sfld integer not null, csum integer not null, flags integer not null, data text not null);
            create table cards (id integer primary key, nid integer not null, did integer not null,
                ord integer not null, mod integer not null, usn integer not null, type integer not null,
                queue integer not null, due integer not null, ivl integer not null, factor integer not null,
                reps integer not null, lapses integer not null, left integer not null, odue integer not null,
                odid integer not null, flags integer not null, data text not null);
            create index ix_cards_nid on cards (nid);
            """
        )
        con.execute(
            "insert into col values (1, 0, 0, 0, 18, 0, 0, 0, '{}', '{}', '{}', '{}', '')",
        )
        card_id = 1000
        for note_id, (tags, card_count) in enumerate(FIXTURE_NOTES, start=1):
            con.execute(
                "insert into notes values (?, ?, 1, 0, 0, ?, 'front\x1fback', 'front', 0, 0, '')",
                (note_id, "guid{}".format(note_id), tags),
            )
            for ordinal in range(card_count):
                card_id += 1
                con.execute(
                    "insert into cards values (?, ?, 1, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '')",
                    (card_id, note_id, ordinal),
                )
        con.commit()
    finally:
        con.close()


class _Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: List[str] = []

    def check(self, label: str, actual: object, expected: object) -> None:
        if actual == expected:
            self.passed += 1
            print("  PASS  {}  = {!r}".format(label, actual))
        else:
            self.failures.append(label)
            print("  FAIL  {}\n          expected {!r}\n          actual   {!r}".format(label, expected, actual))

    def check_true(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print("  PASS  {}".format(label))
        else:
            self.failures.append(label)
            print("  FAIL  {}{}".format(label, "\n          " + detail if detail else ""))


def _run_main_capturing(argv: List[str]) -> Tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _selftest_counting(checker: _Checker, db_path: Path, outline_path: Path) -> Optional[dict]:
    print(THIN)
    print("A. CARD COUNTING")
    print(THIN)
    code, stdout, stderr = _run_main_capturing(["--collection", str(db_path), "--outline", str(outline_path), "--json"])
    checker.check("exit code of a normal run", code, EXIT_OK)
    checker.check_true("stderr is empty on a normal run", stderr == "", stderr)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as exc:
        checker.check_true("--json emits valid JSON", False, str(exc))
        return None

    checker.check("cards counted in the collection", report["collection"]["total_cards"], 12)
    checker.check("notes counted in the collection", report["collection"]["total_notes"], 6)
    checker.check("cards on sys::alpha (exact, nothing tagged there)", report["cards_exact"]["sys.alpha"], 0)
    checker.check("cards on sys::alpha (subtree, via ::leaf)", report["cards_subtree"]["sys.alpha"], 3)
    checker.check("cards on sys::alpha::leaf (2 + 1 UPPERCASE)", report["cards_exact"]["sys.alpha.leaf"], 3)
    checker.check("cards on sys::beta (nothing tagged)", report["cards_exact"]["sys.beta"], 0)
    checker.check("cards on disc::path (one note, 3 cards)", report["cards_exact"]["disc.path"], 3)
    checker.check("untagged cards excluded", report["collection"]["cards_with_any_topic_tag"], 8)
    return report


def _selftest_split(checker: _Checker, report: dict) -> None:
    print("")
    print(THIN)
    print("B. COVERED / UNCOVERED SPLIT IS EXHAUSTIVE")
    print(THIN)
    checker.check("covered topics (exact)", report["topic_counts"]["exact"]["covered"], 3)
    checker.check("uncovered topics (exact)", report["topic_counts"]["exact"]["uncovered"], 4)
    checker.check("covered topics (subtree)", report["topic_counts"]["subtree"]["covered"], 4)
    checker.check("uncovered topics (subtree)", report["topic_counts"]["subtree"]["uncovered"], 3)
    checker.check(
        "covered + uncovered == all topics",
        len(report["covered_ids"]) + len(report["uncovered_ids"]),
        report["outline"]["topics"],
    )
    checker.check_true(
        "covered and uncovered lists are disjoint",
        not (set(report["covered_ids"]) & set(report["uncovered_ids"])),
    )


def _selftest_weights(checker: _Checker, report: dict) -> None:
    print("")
    print(THIN)
    print("C. WEIGHTED COVERAGE IS A RANGE, COMPUTED BY HAND")
    print(THIN)
    print("  axis 'sys', subtree: covered={alpha 20-30}, uncovered={beta 10-20}")
    print("    low  = 20 / (20 + 20) = 0.50   high = 30 / (30 + 10) = 0.75")
    print("  axis 'sys', exact  : nothing weighted is covered -> 0.00% - 0.00%")
    print("  axis 'disc'        : 5 / (5 + 5) = 0.50 at both ends")
    sys_axis = next(a for a in report["axes"] if a["axis"] == "sys")
    disc_axis = next(a for a in report["axes"] if a["axis"] == "disc")
    checker.check("sys weighted topics", sys_axis["weighted_topics"], 2)
    checker.check("sys published total low", sys_axis["published_total_low"], 30)
    checker.check("sys published total high", sys_axis["published_total_high"], 50)
    checker.check("sys subtree share low", sys_axis["modes"]["subtree"]["share_low"], 0.5)
    checker.check("sys subtree share high", sys_axis["modes"]["subtree"]["share_high"], 0.75)
    checker.check("sys exact share low", sys_axis["modes"]["exact"]["share_low"], 0.0)
    checker.check("sys exact share high", sys_axis["modes"]["exact"]["share_high"], 0.0)
    checker.check("disc subtree share low", disc_axis["modes"]["subtree"]["share_low"], 0.5)
    checker.check("disc subtree share high", disc_axis["modes"]["subtree"]["share_high"], 0.5)
    checker.check_true(
        "no blended cross-axis figure exists in the report",
        all(key not in report for key in ("share_low", "share_high", "overall_share")),
    )
    _selftest_bound_direction(checker)


def _selftest_bound_direction(checker: _Checker) -> None:
    """Pin WHICH corner of the weight box each endpoint comes from.

    The fixture above cannot do this on its own: it has covered 20-30 against
    uncovered 10-20, so covered_low + uncovered_high == covered_high +
    uncovered_low == 40 and the two denominators coincide. Swapping them is
    therefore invisible there. This check uses a deliberately asymmetric case
    where the two denominators differ, so an implementation that reverses the
    endpoints -- or that collapses them to a single midpoint -- fails.
    """
    print("")
    print("  bound direction, asymmetric case: covered 20-30 vs uncovered 10-40")
    print("    low  = 20 / (20 + 40) = 1/3   <- covered at MIN, uncovered at MAX")
    print("    high = 30 / (30 + 10) = 0.75  <- covered at MAX, uncovered at MIN")
    print("    (a reversed implementation would give 20/40 = 0.5 and 30/60 = 0.5)")

    def synthetic(topic_id: str, low: int, high: int) -> Topic:
        return Topic(
            id=topic_id,
            name=topic_id,
            axis="sys",
            level=1,
            path=("sys", topic_id),
            tag=TAG_PREFIX + "sys::" + topic_id,
            weight_low=low,
            weight_high=high,
            weight_source="fixture#synthetic_table",
        )

    covered = [synthetic("wide_covered", 20, 30)]
    uncovered = [synthetic("wide_uncovered", 10, 40)]
    share_low, share_high = _covered_share(covered, uncovered)
    checker.check("asymmetric share low is covered_low/(covered_low+uncovered_high)", share_low, 20 / 60)
    checker.check("asymmetric share high is covered_high/(covered_high+uncovered_low)", share_high, 30 / 40)
    checker.check_true(
        "the two endpoints are distinct -- a range, not a point estimate",
        share_low is not None and share_high is not None and share_low < share_high,
        "got {!r} and {!r}".format(share_low, share_high),
    )
    checker.check_true(
        "the endpoints are not a midpoint pair",
        share_low != share_high,
    )
    # The denominators must differ here, or this check would be as blind as the
    # main fixture. Asserted so a later edit cannot quietly re-degenerate it.
    checker.check_true(
        "this case is non-degenerate (the two denominators differ)",
        (20 + 40) != (30 + 10),
    )
    # Everything covered -> exactly 1.0 at both ends; nothing covered -> 0.0 at
    # both ends but only when a denominator exists at all.
    checker.check("all covered is 1.0 at both ends", _covered_share(covered, []), (1.0, 1.0))
    checker.check("none covered is 0.0 at both ends", _covered_share([], uncovered), (0.0, 0.0))


def _selftest_unknowns(checker: _Checker, report: dict) -> None:
    print("")
    print(THIN)
    print("D. UNKNOWN WEIGHTS ARE EXCLUDED, NOT ZEROED")
    print(THIN)
    sys_axis = next(a for a in report["axes"] if a["axis"] == "sys")
    checker.check("unweightable topics", report["unweightable"]["total"], 3)
    checker.check("unweightable covered (subtree)", report["unweightable"]["covered"]["subtree"], 2)
    checker.check(
        "unweightable topics absent from the weighted denominator",
        sys_axis["weighted_topics"] + sys_axis["unweightable_topics"],
        sys_axis["topics"],
    )
    checker.check_true(
        "sys.gamma is covered yet contributes no weight",
        report["cards_exact"]["sys.gamma"] == 1 and sys_axis["published_total_high"] == 50,
    )
    checker.check("an all-UNKNOWN axis yields UNDEFINED, not 0.0", _covered_share([], []), (None, None))


def _selftest_orphans(checker: _Checker, report: dict) -> None:
    print("")
    print(THIN)
    print("E. ORPHAN TAGS ARE SURFACED")
    print(THIN)
    orphans = {item["tag"]: item for item in report["unmatched_tags"]}
    checker.check("orphan tags found", sorted(orphans), [TAG_PREFIX + "sys::not_in_outline"])
    checker.check(
        "orphan has no outline ancestor",
        orphans[TAG_PREFIX + "sys::not_in_outline"]["nearest_outline_ancestor"],
        None,
    )


def _selftest_readonly(checker: _Checker, root: Path, db_path: Path, sha_before: str, size_before: int) -> None:
    print("")
    print(THIN)
    print("F. THE COLLECTION WAS NOT MODIFIED")
    print(THIN)
    checker.check("collection sha256 unchanged after a full run", _sha256_file(db_path), sha_before)
    checker.check("collection size unchanged after a full run", db_path.stat().st_size, size_before)
    checker.check_true("no -wal sidecar was created", not (root / "collection.anki2-wal").exists())
    checker.check_true("no -shm sidecar was created", not (root / "collection.anki2-shm").exists())

    print("")
    print(THIN)
    print("G. THE SNAPSHOT FALLBACK PATH AGREES WITH THE IN-PLACE PATH")
    print(THIN)
    direct = analyse_collection(db_path)
    snapshot = analyse_collection(db_path, force_snapshot=True)
    checker.check("snapshot path yields identical tag counts", snapshot.cards_by_tag, direct.cards_by_tag)
    checker.check_true("snapshot path is reported as such", "snapshot" in snapshot.open_mode, snapshot.open_mode)
    checker.check("collection sha256 unchanged after the snapshot run", _sha256_file(db_path), sha_before)


def _selftest_text_report(checker: _Checker, db_path: Path, outline_path: Path) -> None:
    print("")
    print(THIN)
    print("H. THE HUMAN-READABLE REPORT PRINTS BOTH LISTS")
    print(THIN)
    code, text, _err = _run_main_capturing(["--collection", str(db_path), "--outline", str(outline_path)])
    checker.check("exit code of the text run", code, EXIT_OK)
    checker.check_true("COVERED list printed", "COVERED TOPICS" in text)
    checker.check_true("UNCOVERED list printed", "UNCOVERED TOPICS" in text)
    checker.check_true("uncovered topic named in the text", TAG_PREFIX + "sys::beta" in text)
    checker.check_true("UNKNOWN weights called out", "UNKNOWN wt" in text)
    checker.check_true("weighted range printed as a range", "0.00% - 0.00%" in text and "50.00% - 75.00%" in text)


def _selftest_expect_failure(
    checker: _Checker, label: str, argv: List[str], expected_code: int, expected_text: str
) -> None:
    code, _stdout, stderr = _run_main_capturing(argv)
    checker.check("{}: exit code".format(label), code, expected_code)
    checker.check_true(
        "{}: message mentions {!r}".format(label, expected_text),
        expected_text in stderr,
        "stderr was: {!r}".format(stderr),
    )


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _selftest_outline_failures(checker: _Checker, root: Path, db_path: Path) -> None:
    print("")
    print(THIN)
    print("I. A MISSING OR MALFORMED OUTLINE EXITS NON-ZERO WITH A CLEAR MESSAGE")
    print(THIN)

    def bad(label: str, outline: Path, expected_text: str) -> None:
        _selftest_expect_failure(
            checker,
            label,
            ["--collection", str(db_path), "--outline", str(outline)],
            EXIT_OUTLINE,
            expected_text,
        )

    bad("missing outline", root / "does-not-exist.json", "not found")

    broken = root / "broken.json"
    broken.write_text("{not json at all", encoding="utf-8")
    bad("malformed JSON", broken, "not valid JSON")

    bad("no topics key", _write_json(root / "no-topics.json", {"schema_version": "1.0.0"}), "no 'topics' key")
    bad("empty topics", _write_json(root / "empty-topics.json", {"topics": []}), "empty")
    bad(
        "topic missing keys",
        _write_json(root / "missing-key.json", {"topics": [{"id": "a", "name": "A", "path": ["a"], "weight_low": 1}]}),
        "missing required key",
    )
    bad(
        "UNKNOWN source carrying a number",
        _write_json(
            root / "invented-weight.json",
            {"topics": [{"id": "a", "name": "A", "path": ["a"], "weight_low": 10, "weight_high": 20, "weight_source": UNKNOWN}]},
        ),
        "must not carry a value",
    )
    bad(
        "inverted range",
        _write_json(
            root / "inverted-weight.json",
            {"topics": [{"id": "a", "name": "A", "path": ["a"], "weight_low": 30, "weight_high": 10, "weight_source": "x"}]},
        ),
        "exceeds",
    )
    unknown_topic = {"weight_low": None, "weight_high": None, "weight_source": UNKNOWN}
    first = dict(unknown_topic, id="a", name="A", path=["a"])
    second = dict(unknown_topic, id="a", name="A2", path=["b"])
    bad("duplicate id", _write_json(root / "dupes.json", {"topics": [first, second]}), "duplicate id")
    bad(
        "tag/path disagreement",
        _write_json(
            root / "tag-mismatch.json",
            {"topics": [dict(unknown_topic, id="a", name="A", path=["a"], tag="speedrun::topic::somethingelse")]},
        ),
        "does not match",
    )


def _selftest_collection_failures(checker: _Checker, root: Path, outline_path: Path) -> None:
    print("")
    print(THIN)
    print("J. A MISSING OR UNREADABLE COLLECTION EXITS NON-ZERO WITH A CLEAR MESSAGE")
    print(THIN)
    _selftest_expect_failure(
        checker,
        "missing collection",
        ["--collection", str(root / "nope.anki2"), "--outline", str(outline_path)],
        EXIT_COLLECTION,
        "collection not found",
    )

    not_a_collection = root / "other.anki2"
    other = sqlite3.connect(str(not_a_collection))
    other.execute("create table unrelated (x integer)")
    other.commit()
    other.close()
    _selftest_expect_failure(
        checker,
        "sqlite file that is not a collection",
        ["--collection", str(not_a_collection), "--outline", str(outline_path)],
        EXIT_COLLECTION,
        "not an Anki collection",
    )

    garbage = root / "garbage.anki2"
    garbage.write_bytes(b"this is not a database" * 100)
    _selftest_expect_failure(
        checker,
        "non-sqlite file",
        ["--collection", str(garbage), "--outline", str(outline_path)],
        EXIT_COLLECTION,
        "could not open",
    )


def _selftest_cli(checker: _Checker, db_path: Path, outline_path: Path) -> None:
    print("")
    print(THIN)
    print("K. COMMAND-LINE CONTRACT")
    print(THIN)
    code, _stdout, _stderr = _run_main_capturing(["--outline", str(outline_path)])
    checker.check("no --collection and no --self-test is a usage error", code, EXIT_USAGE)

    base = ["--collection", str(db_path), "--outline", str(outline_path), "--covered-by", "subtree"]
    code, _stdout, _stderr = _run_main_capturing(base + ["--fail-under", "60"])
    checker.check("--fail-under 60 against a 50.00% low end exits non-zero", code, EXIT_THRESHOLD)
    code, _stdout, _stderr = _run_main_capturing(base + ["--fail-under", "50"])
    checker.check("--fail-under 50 against a 50.00% low end passes", code, EXIT_OK)


def self_test() -> int:
    """Build a synthetic fixture from scratch and verify the whole pipeline.

    Every expected number below is derived by hand from the fixture and is
    stated in the printed output, so the arithmetic can be checked without
    reading the code.
    """
    checker = _Checker()
    print(RULE)
    print("SELF-TEST  --  synthetic fixture, built by this script, checked against")
    print("hand-computed expectations. No real deck and no network involved.")
    print(RULE)
    print("")
    print("FIXTURE")
    print("  outline: 7 topics on 2 axes.")
    print("    axis 'sys' : alpha 20-30% | alpha.leaf UNKNOWN | beta 10-20%")
    print("                 gamma UNKNOWN | delta UNKNOWN")
    print("    axis 'disc': path 5-5% | pharm 5-5%")
    print("  cards  : 3 on sys::alpha::leaf (one note tagged in UPPERCASE),")
    print("           1 on sys::gamma, 3 on disc::path, 1 on an orphan tag,")
    print("           4 untagged. 12 cards / 6 notes total.")
    print("  NOTHING is tagged sys::alpha directly, so exact and subtree must")
    print("  disagree -- which is the real-world case, since every published")
    print("  weight sits at an axis root.")
    print("")

    with tempfile.TemporaryDirectory(prefix="speedrun-selftest-") as tmp:
        root = Path(tmp)
        outline_path = root / "outline.json"
        outline_path.write_text(json.dumps(_fixture_outline(), indent=2), encoding="utf-8")
        db_path = root / "collection.anki2"
        _build_fixture_collection(db_path)
        sha_before = _sha256_file(db_path)
        size_before = db_path.stat().st_size

        report = _selftest_counting(checker, db_path, outline_path)
        if report is None:
            print("")
            print(RULE)
            print("SELF-TEST FAILED: --json did not emit valid JSON; nothing else could be checked.")
            print(RULE)
            return EXIT_SELFTEST
        _selftest_split(checker, report)
        _selftest_weights(checker, report)
        _selftest_unknowns(checker, report)
        _selftest_orphans(checker, report)
        _selftest_readonly(checker, root, db_path, sha_before, size_before)
        _selftest_text_report(checker, db_path, outline_path)
        _selftest_outline_failures(checker, root, db_path)
        _selftest_collection_failures(checker, root, outline_path)
        _selftest_cli(checker, db_path, outline_path)

    print("")
    print(RULE)
    if checker.failures:
        print("SELF-TEST FAILED: {} of {} checks failed".format(len(checker.failures), checker.passed + len(checker.failures)))
        for label in checker.failures:
            print("  - {}".format(label))
        print(RULE)
        return EXIT_SELFTEST
    print("SELF-TEST PASSED: {} checks, 0 failures".format(checker.passed))
    print("The script is exercised end to end -- counting, the weighted range")
    print("arithmetic, UNKNOWN exclusion, read-only access, and every failure exit.")
    print(RULE)
    return EXIT_OK


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> "None":  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write("{}: error: {}\n".format(self.prog, message))
        raise SystemExit(EXIT_USAGE)


def _build_parser() -> _Parser:
    parser = _Parser(
        prog="coverage.py",
        description="Coverage map: percent of the published USMLE outline covered by cards, weighted by the published weight ranges.",
    )
    parser.add_argument("--collection", type=Path, help="path to an Anki collection.anki2 (opened READ-ONLY)")
    parser.add_argument(
        "--outline",
        type=Path,
        default=Path(__file__).resolve().parent / "outline.json",
        help="path to outline.json (default: alongside this script)",
    )
    parser.add_argument(
        "--covered-by",
        choices=("exact", "subtree"),
        default="exact",
        help="which definition drives the printed covered/uncovered lists (default: exact). "
        "Both definitions are reported regardless.",
    )
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON instead of text")
    parser.add_argument("--max-list", type=int, default=0, help="truncate each printed list to N topics (0 = print all)")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="exit {} if the LOW end of any axis's weighted covered share is below this percent".format(EXIT_THRESHOLD),
    )
    parser.add_argument(
        "--force-snapshot",
        action="store_true",
        help="always read a temporary copy of the collection instead of opening it in place",
    )
    parser.add_argument("--self-test", action="store_true", help="build a synthetic fixture and verify this script against it")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else EXIT_USAGE

    if args.self_test:
        return self_test()

    if args.collection is None:
        parser.print_usage(sys.stderr)
        sys.stderr.write("coverage.py: error: --collection is required (or use --self-test)\n")
        return EXIT_USAGE

    try:
        outline = load_outline(args.outline)
    except OutlineError as exc:
        sys.stderr.write("outline error: {}\n".format(exc))
        return EXIT_OUTLINE

    try:
        counts = analyse_collection(args.collection, force_snapshot=args.force_snapshot)
    except CollectionError as exc:
        sys.stderr.write("collection error: {}\n".format(exc))
        return EXIT_COLLECTION

    try:
        report = build_report(outline, counts, args.covered_by)
    except ExhaustivenessError as exc:
        sys.stderr.write("coverage assertion failed: {}\n".format(exc))
        return EXIT_ASSERT

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_report(report, outline.topics, args.max_list))

    if args.fail_under is not None:
        threshold = args.fail_under / 100.0
        below: List[str] = []
        for axis in report["axes"]:
            share_low = axis["modes"][args.covered_by]["share_low"]
            if share_low is None:
                below.append("{} (UNDEFINED -- no published weight on this axis)".format(axis["axis"]))
            elif share_low < threshold:
                below.append("{} ({})".format(axis["axis"], _pct(share_low)))
        if below:
            sys.stderr.write(
                "coverage below --fail-under {:.2f}% on axis/axes: {}\n".format(args.fail_under, ", ".join(below))
            )
            return EXIT_THRESHOLD

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
