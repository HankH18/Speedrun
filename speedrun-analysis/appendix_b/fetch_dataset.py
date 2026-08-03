# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Appendix B -- fetch the real review dataset. Downloads nothing by default that
this repository is allowed to keep, and refuses to run at all without access.

    python3 speedrun-analysis/appendix_b/fetch_dataset.py --preflight
    python3 speedrun-analysis/appendix_b/fetch_dataset.py --list
    python3 speedrun-analysis/appendix_b/fetch_dataset.py --users 1-3
    python3 speedrun-analysis/appendix_b/fetch_dataset.py --users all --yes

WHAT THIS SCRIPT IS FOR
-----------------------
`thresholds.json` reports eight thresholds, all UNKNOWN, all `value: null`,
because no derivation in `derive_thresholds.py` has ever seen a real review. The
dataset named below is the one that would change that. It is **gated**: nobody --
not this script, not CI, not a reviewer cloning the repo -- can read a byte of it
without first logging in to HuggingFace and accepting the dataset's terms.

So this file is deliberately the *only* thing in `speedrun-analysis/` that talks
to the network, it is deliberately not run by `run.py`, and it deliberately
writes outside the tree git tracks. See `DATASET-PROVENANCE.md` next to it for
the licence position, which is **UNVERIFIED** -- the licence is custom and cannot
be read without the same access this script needs.

WHAT IT WILL NOT DO
-------------------
* It bundles no data. Nothing under `DEFAULT_DEST` is committed; the path is in
  `.gitignore` and the script refuses to write anywhere git tracks.
* It never prints, logs or stores the token. Every string it emits is passed
  through `_scrub()` first, which redacts any secret it was given.
* It never silently falls back to a different revision. `REVISION` is a commit
  sha, every request pins it, and every response is checked to have come from
  it -- a mismatch is a hard failure, not a warning.

STDLIB ONLY
-----------
`huggingface_hub` is used if it happens to be installed, and the plain HTTP
resolve endpoints are used if it is not. Neither is a dependency of this repo and
`--http` forces the stdlib path so the fallback is exercisable rather than
theoretical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Iterable
from typing import Sequence

# --------------------------------------------------------------------------
# The pin. Everything below is a consequence of these five constants.
# --------------------------------------------------------------------------

DATASET_ID = "open-spaced-repetition/anki-revlogs-10k"

# Commit sha, not a branch. A tag or `main` would let the dataset move under a
# derivation that has already been run and reported, which is the whole failure
# mode `thresholds.json` exists to prevent.
REVISION = "75299740cff05894ef42d7ad990666691efdd2da"

# The three tables. Names and columns are recorded in DATASET-PROVENANCE.md.
TABLES = ("revlogs", "cards", "decks")

HF_HOST = "https://huggingface.co"

# Listed in .gitignore as `/speedrun-analysis/appendix_b/data/`.
# `_assert_untracked()` re-checks at runtime rather than trusting that entry to
# still be there.
DEFAULT_DEST = Path(__file__).resolve().parent / "data"

USER_AGENT = "speedrun-appendix-b-fetch/1 (+https://github.com/ankitects/anki fork)"

# Parquet's file-format magic, at both ends of a well-formed file. Checking it
# is not a schema check -- it is the cheapest possible answer to "did I get a
# parquet file or an HTML error page?", and it needs no third-party reader.
PARQUET_MAGIC = b"PAR1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class FetchError(RuntimeError):
    """Anything that should stop the run with a message a human can act on."""


# --------------------------------------------------------------------------
# Token discovery. Nothing here returns the token to a caller that prints.
# --------------------------------------------------------------------------


@dataclass
class Token:
    """A token plus *where it came from*, never where it came from plus a value.

    `source` is safe to print. `value` is not, and is the only string registered
    with `_scrub()`.
    """

    value: str
    source: str

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"Token(source={self.source!r}, value=<redacted>)"

    __str__ = __repr__


def _token_file_candidates() -> list[Path]:
    """The files the HuggingFace CLI is documented to write a token to."""
    candidates: list[Path] = []
    explicit = os.environ.get("HF_TOKEN_PATH")
    if explicit:
        candidates.append(Path(explicit))
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        candidates.append(Path(hf_home) / "token")
    candidates.append(Path.home() / ".cache" / "huggingface" / "token")
    candidates.append(Path.home() / ".huggingface" / "token")
    return candidates


