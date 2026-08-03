# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Read-only inventory of an Anki .apkg deck.

    python3 speedrun-analysis/deck/import_deck.py <deck.apkg> [--json] [--samples N]

An .apkg is a zip holding a SQLite collection plus a media map. Three layouts
exist in the wild:

  * legacy  -- ``collection.anki2``  (schema <= 11, plain SQLite)
  * v2      -- ``collection.anki21`` (plain SQLite, deflate-compressed *by the
               zip*, which the stdlib ``zipfile`` module handles)
  * v3      -- ``collection.anki21b`` (SQLite wrapped in a raw **zstd** stream)

Standard library only, so the v3 case is only decodable on Python 3.14+, where
``compression.zstd`` landed. On older interpreters this script does not guess:
it says so and points at the fork's own Rust-backed importer. See
``handle_zstd_collection`` below.

The source .apkg is never opened for writing. Its SHA-256 is taken before and
after the run and the two are compared; a mismatch is reported as a failure.
Everything is unpacked into a throwaway temp directory that is deleted on exit,
and every SQLite handle is opened with ``mode=ro``.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

# Zip member names that can hold the collection, best first.
COLLECTION_MEMBERS = ("collection.anki21b", "collection.anki21", "collection.anki2")

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
SQLITE_MAGIC = b"SQLite format 3\x00"

# Anki writes this placeholder note into the legacy collection.anki2 sidecar of
# a v2 package so that ancient clients show a useful message instead of junk.
LEGACY_STUB_MARKER = "Please update to the latest Anki version"


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc(seconds: float) -> str:
    stamp = datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def provenance_of(path: str) -> dict:
    stat = os.stat(path)
    return {
        "path": os.path.abspath(path),
        "filename": os.path.basename(path),
        "size_bytes": stat.st_size,
        "sha256": sha256_of(path),
        "mtime_utc": utc(stat.st_mtime),
    }


# --------------------------------------------------------------------------
# package layout
# --------------------------------------------------------------------------


def read_meta_version(archive: zipfile.ZipFile) -> int | None:
    """Return the package version from the ``meta`` protobuf, or None.

    ``meta`` is a two-byte protobuf: field 1 (``version``) as a varint. Parsing
    that by hand avoids pulling in a protobuf dependency for two bytes.
    """
    try:
        raw = archive.read("meta")
    except KeyError:
        return None
    if len(raw) < 2 or raw[0] != 0x08:
        return None
    value = 0
    shift = 0
    for byte in raw[1:]:
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
        shift += 7
    return None


def describe_members(archive: zipfile.ZipFile) -> list[dict]:
    return [
        {
            "name": info.filename,
            "stored_bytes": info.compress_size,
            "uncompressed_bytes": info.file_size,
        }
        for info in archive.infolist()
    ]


def media_entry_count(archive: zipfile.ZipFile) -> int | str:
    """Count media files. v2 stores a JSON map; v3 stores a protobuf."""
    try:
        raw = archive.read("media")
    except KeyError:
        return 0
    try:
        return len(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, ValueError):
        return "UNKNOWN (binary/protobuf media map, not parsed)"