def find_token() -> Token | None:
    """Env first, then the CLI's token files. Returns None rather than raising."""
    for var in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        raw = os.environ.get(var, "").strip()
        if raw:
            return Token(raw, f"environment variable {var}")
    for path in _token_file_candidates():
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw:
            return Token(raw, f"file {path}")
    return None


NO_TOKEN_MESSAGE = f"""\
No HuggingFace token found, so nothing was downloaded.

{DATASET_ID} is a GATED dataset. Reading it is a three-step
process and no part of it can be automated from here:

  1. Create a HuggingFace account (or sign in) at https://huggingface.co/join
  2. Open https://huggingface.co/datasets/{DATASET_ID}
     and accept the access request. The gate is `gated: auto`, so acceptance is
     immediate -- but it requires agreeing to share your account's contact
     information (username and email) with the dataset's authors, and it
     requires accepting the dataset's own custom licence, which this project has
     NOT been able to read. See DATASET-PROVENANCE.md before you agree.
  3. Create a token with `read` scope at
     https://huggingface.co/settings/tokens and make it visible here by either:
       export HF_TOKEN=hf_...                  (this shell only; nothing is stored)
     or
       pip install huggingface_hub && hf auth login   (writes ~/.cache/huggingface/token)

Then re-run this script. It reads, in order:
  $HF_TOKEN, $HUGGING_FACE_HUB_TOKEN, $HUGGINGFACE_HUB_TOKEN,
  $HF_TOKEN_PATH, $HF_HOME/token, ~/.cache/huggingface/token,
  ~/.huggingface/token

Do not paste the token into this repository. It is never printed, never logged
and never written to the manifest, and there is no code path here that would
put it in a file.\
"""


def _scrub(text: str, secrets: Iterable[str]) -> str:
    """Redact every secret from a string that is about to be shown to a human.

    Applied to *all* output, including exception text, on the principle that a
    token leak is not made acceptable by being accidental.
    """
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "<redacted>")
    return out


# --------------------------------------------------------------------------
# Paths. The one rule: never write where git can see it.
# --------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _assert_untracked(dest: Path) -> None:
    """Refuse to download into a path git tracks or would track.

    `.gitignore` carries the entry, but an entry can be removed by someone who
    does not know why it is there. This is the check that actually holds the
    line, and it runs before a single byte is written.
    """
    root = _repo_root()
    try:
        rel = dest.resolve().relative_to(root)
    except ValueError:
        # Outside the repository entirely; git cannot see it.
        return
    ignored = _git_check_ignore(root, dest)
    if ignored is None:
        raise FetchError(
            f"Cannot determine whether {rel} is gitignored (git not available).\n"
            "Refusing to download into the working tree. Pass --dest with a path\n"
            "outside the repository."
        )
    if not ignored:
        raise FetchError(
            f"{rel} is NOT gitignored, and this dataset must never be committed.\n"
            "Add it to .gitignore, or pass --dest with a path outside the repo.\n"
            "No payload from this dataset may enter git history."
        )


def _git_check_ignore(root: Path, dest: Path) -> bool | None:
    """True if git ignores `dest`, False if not, None if git could not answer.

    The trailing separator is load-bearing and was put there by a test that
    caught its absence. `.gitignore` carries a directory-only rule
    (`/speedrun-analysis/appendix_b/data/`), and `git check-ignore` will not match
    a directory-only rule against a bare path that does not yet exist on disk --
    which, on a fresh clone, is exactly the state this runs in. Asking about
    `<dest>/` matches whether or not the directory exists.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", f"{dest}{os.sep}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


# --------------------------------------------------------------------------
# HTTP. Stdlib only, revision pinned on every request.
# --------------------------------------------------------------------------


class _StripAuthOnCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    """Drop the Authorization header when a redirect leaves huggingface.co.

    HF's resolve endpoints 302 to a CDN with the credentials already baked into
    the signed URL. Forwarding our bearer token to that host would both leak it
    to a third party and make the request fail, so it is removed here rather
    than being left to chance.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is None:
            return None
        old_host = urllib.parse.urlparse(req.full_url).netloc
        new_host = urllib.parse.urlparse(newurl).netloc
        if old_host != new_host:
            for key in list(new.headers):
                if key.lower() == "authorization":
                    del new.headers[key]
            new.unredirected_hdrs.pop("Authorization", None)
        return new


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_StripAuthOnCrossHostRedirect())


def _request(url: str, token: Token, method: str = "GET") -> urllib.request.Request:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token.value}")
    req.add_header("User-Agent", USER_AGENT)
    return req


def _explain_http_error(err: urllib.error.HTTPError, what: str) -> FetchError:
    """Turn an HTTP status into the specific thing the user has to go and do."""
    if err.code in (401, 403):
        return FetchError(
            f"HuggingFace returned {err.code} for {what}.\n\n"
            f"The token was found and sent, so this is an ACCESS problem, not a\n"
            f"missing-token problem. {DATASET_ID} is gated:\n"
            f"  * open https://huggingface.co/datasets/{DATASET_ID}\n"
            f"    while signed in as the account that owns this token, and accept\n"
            f"    the access request (it asks you to share your contact info and\n"
            f"    to accept the dataset's custom licence);\n"
            f"  * check the token has `read` scope, and -- if it is a fine-grained\n"
            f"    token -- that this dataset is in its allow-list;\n"
            f"  * a token that works for public repos still returns 403 here.\n"
            f"Nothing was downloaded."
        )
    if err.code == 404:
        return FetchError(
            f"HuggingFace returned 404 for {what}.\n"
            f"Either the pinned revision {REVISION[:12]} no longer exists, or the\n"
            f"file layout assumed by this script is wrong. Run --list to ask the\n"
            f"repository what it actually contains at that revision.\n"
            f"Nothing was downloaded, and no other revision was tried."
        )
    if err.code == 416:
        return FetchError(f"Range request rejected for {what}; delete the partial file and retry.")
    return FetchError(f"HuggingFace returned {err.code} {err.reason} for {what}.")


def _resolve_url(path: str) -> str:
    return f"{HF_HOST}/datasets/{DATASET_ID}/resolve/{REVISION}/{path}"


def _tree_url(subdir: str = "", recursive: bool = True) -> str:
    suffix = f"/{subdir}" if subdir else ""
    tail = "?recursive=1" if recursive else ""
    return f"{HF_HOST}/api/datasets/{DATASET_ID}/tree/{REVISION}{suffix}{tail}"


@dataclass
class RemoteFile:
    """What the server says about one file, before we have any of its bytes."""

    path: str
    size: int | None = None
    # LFS sha256 when the server exposes one; None for small non-LFS files.
    remote_sha256: str | None = None
    commit: str | None = None


def head_remote(path: str, token: Token) -> RemoteFile:
    """HEAD one file at the pinned revision. Raises FetchError on any failure."""
    req = _request(_resolve_url(path), token, method="HEAD")
    try:
        with _opener().open(req, timeout=60) as resp:
            headers = resp.headers
    except urllib.error.HTTPError as err:
        raise _explain_http_error(err, f"{path} (HEAD)") from None
    except urllib.error.URLError as err:
        raise FetchError(f"Network error for {path}: {err.reason}") from None

    commit = headers.get("X-Repo-Commit")
    size_raw = headers.get("X-Linked-Size") or headers.get("Content-Length")
    etag = (headers.get("X-Linked-Etag") or headers.get("ETag") or "").strip('"')
    return RemoteFile(
        path=path,
        size=int(size_raw) if size_raw and size_raw.isdigit() else None,
        remote_sha256=etag if _SHA256_RE.match(etag) else None,
        commit=commit,
    )