def handle_zstd_collection(blob_path: str) -> str:
    """Decompress a v3 zstd collection, or explain why we cannot.

    Raises SystemExit with an explicit message rather than guessing. The
    fallback named there uses the fork's own Rust importer through pylib, which
    adds no Python dependency.
    """
    try:
        from compression import zstd  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        sys.exit(
            "This .apkg is an Anki v3 package: the collection is a raw zstd\n"
            "stream, and this interpreter (Python "
            f"{sys.version_info.major}.{sys.version_info.minor}) has no stdlib\n"
            "zstd decoder -- `compression.zstd` only exists on Python 3.14+.\n"
            "\n"
            "Not guessing. Use the fork's own Rust-backed importer instead, which\n"
            "adds no Python dependency:\n"
            "\n"
            "    just build     # produces out/pyenv with anki + the Rust backend\n"
            "    out/pyenv/bin/python -c \"import anki.collection as c; \\\n"
            "        col = c.Collection('/tmp/scratch.anki2'); \\\n"
            "        print(col.import_anki_package(<request>))\"\n"
            "\n"
            "That path writes a NEW scratch collection under /tmp and still\n"
            "leaves the source .apkg untouched."
        )
    out_path = blob_path + ".sqlite"
    with zstd.ZstdFile(blob_path, "rb") as src, open(out_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return out_path


def extract_collection(archive: zipfile.ZipFile, member: str, workdir: str) -> str:
    """Extract one collection member into workdir, decompressing if needed."""
    blob_path = os.path.join(workdir, member)
    with archive.open(member) as src, open(blob_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    with open(blob_path, "rb") as probe:
        magic = probe.read(16)
    if magic.startswith(ZSTD_MAGIC):
        return handle_zstd_collection(blob_path)
    if not magic.startswith(SQLITE_MAGIC):
        sys.exit(
            f"{member!r} is neither SQLite nor zstd (leading bytes {magic[:8]!r}). "
            "Refusing to guess at its format."
        )
    return blob_path


def open_readonly(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


# --------------------------------------------------------------------------
# collection reading
# --------------------------------------------------------------------------


def table_names(con: sqlite3.Connection) -> set[str]:
    rows = con.execute("select name from sqlite_master where type = 'table'")
    return {row[0] for row in rows}


def notetypes_schema11(con: sqlite3.Connection) -> dict[int, dict]:
    """Notetypes for schema <= 11, where they live in a JSON blob on `col`."""
    (blob,) = con.execute("select models from col").fetchone()
    out = {}
    for key, model in json.loads(blob).items():
        out[int(key)] = {
            "id": int(key),
            "name": model.get("name"),
            "kind": "cloze" if model.get("type") == 1 else "standard",
            "fields": [f["name"] for f in model.get("flds", [])],
            "templates": [t["name"] for t in model.get("tmpls", [])],
        }
    return out


def notetypes_schema18(con: sqlite3.Connection) -> dict[int, dict]:
    """Notetypes for schema >= 18, where they have their own tables."""
    out: dict[int, dict] = {}
    for ntid, name, config in con.execute("select id, name, config from notetypes"):
        # config is a protobuf; the cloze flag is not worth hand-decoding, so
        # it is reported as UNKNOWN rather than guessed at.
        del config
        out[ntid] = {
            "id": ntid,
            "name": name,
            "kind": "UNKNOWN (notetype config is protobuf; not decoded)",
            "fields": [],
            "templates": [],
        }
    for ntid, name in con.execute("select ntid, name from fields order by ntid, ord"):
        if ntid in out:
            out[ntid]["fields"].append(name)
    for ntid, name in con.execute(
        "select ntid, name from templates order by ntid, ord"
    ):
        if ntid in out:
            out[ntid]["templates"].append(name)
    return out


def deck_names(con: sqlite3.Connection, tables: set[str]) -> dict[int, str]:
    if "decks" in tables:
        return {did: name.replace("\x1f", "::") for did, name in con.execute("select id, name from decks")}
    (blob,) = con.execute("select decks from col").fetchone()
    return {int(k): v.get("name") for k, v in json.loads(blob).items()}


def tag_counts(con: sqlite3.Connection) -> tuple[collections.Counter, int]:
    """Tag vocabulary with per-tag NOTE counts, plus the untagged-note count.

    `notes.tags` is a space-delimited string with sentinel spaces at both ends.
    """
    counter: collections.Counter = collections.Counter()
    untagged = 0
    for (raw,) in con.execute("select tags from notes"):
        tags = (raw or "").split()
        if not tags:
            untagged += 1
            continue
        counter.update(set(tags))
    return counter, untagged


def truncate(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit] + f" ... [+{len(flat) - limit} chars]"


def sample_notes(
    con: sqlite3.Connection, notetypes: dict[int, dict], count: int, width: int
) -> list[dict]:
    rows = con.execute(
        "select id, mid, tags, flds from notes order by id limit ?", (count,)
    )
    samples = []
    for note_id, mid, tags, flds in rows:
        model = notetypes.get(mid, {})
        names = model.get("fields") or []
        values = flds.split("\x1f")
        fields = {
            (names[i] if i < len(names) else f"field[{i}]"): truncate(v, width)
            for i, v in enumerate(values)
        }
        samples.append(
            {
                "note_id": note_id,
                "created_utc": utc(note_id / 1000),
                "notetype": model.get("name", f"UNKNOWN mid={mid}"),
                "tags": tags.split(),
                "fields": fields,
            }
        )
    return samples


def card_state_counts(con: sqlite3.Connection) -> dict[str, int]:
    names = {0: "new", 1: "learning", 2: "review", 3: "relearning"}
    out: dict[str, int] = {}
    for ctype, n in con.execute("select type, count(*) from cards group by type"):
        out[names.get(ctype, f"type={ctype}")] = n
    return out


def inspect_collection(path: str, samples: int, width: int) -> dict:
    con = open_readonly(path)
    try:
        tables = table_names(con)
        (schema_ver,) = con.execute("select ver from col").fetchone()
        (crt, mod) = con.execute("select crt, mod from col").fetchone()
        notetypes = (
            notetypes_schema18(con)
            if "notetypes" in tables
            else notetypes_schema11(con)
        )
        used = dict(con.execute("select mid, count(*) from notes group by mid"))
        decks = deck_names(con, tables)
        per_deck = dict(con.execute("select did, count(*) from cards group by did"))
        tags, untagged = tag_counts(con)
        note_count = con.execute("select count(*) from notes").fetchone()[0]
        card_count = con.execute("select count(*) from cards").fetchone()[0]
        review_count = (
            con.execute("select count(*) from revlog").fetchone()[0]
            if "revlog" in tables
            else 0
        )
        first_last = con.execute("select min(id), max(id) from notes").fetchone()
        return {
            "schema_version": schema_ver,
            "collection_created_utc": utc(crt),
            "collection_modified_utc": utc(mod / 1000),
            "note_count": note_count,
            "card_count": card_count,
            "review_log_entries": review_count,
            "first_note_created_utc": utc(first_last[0] / 1000) if first_last[0] else None,
            "last_note_created_utc": utc(first_last[1] / 1000) if first_last[1] else None,
            "notetypes_used": [
                dict(notetypes.get(mid, {"id": mid, "name": f"UNKNOWN mid={mid}"}),
                     note_count=n)
                for mid, n in sorted(used.items(), key=lambda kv: -kv[1])
            ],
            "notetypes_defined_but_unused": sorted(
                nt["name"] for mid, nt in notetypes.items() if mid not in used
            ),
            "decks": [
                {"id": did, "name": decks.get(did, f"UNKNOWN did={did}"), "cards": n}
                for did, n in sorted(per_deck.items(), key=lambda kv: -kv[1])
            ],
            "decks_defined_but_empty": sorted(
                name for did, name in decks.items() if did not in per_deck
            ),
            "distinct_tags": len(tags),
            "tag_vocabulary": [
                {"tag": t, "notes": n} for t, n in sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "untagged_notes": untagged,
            "card_states": card_state_counts(con),
            "sample_notes": sample_notes(con, notetypes, samples, width),
            "looks_like_legacy_stub": bool(
                con.execute(
                    "select 1 from notes where flds like ? limit 1",
                    (f"%{LEGACY_STUB_MARKER}%",),
                ).fetchone()
            ),
        }
    finally:
        con.close()


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


def inspect_package(apkg: str, samples: int, width: int) -> dict:
    before = provenance_of(apkg)
    workdir = tempfile.mkdtemp(prefix="apkg-inventory-")
    try:
        with zipfile.ZipFile(apkg) as archive:
            names = set(archive.namelist())
            present = [m for m in COLLECTION_MEMBERS if m in names]
            if not present:
                sys.exit(
                    f"No collection found in {apkg!r}. Members: {sorted(names)[:20]}"
                )
            primary = present[0]
            report = {
                "provenance": before,
                "package_version": read_meta_version(archive),
                "zip_members": describe_members(archive),
                "media_entries": media_entry_count(archive),
                "collection_members_present": present,
                "collection_analysed": primary,
                "collections": {},
            }
            for member in present:
                blob = extract_collection(archive, member, workdir)
                report["collections"][member] = inspect_collection(
                    blob, samples if member == primary else 0, width
                )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    after = sha256_of(apkg)
    report["source_unchanged"] = after == before["sha256"]
    if not report["source_unchanged"]:
        report["source_unchanged_error"] = (
            f"SHA-256 changed during the run: {before['sha256']} -> {after}"
        )
    return report


def print_report(report: dict) -> None:
    prov = report["provenance"]
    line = "=" * 72
    print(line)
    print(f"DECK INVENTORY  {prov['filename']}")
    print(line)
    print(f"path             {prov['path']}")
    print(f"size             {prov['size_bytes']:,} bytes")
    print(f"sha256           {prov['sha256']}")
    print(f"file mtime       {prov['mtime_utc']}")
    print(f"package version  {report['package_version']} (from `meta`)")
    print(f"media entries    {report['media_entries']}")
    print("zip members:")
    for m in report["zip_members"]:
        print(
            f"  {m['name']:<24} {m['uncompressed_bytes']:>10,} bytes"
            f"  (stored {m['stored_bytes']:,})"
        )
    print(f"collections present: {', '.join(report['collection_members_present'])}")
    print(f"analysed:            {report['collection_analysed']}")

    for member, col in report["collections"].items():
        primary = member == report["collection_analysed"]
        print()
        print("-" * 72)
        label = "PRIMARY" if primary else "SECONDARY"
        print(f"{label}: {member}   schema ver {col['schema_version']}")
        if col["looks_like_legacy_stub"]:
            print("  NOTE: contains Anki's 'please upgrade' placeholder note --")
            print("        this is a compatibility stub, not real deck content.")
        print("-" * 72)
        print(f"  notes                {col['note_count']}")
        print(f"  cards                {col['card_count']}")
        print(f"  review log entries   {col['review_log_entries']}")
        print(f"  collection created   {col['collection_created_utc']}")
        print(f"  collection modified  {col['collection_modified_utc']}")
        print(f"  first note created   {col['first_note_created_utc']}")
        print(f"  last note created    {col['last_note_created_utc']}")
        print("  card states:", col["card_states"] or "(none)")
        print("  notetypes in use:")
        for nt in col["notetypes_used"]:
            print(f"    - {nt.get('name')}  ({nt.get('note_count')} notes)")
            print(f"        id        {nt.get('id')}")
            print(f"        kind      {nt.get('kind')}")
            print(f"        fields    {nt.get('fields')}")
            print(f"        templates {nt.get('templates')}")
        if col["notetypes_defined_but_unused"]:
            print(f"  notetypes defined but unused: {col['notetypes_defined_but_unused']}")
        print("  decks (by card count):")
        for d in col["decks"]:
            print(f"    - {d['name']!r}  {d['cards']} cards  (id {d['id']})")
        if col["decks_defined_but_empty"]:
            print(f"  decks defined but empty: {col['decks_defined_but_empty']}")

        print(f"  TAG VOCABULARY -- {col['distinct_tags']} distinct tag(s)")
        if not col["tag_vocabulary"]:
            print("    (none) -- this deck carries NO tags at all.")
        for entry in col["tag_vocabulary"]:
            print(f"    {entry['notes']:>6}  {entry['tag']}")
        print(f"  notes with zero tags: {col['untagged_notes']} of {col['note_count']}")

        if col["sample_notes"]:
            print("  SAMPLE NOTES (fields truncated):")
            for i, note in enumerate(col["sample_notes"], 1):
                print(f"    [{i}] note {note['note_id']}  created {note['created_utc']}")
                print(f"        notetype: {note['notetype']}   tags: {note['tags'] or '(none)'}")
                for name, value in note["fields"].items():
                    print(f"        {name}: {value}")

    print()
    print(f"source .apkg unchanged by this run: {report['source_unchanged']}")
    if not report["source_unchanged"]:
        print(report["source_unchanged_error"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only inventory of an Anki .apkg deck (stdlib only)."
    )
    parser.add_argument("apkg", help="path to the .apkg file")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--samples", type=int, default=5, help="sample notes to show")
    parser.add_argument("--width", type=int, default=220, help="field truncation width")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.apkg):
        sys.exit(f"not a file: {args.apkg}")

    report = inspect_package(args.apkg, args.samples, args.width)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)
    return 0 if report["source_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