def list_remote(token: Token, subdir: str = "") -> list[RemoteFile]:
    """Enumerate files at the pinned revision via the tree API.

    This is what makes the assumed hive layout falsifiable: `--list` asks the
    repository rather than trusting the layout inferred from the dataset
    builder's source.
    """
    req = _request(_tree_url(subdir), token)
    try:
        with _opener().open(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raise _explain_http_error(err, f"tree listing of {subdir or '/'}") from None
    except urllib.error.URLError as err:
        raise FetchError(f"Network error listing {subdir or '/'}: {err.reason}") from None

    out: list[RemoteFile] = []
    for entry in payload:
        if entry.get("type") != "file":
            continue
        lfs = entry.get("lfs") or {}
        oid = lfs.get("oid") or lfs.get("sha256") or ""
        out.append(
            RemoteFile(
                path=entry["path"],
                size=lfs.get("size") or entry.get("size"),
                remote_sha256=oid if _SHA256_RE.match(str(oid)) else None,
            )
        )
    return out


def download_one(remote: RemoteFile, dest: Path, token: Token) -> Path:
    """Stream one file to disk. Writes to `.part` and renames only on success."""
    target = dest / remote.path
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")

    req = _request(_resolve_url(remote.path), token)
    try:
        with _opener().open(req, timeout=300) as resp, open(partial, "wb") as fh:
            served_commit = resp.headers.get("X-Repo-Commit")
            _assert_pinned_revision(served_commit, remote.path)
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
    except urllib.error.HTTPError as err:
        partial.unlink(missing_ok=True)
        raise _explain_http_error(err, remote.path) from None
    except urllib.error.URLError as err:
        partial.unlink(missing_ok=True)
        raise FetchError(f"Network error downloading {remote.path}: {err.reason}") from None

    partial.replace(target)
    return target


def _assert_pinned_revision(served_commit: str | None, what: str) -> None:
    """A response from any revision other than the pin is a hard failure.

    Not a warning. A number derived from a different snapshot than the one the
    provenance file names is a number with false provenance, which is worse than
    no number.
    """
    if served_commit is None:
        # Older/proxied responses omit the header. Say so; do not pretend.
        return
    if served_commit != REVISION:
        raise FetchError(
            f"Revision mismatch for {what}: asked for {REVISION}, "
            f"server answered from {served_commit}. Refusing the file."
        )


# --------------------------------------------------------------------------
# Verification of what actually landed on disk.
# --------------------------------------------------------------------------


@dataclass
class Verification:
    path: str
    bytes_on_disk: int
    sha256: str
    checks: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(v.startswith(("PASS", "SKIP")) for v in self.checks.values())


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parquet_magic_check(path: Path, size: int) -> str:
    """Cheapest honest answer to 'is this a parquet file or an error page?'."""
    if size < 8:
        return "FAIL: file is shorter than a parquet header+footer"
    with open(path, "rb") as fh:
        head = fh.read(4)
        fh.seek(-4, os.SEEK_END)
        tail = fh.read(4)
    if head == PARQUET_MAGIC and tail == PARQUET_MAGIC:
        return "PASS: PAR1 magic at both ends"
    return f"FAIL: expected PAR1 at both ends, got head={head!r} tail={tail!r}"


def verify(path: Path, remote: RemoteFile, dest: Path) -> Verification:
    """Check size, digest and file type. Records SKIP where it cannot check."""
    size = path.stat().st_size
    digest = _sha256_of(path)
    checks: dict[str, str] = {}

    if size == 0:
        checks["nonempty"] = "FAIL: zero bytes"
    else:
        checks["nonempty"] = f"PASS: {size:,} bytes"

    if remote.size is None:
        checks["size"] = "SKIP: server did not report a size"
    elif remote.size == size:
        checks["size"] = f"PASS: matches server-reported {remote.size:,}"
    else:
        checks["size"] = f"FAIL: server said {remote.size:,}, got {size:,}"

    if remote.remote_sha256 is None:
        checks["sha256"] = "SKIP: server exposed no LFS sha256 to compare against"
    elif remote.remote_sha256 == digest:
        checks["sha256"] = "PASS: matches server LFS oid"
    else:
        checks["sha256"] = f"FAIL: server oid {remote.remote_sha256}, computed {digest}"

    if path.suffix == ".parquet":
        checks["format"] = _parquet_magic_check(path, size)
    else:
        checks["format"] = "SKIP: not a .parquet file"

    if remote.commit is None:
        checks["revision"] = "SKIP: no X-Repo-Commit header on the response"
    elif remote.commit == REVISION:
        checks["revision"] = f"PASS: served from {REVISION}"
    else:
        checks["revision"] = f"FAIL: served from {remote.commit}, wanted {REVISION}"

    return Verification(
        path=str(path.relative_to(dest)),
        bytes_on_disk=size,
        sha256=digest,
        checks=checks,
    )


# --------------------------------------------------------------------------
# Which files to ask for.
# --------------------------------------------------------------------------


def parse_users(spec: str) -> list[int] | None:
    """`1-3`, `1,4,9`, `all`. None means 'every user', which is ~15.7 GB."""
    if spec.strip().lower() == "all":
        return None
    users: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, _, hi_s = part.partition("-")
            lo, hi = int(lo_s), int(hi_s)
            if hi < lo:
                raise FetchError(f"Bad user range {part!r}: {hi} < {lo}")
            users.extend(range(lo, hi + 1))
        else:
            users.append(int(part))
    if not users:
        raise FetchError("No users selected.")
    return sorted(set(users))


def assumed_paths(users: Sequence[int], tables: Sequence[str]) -> list[str]:
    """The hive-partition layout, inferred from source rather than observed.

    `anki-revlogs-dataset-builder/build_parquet.py::save_to_parquet` writes
    `pq.write_to_dataset(..., partition_cols=["user_id"])` and then renames each
    partition's file to `data.parquet`; `srs-benchmark/data_loader.py` reads back
    `data_path / kind / f"user_id={user_id}"`. That is where this layout comes
    from. It is an inference from two public repositories, not something anyone
    here has seen in the gated repo -- which is exactly why `--list` exists and
    why every path is HEADed before it is fetched.
    """
    return [f"{table}/user_id={uid}/data.parquet" for uid in users for table in tables]


def select_remote_files(
    token: Token, users: list[int] | None, tables: Sequence[str], use_listing: bool
) -> list[RemoteFile]:
    if users is None or use_listing:
        listed = list_remote(token)
        wanted = [f for f in listed if f.path.split("/")[0] in tables]
        if users is not None:
            keep = {f"user_id={uid}" for uid in users}
            wanted = [f for f in wanted if any(seg in keep for seg in f.path.split("/"))]
        if not wanted:
            raise FetchError(
                "The tree listing returned no matching files. The layout assumed by\n"
                "this script may be wrong; inspect the full listing with --list."
            )
        return wanted
    return [RemoteFile(path=p) for p in assumed_paths(users, tables)]


# --------------------------------------------------------------------------
# huggingface_hub path (used only when it is already installed).
# --------------------------------------------------------------------------


def _hub_available() -> bool:
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        return False
    return True


def download_via_hub(paths: Sequence[str], dest: Path, token: Token) -> list[Path]:
    """Same pin, same destination, someone else's retry logic."""
    from huggingface_hub import snapshot_download

    local = snapshot_download(
        repo_id=DATASET_ID,
        repo_type="dataset",
        revision=REVISION,
        allow_patterns=list(paths),
        local_dir=str(dest),
        token=token.value,
    )
    return [Path(local) / p for p in paths]


# --------------------------------------------------------------------------
# Reporting.
# --------------------------------------------------------------------------


def write_manifest(dest: Path, results: list[Verification], mode: str, secrets: list[str]) -> Path:
    """A machine-readable record of exactly what landed, beside the data.

    Lives inside the gitignored download directory on purpose: it describes a
    payload this repository is not allowed to keep, so it is not evidence this
    repository may carry either.
    """
    manifest = {
        "dataset_id": DATASET_ID,
        "revision": REVISION,
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transport": mode,
        "gated": True,
        "licence": "custom 'anki-revlogs-10k License'; UNREAD -- see DATASET-PROVENANCE.md",
        "synthetic": False,
        "files": [
            {
                "path": r.path,
                "bytes": r.bytes_on_disk,
                "sha256": r.sha256,
                "checks": r.checks,
                "ok": r.ok,
            }
            for r in results
        ],
        "all_ok": all(r.ok for r in results),
    }
    path = dest / "download-manifest.json"
    path.write_text(_scrub(json.dumps(manifest, indent=2), secrets) + "\n", encoding="utf-8")
    return path


def _print(text: str, secrets: Iterable[str]) -> None:
    print(_scrub(text, secrets))


# --------------------------------------------------------------------------
# Entry point.
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Fetch {DATASET_ID} at pinned revision {REVISION[:12]}.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--users",
        default="1-3",
        help="user ids to fetch: '1-3', '1,4,9', or 'all' (~15.7 GB, needs --yes)",
    )
    parser.add_argument(
        "--tables",
        default=",".join(TABLES),
        help=f"comma-separated subset of {','.join(TABLES)}",
    )
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help="download directory")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="check token + access + revision and exit; downloads nothing",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="print the repository's own file listing at the pinned revision",
    )
    parser.add_argument(
        "--use-listing",
        action="store_true",
        help="select files from the tree API instead of the assumed layout",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="force the stdlib HTTP path even if huggingface_hub is installed",
    )
    parser.add_argument("--yes", action="store_true", help="confirm a whole-dataset download")
    return parser


def _preflight(token: Token, secrets: list[str]) -> int:
    """Prove access and the pin without fetching a payload."""
    _print(f"token source: {token.source}", secrets)
    probe = f"{TABLES[0]}/user_id=1/data.parquet"
    _print(f"HEAD {probe} @ {REVISION[:12]}", secrets)
    remote = head_remote(probe, token)
    _assert_pinned_revision(remote.commit, probe)
    _print(
        "  reachable: yes\n"
        f"  server revision: {remote.commit or 'not reported'}\n"
        f"  size: {remote.size if remote.size is not None else 'not reported'}\n"
        f"  lfs sha256: {remote.remote_sha256 or 'not reported'}",
        secrets,
    )
    _print("preflight OK. Nothing was downloaded.", secrets)
    return 0


def _do_list(token: Token, secrets: list[str]) -> int:
    files = list_remote(token)
    _print(f"{len(files)} files at {DATASET_ID}@{REVISION[:12]}", secrets)
    for f in sorted(files, key=lambda x: x.path)[:200]:
        size = f"{f.size:,}" if f.size else "?"
        _print(f"  {f.path}  {size} bytes", secrets)
    if len(files) > 200:
        _print(f"  ... {len(files) - 200} more", secrets)
    return 0


def _fetch(args: argparse.Namespace, token: Token, secrets: list[str]) -> int:
    users = parse_users(args.users)
    tables = tuple(t.strip() for t in args.tables.split(",") if t.strip())
    unknown = [t for t in tables if t not in TABLES]
    if unknown:
        raise FetchError(f"Unknown table(s) {unknown}; known tables are {list(TABLES)}.")
    if users is None and not args.yes:
        raise FetchError(
            "--users all downloads the whole dataset (~15.7 GB per the dataset card).\n"
            "Re-run with --yes if that is what you meant."
        )

    dest = Path(args.dest).expanduser().resolve()
    _assert_untracked(dest)

    remotes = select_remote_files(token, users, tables, args.use_listing)
    _print(f"{len(remotes)} file(s) selected -> {dest}", secrets)

    # HEAD everything before fetching anything, so a wrong layout or a revoked
    # grant fails before half a dataset is on disk.
    resolved: list[RemoteFile] = []
    for remote in remotes:
        head = head_remote(remote.path, token)
        _assert_pinned_revision(head.commit, remote.path)
        if remote.remote_sha256 and not head.remote_sha256:
            head.remote_sha256 = remote.remote_sha256
        resolved.append(head)

    # Created only once every HEAD has succeeded, so a run that fails on access
    # or on a wrong layout leaves no empty directory behind.
    dest.mkdir(parents=True, exist_ok=True)

    use_hub = _hub_available() and not args.http
    mode = "huggingface_hub" if use_hub else "stdlib urllib"
    _print(f"transport: {mode}", secrets)

    if use_hub:
        download_via_hub([r.path for r in resolved], dest, token)
        local = [dest / r.path for r in resolved]
    else:
        local = [download_one(r, dest, token) for r in resolved]

    results = [verify(p, r, dest) for p, r in zip(local, resolved)]
    manifest = write_manifest(dest, results, mode, secrets)

    failed = [r for r in results if not r.ok]
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        _print(f"{status} {r.path}", secrets)
        for name, outcome in r.checks.items():
            _print(f"       {name}: {outcome}", secrets)
    _print(f"manifest: {manifest}", secrets)

    if failed:
        _print(f"{len(failed)} file(s) failed verification.", secrets)
        return 1
    _print(
        f"{len(results)} file(s) verified at revision {REVISION[:12]}.\n"
        "None of it is committed, and none of it may be. The dataset's licence is\n"
        "custom and UNREAD: see DATASET-PROVENANCE.md before deriving anything.",
        secrets,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    token = find_token()
    if token is None:
        print(NO_TOKEN_MESSAGE, file=sys.stderr)
        return 2
    secrets = [token.value]

    handlers: dict[str, Any] = {
        "preflight": lambda: _preflight(token, secrets),
        "list_only": lambda: _do_list(token, secrets),
    }
    try:
        for flag, handler in handlers.items():
            if getattr(args, flag):
                return handler()
        return _fetch(args, token, secrets)
    except FetchError as err:
        print(_scrub(str(err), secrets), file=sys.stderr)
        return 1
    except Exception as err:  # noqa: BLE001 - scrub before anything reaches a terminal
        print(_scrub(f"{type(err).__name__}: {err}", secrets), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
