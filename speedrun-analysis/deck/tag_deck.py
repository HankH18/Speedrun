# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Propose `speedrun::topic::` tags for an Anki deck against the USMLE outline.

    python3 speedrun-analysis/deck/tag_deck.py <deck.apkg>
    python3 speedrun-analysis/deck/tag_deck.py <deck.apkg> --emit-collection out.anki2
    python3 speedrun-analysis/deck/tag_deck.py --self-test

WHAT THIS DOES NOT DO
---------------------
It does not write to the user's .apkg. It does not write to the user's Anki
collection. It does not "apply" anything. It reads the package read-only (the
same way ``import_deck.py`` does, and it reuses that module's extractor), and
it emits two artefacts:

  * ``tag_proposals.json`` -- note id -> proposed tags, with the matched
    evidence and a confidence for every proposal.
  * ``tag_report.txt``     -- the same thing for a human to argue with.

Applying the proposals is a separate, explicit step that a person has to take.
``--emit-collection`` writes a THROWAWAY COPY of the collection with the
proposals stamped on, purely so that ``outline/coverage.py`` has something to
read; the source package is hashed before and after and the run fails if a
single byte moved.

HOW MATCHING WORKS
------------------
The matching vocabulary is derived from ``outline.json`` itself -- the
outline's own verbatim ``examples`` strings -- not from a keyword list invented
here. Each examples string is taken apart the way the outline punctuates it,
and each fragment is classified STRONG or WEAK:

  * material inside ( ) or [ ] is WEAK. The outline uses brackets for the
    causative organisms and for "eg" lists; a card that names the bug is not
    thereby a card about that organ system's disorder.
  * ``;``, ``/`` and newline separate coordinate list items -- STRONG.
  * ``:`` introduces a breakdown of the item before it -- both halves STRONG.
  * ``,`` is ambiguous. The outline uses it both for lists ("cellulitis,
    erysipelas, impetigo") and for index-style inversion ("myositis,
    infective"; "otitis, externa, media"). The first comma part is STRONG; a
    later part is STRONG only if it has two or more words, because a lone
    trailing word is far more often a modifier than a disease.
  * topic NAMES are WEAK. They are structural labels ("Infectious disorders",
    "Shock"), not mentions of an entity.

Fragments then become index entries of these kinds:

  * ``phrase`` -- STRONG, multi-word, e.g. "staphylococcal scalded skin
                  syndrome". Can establish a proposal.
  * ``term``   -- STRONG, single word, e.g. "osteomyelitis". Can establish a
                  proposal. Also produced by stripping a purely generic
                  modifier: "bacterial endocarditis" -> "endocarditis", since
                  nothing specific was thrown away.
  * ``head``   -- the head noun of a STRONG phrase whose modifier was NOT
                  generic ("lobar pneumonia" -> "pneumonia"). Corroborates
                  only.
  * ``weak``   -- everything ruled WEAK above. Corroborates only.

A phrase used by many topics discriminates nothing, so entries are dropped
above ``MAX_DOC_FREQUENCY`` topics and discounted below it. The only
hand-written vocabulary in this file is ``ORGANISM_ALIASES``: purely
abbreviation expansion ("S. aureus" -> "Staphylococcus aureus") so that deck
shorthand can be found in outline spelling. It invents no clinical
equivalences, and every alias that fires is recorded in the evidence trail.

CONFIDENCE POLICY
-----------------
  HIGH    at least one ``phrase`` or ``term`` hit that belongs to exactly ONE
          outline topic -- or, if it belongs to several, to several topics
          that all sit under one common ancestor at level >= 2, in which case
          the proposal backs off to that ancestor rather than guessing which
          child was meant.
  MEDIUM  some evidence, but all of it is shared between unrelated topics or
          is head-noun-only. Score >= MEDIUM_MIN.
  LOW     a trace of evidence, below MEDIUM_MIN.
  NONE    nothing in the outline's vocabulary appears in the note.

Only HIGH is proposed as a tag by default. MEDIUM/LOW notes are listed in the
report with their best candidate so a human can adjudicate them, and are left
UNTAGGED. An untagged note is honest; a wrongly tagged one silently corrupts
the coverage number, which is the one thing this whole pipeline exists to
produce.

Standard library only, by project rule.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_deck  # noqa: E402  (needs the path insert above)

TAG_PREFIX = "speedrun::topic::"

EXIT_OK = 0
EXIT_INPUT = 2  # deck or outline missing / unreadable
EXIT_MUTATED = 3  # the source package changed during the run
EXIT_SELFTEST = 5  # --self-test found a real defect
EXIT_USAGE = 64  # bad command line (EX_USAGE)

# --------------------------------------------------------------------------
# Tunables. Every number here is a policy choice, not a measurement; they are
# printed in the report so a reader can see what produced the match rate.
# --------------------------------------------------------------------------

MAX_DOC_FREQUENCY = 3  # index entries used by more than this many topics are dropped
MIN_PHRASE_CHARS = 5  # shorter candidates carry too little signal to trust
MIN_HEAD_CHARS = 7  # head nouns must be at least this long to be used
MAX_HEAD_TOKENS = 5  # only derive a head noun from phrases up to this many tokens
MAX_TAGS_PER_NOTE = 6  # a note proposing more than this is truncated and flagged
MEDIUM_MIN = 0.9  # score at or above this, without a HIGH hit, is MEDIUM

BASE_WEIGHT = {"phrase": 3.0, "term": 2.0, "head": 1.2, "weak": 1.0}
# Only these kinds may ESTABLISH a proposal. The rest can only corroborate one.
DECIDING_KINDS = ("phrase", "term")
# Discount for evidence shared between several topics. Index is the number of
# topics using the entry; entries above MAX_DOC_FREQUENCY never reach here.
IDF_FACTOR = {1: 1.0, 2: 0.5, 3: 0.3}
LCA_FACTOR = 0.7  # evidence resolved by backing off to a common ancestor
MIN_LCA_LEVEL = 2  # never back off to a whole level-1 exam section

# How an outline `examples` string is taken apart. See the module docstring.
BRACKET_RE = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")
LIST_SPLIT_RE = re.compile(r"[;/\n]|\s-\s|\.\s")
COLON_SPLIT_RE = re.compile(r":")
COMMA_SPLIT_RE = re.compile(r",")
TOKEN_RE = re.compile(r"[a-z0-9]+")

# Words that are pure connective tissue in the outline's prose, or so common
# across medicine that a hit on them says nothing about WHICH topic a card is
# about. Curated, and deliberately short: the document-frequency filter above
# does most of the work, and anything this list gets wrong is a false NEGATIVE
# (a note left untagged), never a false positive.
GENERIC_TERMS = frozenset(
    """
    acute adult adults advanced adverse affecting agent agents also
    associated bacteria bacterial benign both cause caused causes cell cells
    chronic clinical common complications congenital defect defects deficiency
    develop disease diseases disorder disorders drug drugs due early effect
    effects etiology examples factor factors failure female fever findings
    following fungal general genetic gland however human idiopathic including
    infant infants infection infections infectious inflammation inflammatory
    injury involving isolated known lower male malignant management mechanism
    metabolic mixed multiple neoplasm neoplasms nonspecific normal other others
    parasitic pathology patient patients primary process processes protozoal
    reaction reactions related response secondary severe species specific
    spirochetal state states structure symptom symptoms syndrome syndromes
    system systemic tissue toxic traumatic treatment tumor tumors type types
    unspecified upper viral virus viruses
    diagnosis prognosis mechanism mechanisms organism organisms metabolism
    """.split()
)

# A lone word is only allowed to DECIDE a proposal when it is morphologically a
# clinical entity. Without this, single words the outline happens to use in one
# sense and the deck in another -- "shock", "colon", "hemolysis", "adherence",
# "penicillins", "transfers" -- each mis-tag a dozen notes apiece; that was
# measured on this deck, not assumed. The cost is real and stated in the
# report: entity names with no suffix ("gangrene", "tetanus", "impetigo",
# "syphilis") lose their deciding power and their notes fall to MEDIUM.
CLINICAL_SUFFIXES = (
    "itis", "itides", "osis", "oses", "iasis", "emia", "aemia", "emias",
    "oma", "omas", "omata", "pathy", "pathies", "plasia", "trophy", "algia",
    "uria", "rrhea", "rrhoea", "penia", "megaly", "ectasis", "ism", "isms",
)

# Deck shorthand -> outline spelling. Pure abbreviation expansion: each entry
# is the standard long form of the abbreviation on its left, and nothing more.
# Ambiguous abbreviations are deliberately absent -- "GBS" (Group B
# Streptococcus vs Guillain-Barre syndrome) and "GAS" (Group A Streptococcus
# vs gas gangrene) are NOT here, because expanding them would be a guess.
ORGANISM_ALIASES: Tuple[Tuple[str, str], ...] = (
    (r"\b(?:staph(?:ylococcus)?|s)\.?\s+aureus\b", "staphylococcus aureus"),
    (r"\b(?:staph(?:ylococcus)?|s)\.?\s+epiderm\w*", "staphylococcus epidermidis"),
    (r"\b(?:staph(?:ylococcus)?|s)\.?\s+saproph\w*", "staphylococcus saprophyticus"),
    (r"\b(?:strep(?:tococcus)?|s)\.?\s+pneumo\w*", "streptococcus pneumoniae"),
    (r"\b(?:strep(?:tococcus)?|s)\.?\s+pyogenes\b", "streptococcus pyogenes"),
    (r"\bgroup a strep(?:tococcus|tococci)?\b", "streptococcus pyogenes"),
    (r"\b(?:strep(?:tococcus)?|s)\.?\s+agalactiae\b", "streptococcus agalactiae"),
    (r"\bgroup b strep(?:tococcus|tococci)?\b", "streptococcus agalactiae"),
    (r"\b(?:strep(?:tococcus)?|s)\.?\s+mutans\b", "streptococcus mutans"),
    (r"\b(?:escherichia|e)\.?\s+coli\b", "escherichia coli"),
    (r"\b(?:clostridium|c)\.?\s+difficile\b", "clostridium difficile"),
    (r"\b(?:clostridium|c)\.?\s+perfringens\b", "clostridium perfringens"),
    (r"\b(?:clostridium|c)\.?\s+botulinum\b", "clostridium botulinum"),
    (r"\b(?:clostridium|c)\.?\s+tetani\b", "clostridium tetani"),
    (r"\b(?:neisseria|n)\.?\s+gonorrhoeae\b", "neisseria gonorrhoeae"),
    (r"\b(?:neisseria|n)\.?\s+meningitidis\b", "neisseria meningitidis"),
    (r"\b(?:haemophilus|h)\.?\s+influenzae\b", "haemophilus influenzae"),
    (r"\b(?:vibrio|v)\.?\s+cholerae\b", "vibrio cholerae"),
    (r"\b(?:corynebacterium|c)\.?\s+diphtheriae\b", "corynebacterium diphtheriae"),
    (r"\b(?:pseudomonas|p)\.?\s+aeruginosa\b", "pseudomonas aeruginosa"),
    (r"\b(?:klebsiella|k)\.?\s+pneumoniae\b", "klebsiella pneumoniae"),
    (r"\b(?:bacillus|b)\.?\s+anthracis\b", "bacillus anthracis"),
    (r"\b(?:bacillus|b)\.?\s+cereus\b", "bacillus cereus"),
    (r"\b(?:listeria|l)\.?\s+monocytogenes\b", "listeria monocytogenes"),
    (r"\b(?:treponema|t)\.?\s+pallidum\b", "treponema pallidum"),
    (r"\b(?:borrelia|b)\.?\s+burgdorferi\b", "borrelia burgdorferi"),
)

# A topic counts as microbiology-relevant when the OUTLINE'S OWN wording says
# so -- the topic name contains one of these words. No clinical judgement of
# ours is layered on top; the resulting list is printed in full so a reader can
# see exactly which topics the rule selected.
MICRO_NAME_RE = re.compile(r"\b(infectious|infections?|hiv)\b", re.IGNORECASE)


class TaggerError(Exception):
    """A deck or outline could not be read, or changed while being read."""


# --------------------------------------------------------------------------
# Text normalisation
# --------------------------------------------------------------------------


def normalise(raw: str) -> str:
    """Fold text to lowercase ASCII words, dropping markup, emoji and accents.

    Both the deck and the outline go through this, so 'Behcet' and 'Behçet'
    compare equal instead of silently failing to match.
    """
    text = re.sub(r"<[^>]*>", " ", raw)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    # Anything outside the small ASCII set below (emoji, arrows, Greek) is not
    # vocabulary either side shares, so it becomes a separator rather than
    # being glued onto a neighbouring word.
    text = re.sub(r"[^a-z0-9\s\-'./,;:()\[\]]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens_of(text: str) -> List[str]:
    return TOKEN_RE.findall(text)


def phrase_key(raw: str) -> Optional[str]:
    """Turn one raw candidate into an index key, or None if it is unusable."""
    text = normalise(raw)
    text = re.sub(r"^(?:eg|e g|ie|i e|including|includes|other|others)\b", " ", text)
    text = re.sub(r"[^a-z0-9\s\-']", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -'")
    if len(text) < MIN_PHRASE_CHARS:
        return None
    parts = tokens_of(text)
    if not parts:
        return None
    if all(p in GENERIC_TERMS or len(p) < 3 for p in parts):
        return None
    return text


def expand_aliases(text: str) -> Tuple[str, List[str]]:
    """Append outline spellings for any deck shorthand present.

    Returns the searchable text and the list of aliases that fired. Nothing is
    replaced -- the original wording stays searchable too.
    """
    fired: List[str] = []
    additions: List[str] = []
    for pattern, canonical in ORGANISM_ALIASES:
        if re.search(pattern, text):
            fired.append(canonical)
            if canonical not in text:
                additions.append(canonical)
    if additions:
        text = text + " . " + " . ".join(sorted(set(additions)))
    return text, sorted(set(fired))


# --------------------------------------------------------------------------
# Outline index
# --------------------------------------------------------------------------


class Index:
    """Phrase -> topics, plus the outline hierarchy needed to back off."""

    def __init__(self) -> None:
        self.postings: Dict[str, Dict[str, str]] = {}
        self.parent: Dict[str, Optional[str]] = {}
        self.level: Dict[str, int] = {}
        self.name: Dict[str, str] = {}
        self.tag: Dict[str, str] = {}
        self.axis: Dict[str, str] = {}
        self.dropped_generic = 0
        self.dropped_common = 0

    def _add(self, phrase: Optional[str], topic_id: str, kind: str) -> None:
        if phrase is None:
            return
        slot = self.postings.setdefault(phrase, {})
        current = slot.get(topic_id)
        if current is None or BASE_WEIGHT[kind] > BASE_WEIGHT[current]:
            slot[topic_id] = kind

    def ancestors(self, topic_id: str) -> List[str]:
        """topic_id first, then each parent up to the axis root."""
        chain = [topic_id]
        current = self.parent.get(topic_id)
        while current is not None:
            chain.append(current)
            current = self.parent.get(current)
        return chain

    def lca(self, topic_ids: Sequence[str]) -> Optional[str]:
        chains = [self.ancestors(t) for t in topic_ids]
        shared: Optional[Set[str]] = None
        for chain in chains:
            shared = set(chain) if shared is None else shared & set(chain)
        if not shared:
            return None
        return max(shared, key=lambda t: (self.level.get(t, 0), t))


def split_examples(source: str) -> List[Tuple[str, bool]]:
    """Take one `examples` string apart into (fragment, strong) pairs.

    The rules, and why, are in the module docstring. Nothing here is specific
    to microbiology; it is punctuation handling for the outline's own prose.
    """
    out: List[Tuple[str, bool]] = []
    bracketed: List[str] = []

    def collect(match: "re.Match[str]") -> str:
        bracketed.append(match.group(1) or match.group(2) or "")
        return " ; "

    stripped = source
    for _ in range(4):  # unwind nesting a few levels; the outline nests shallowly
        stripped, count = BRACKET_RE.subn(collect, stripped)
        if not count:
            break

    for group in bracketed:
        for piece in re.split(r"[;,]", group):
            out.append((piece, False))

    for item in LIST_SPLIT_RE.split(stripped):
        for subitem in COLON_SPLIT_RE.split(item):
            parts = COMMA_SPLIT_RE.split(subitem)
            for position, part in enumerate(parts):
                strong = position == 0 or len(tokens_of(normalise(part))) >= 2
                out.append((part, strong))
    return out


def is_clinical_word(token: str) -> bool:
    return token.endswith(CLINICAL_SUFFIXES)


def _index_fragment(index: Index, topic_id: str, fragment: str, strong: bool) -> None:
    key = phrase_key(fragment)
    if key is None:
        return
    parts = tokens_of(key)
    if not strong:
        index._add(key, topic_id, "weak")
        return
    if len(parts) > 1:
        index._add(key, topic_id, "phrase")
    else:
        index._add(key, topic_id, "term" if is_clinical_word(parts[0]) else "weak")
    if not 2 <= len(parts) <= MAX_HEAD_TOKENS:
        return
    head = parts[-1]
    if len(head) < MIN_HEAD_CHARS or head in GENERIC_TERMS:
        return
    # Dropping "bacterial" from "bacterial endocarditis" loses nothing, so the
    # head keeps full strength. Dropping "lobar" from "lobar pneumonia" loses
    # the thing that made it specific, so the head can only corroborate.
    only_generic_modifiers = all(p in GENERIC_TERMS for p in parts[:-1])
    promote = only_generic_modifiers and is_clinical_word(head)
    index._add(head, topic_id, "term" if promote else "head")


def build_index(topics: Sequence[dict]) -> Index:
    index = Index()
    for topic in topics:
        topic_id = topic["id"]
        index.parent[topic_id] = topic.get("parent_id")
        index.level[topic_id] = int(topic.get("level") or 0)
        index.name[topic_id] = topic.get("name") or topic_id
        index.axis[topic_id] = topic.get("axis") or "UNKNOWN"
        index.tag[topic_id] = topic.get("tag") or (TAG_PREFIX + "::".join(topic["path"]))

    for topic in topics:
        topic_id = topic["id"]
        _index_fragment(index, topic_id, topic.get("name") or "", strong=False)
        for source in topic.get("examples") or []:
            for fragment, strong in split_examples(source):
                _index_fragment(index, topic_id, fragment, strong)

    for phrase in list(index.postings):
        parts = tokens_of(phrase)
        if all(p in GENERIC_TERMS for p in parts):
            del index.postings[phrase]
            index.dropped_generic += 1
        elif len(index.postings[phrase]) > MAX_DOC_FREQUENCY:
            del index.postings[phrase]
            index.dropped_common += 1
    return index


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def compile_index(index: Index) -> List[Tuple[str, "re.Pattern[str]"]]:
    return [
        (phrase, re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"))
        for phrase in sorted(index.postings)
    ]


def match_note(
    text: str, index: Index, compiled: Sequence[Tuple[str, "re.Pattern[str]"]]
) -> Tuple[Dict[str, dict], List[dict]]:
    """Score one note's text against every outline topic.

    Returns (per-topic record, list of hits that could not be attributed).
    """
    per_topic: Dict[str, dict] = {}
    unattributed: List[dict] = []

    def note(topic_id: str, evidence: dict) -> None:
        slot = per_topic.setdefault(topic_id, {"score": 0.0, "evidence": []})
        slot["score"] += evidence["weight"]
        slot["evidence"].append(evidence)

    for phrase, pattern in compiled:
        if phrase not in text or not pattern.search(text):
            continue
        owners = index.postings[phrase]
        df = len(owners)
        if df == 1:
            topic_id, kind = next(iter(owners.items()))
            note(
                topic_id,
                {
                    "phrase": phrase,
                    "kind": kind,
                    "topics_sharing": 1,
                    "via": "direct",
                    "weight": BASE_WEIGHT[kind] * IDF_FACTOR[1],
                },
            )
            continue

        strongest = max(owners.values(), key=lambda k: BASE_WEIGHT[k])
        for topic_id, kind in sorted(owners.items()):
            note(
                topic_id,
                {
                    "phrase": phrase,
                    "kind": kind,
                    "topics_sharing": df,
                    "via": "direct",
                    "weight": BASE_WEIGHT[kind] * IDF_FACTOR[df],
                },
            )
        ancestor = index.lca(sorted(owners))
        if ancestor is not None and index.level.get(ancestor, 0) >= MIN_LCA_LEVEL:
            note(
                ancestor,
                {
                    "phrase": phrase,
                    "kind": strongest,
                    "topics_sharing": df,
                    "via": "lca",
                    "weight": BASE_WEIGHT[strongest] * LCA_FACTOR,
                    "backed_off_from": sorted(owners),
                },
            )
        else:
            unattributed.append(
                {"phrase": phrase, "topics_sharing": df, "topics": sorted(owners)}
            )
    return per_topic, unattributed


def confidence_of(record: dict) -> str:
    for evidence in record["evidence"]:
        if evidence["kind"] not in DECIDING_KINDS:
            continue
        if evidence["via"] == "lca" or evidence["topics_sharing"] == 1:
            return "HIGH"
    if record["score"] >= MEDIUM_MIN:
        return "MEDIUM"
    return "LOW"


def prune_ancestors(topic_ids: Sequence[str], index: Index) -> List[str]:
    """Drop a topic when a more specific accepted topic sits beneath it."""
    keep = []
    for topic_id in topic_ids:
        descendants = [
            other
            for other in topic_ids
            if other != topic_id and topic_id in index.ancestors(other)
        ]
        if not descendants:
            keep.append(topic_id)
    return keep


# --------------------------------------------------------------------------
# Deck reading (read-only, via import_deck's extractor)
# --------------------------------------------------------------------------


def read_notes(apkg: str) -> Tuple[List[dict], dict, str]:
    """Return (notes, provenance, collection member name). Never writes."""
    before = import_deck.provenance_of(apkg)
    workdir = tempfile.mkdtemp(prefix="apkg-tagger-")
    try:
        with zipfile.ZipFile(apkg) as archive:
            names = set(archive.namelist())
            present = [m for m in import_deck.COLLECTION_MEMBERS if m in names]
            if not present:
                raise TaggerError(
                    "no collection member in {!r}; members: {}".format(
                        apkg, sorted(names)[:20]
                    )
                )
            member = present[0]
            blob = import_deck.extract_collection(archive, member, workdir)
            con = import_deck.open_readonly(blob)
            try:
                tables = import_deck.table_names(con)
                notetypes = (
                    import_deck.notetypes_schema18(con)
                    if "notetypes" in tables
                    else import_deck.notetypes_schema11(con)
                )
                rows = con.execute(
                    "select id, mid, tags, flds from notes order by id"
                ).fetchall()
            finally:
                con.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    after = import_deck.sha256_of(apkg)
    if after != before["sha256"]:
        raise TaggerError(
            "the source package changed while it was being read: {} -> {}".format(
                before["sha256"], after
            )
        )

    notes = []
    for note_id, mid, tags, flds in rows:
        fields = flds.split("\x1f")
        model = notetypes.get(mid, {})
        notes.append(
            {
                "note_id": note_id,
                "notetype": model.get("name", "UNKNOWN mid={}".format(mid)),
                "existing_tags": (tags or "").split(),
                "text": " . ".join(fields),
                "excerpt": import_deck.truncate(normalise(fields[0]), 110),
            }
        )
    return notes, before, member


def extract_collection_copy(apkg: str, destination: Path) -> str:
    """Copy the package's collection out to `destination`. Source untouched."""
    before = import_deck.sha256_of(apkg)
    workdir = tempfile.mkdtemp(prefix="apkg-tagger-copy-")
    try:
        with zipfile.ZipFile(apkg) as archive:
            names = set(archive.namelist())
            member = [m for m in import_deck.COLLECTION_MEMBERS if m in names][0]
            blob = import_deck.extract_collection(archive, member, workdir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(blob, str(destination))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if import_deck.sha256_of(apkg) != before:
        raise TaggerError("the source package changed while it was being copied")
    return member


def stamp_tags(collection: Path, proposals: Dict[int, List[str]]) -> int:
    """Write the proposed tags onto a COPY of the collection. Returns rows hit."""
    con = sqlite3.connect(str(collection))
    try:
        changed = 0
        for note_id, tags in sorted(proposals.items()):
            if not tags:
                continue
            # Anki stores tags space-delimited with a sentinel space each side.
            con.execute(
                "update notes set tags = ? where id = ?",
                (" " + " ".join(sorted(tags)) + " ", note_id),
            )
            changed += 1
        con.commit()
        return changed
    finally:
        con.close()


# --------------------------------------------------------------------------
# Driving the whole thing
# --------------------------------------------------------------------------


def load_outline(path: Path) -> Tuple[List[dict], str]:
    try:
        with path.open("rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise TaggerError("cannot read outline {}: {}".format(path, exc)) from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise TaggerError("{} is not valid JSON: {}".format(path, exc)) from exc
    topics = document.get("topics")
    if not isinstance(topics, list) or not topics:
        raise TaggerError("{} has no `topics` array".format(path))
    return topics, import_deck.sha256_of(str(path))


def analyse(notes: Sequence[dict], index: Index, min_confidence: str) -> List[dict]:
    compiled = compile_index(index)
    order = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    floor = order[min_confidence.upper()]
    results = []
    for note in notes:
        text, aliases = expand_aliases(normalise(note["text"]))
        per_topic, unattributed = match_note(text, index, compiled)
        candidates = []
        for topic_id, record in per_topic.items():
            candidates.append(
                {
                    "topic_id": topic_id,
                    "topic_name": index.name[topic_id],
                    "axis": index.axis[topic_id],
                    "tag": index.tag[topic_id],
                    "score": round(record["score"], 3),
                    "confidence": confidence_of(record),
                    "evidence": sorted(
                        record["evidence"], key=lambda e: (-e["weight"], e["phrase"])
                    ),
                }
            )
        candidates.sort(key=lambda c: (-order[c["confidence"]], -c["score"], c["topic_id"]))

        accepted_ids = [c["topic_id"] for c in candidates if order[c["confidence"]] >= floor]
        accepted_ids = prune_ancestors(accepted_ids, index)
        truncated = False
        if len(accepted_ids) > MAX_TAGS_PER_NOTE:
            ranked = [c["topic_id"] for c in candidates if c["topic_id"] in accepted_ids]
            accepted_ids = ranked[:MAX_TAGS_PER_NOTE]
            truncated = True

        best = candidates[0]["confidence"] if candidates else "NONE"
        results.append(
            {
                "note_id": note["note_id"],
                "notetype": note["notetype"],
                "excerpt": note["excerpt"],
                "existing_tags": note["existing_tags"],
                "aliases_fired": aliases,
                "best_confidence": best,
                "proposed_tags": [index.tag[t] for t in accepted_ids],
                "proposed_topic_ids": accepted_ids,
                "truncated_to_max_tags": truncated,
                "candidates": candidates,
                "ambiguous_hits": unattributed,
            }
        )
    return results


def summarise(results: Sequence[dict], topics: Sequence[dict], index: Index) -> dict:
    tagged = [r for r in results if r["proposed_tags"]]
    by_confidence: Dict[str, int] = {}
    for record in results:
        # Always the note's own best candidate, never the floor it cleared. At
        # the default --min-confidence=high the two agree, because a note is
        # only tagged when a HIGH candidate exists. Under --min-confidence
        # medium they do not: reporting a MEDIUM-tagged note as HIGH would
        # inflate this histogram, which is the one place a reader looks to see
        # how much of the match rate is actually confident.
        by_confidence[record["best_confidence"]] = (
            by_confidence.get(record["best_confidence"], 0) + 1
        )

    notes_per_topic: Dict[str, int] = {}
    for record in tagged:
        for topic_id in record["proposed_topic_ids"]:
            notes_per_topic[topic_id] = notes_per_topic.get(topic_id, 0) + 1

    hit_ids = set(notes_per_topic)
    hit_with_ancestors: Set[str] = set()
    for topic_id in hit_ids:
        hit_with_ancestors.update(index.ancestors(topic_id))

    micro = [t for t in topics if MICRO_NAME_RE.search(t.get("name") or "")]
    micro_hit = [t for t in micro if t["id"] in hit_with_ancestors]
    micro_missed = [t for t in micro if t["id"] not in hit_with_ancestors]

    return {
        "notes_total": len(results),
        "notes_tagged": len(tagged),
        "notes_untagged": len(results) - len(tagged),
        "notes_by_best_confidence": by_confidence,
        "tags_proposed_total": sum(len(r["proposed_tags"]) for r in tagged),
        "outline_topics_total": len(topics),
        "outline_topics_hit_exact": len(hit_ids),
        "outline_topics_hit_including_ancestors": len(hit_with_ancestors),
        "notes_per_topic": dict(sorted(notes_per_topic.items())),
        "micro_relevant_rule": MICRO_NAME_RE.pattern,
        "micro_relevant_total": len(micro),
        "micro_relevant_hit": [t["id"] for t in micro_hit],
        "micro_relevant_no_card": [
            {"id": t["id"], "name": t["name"], "axis": t["axis"], "level": t["level"]}
            for t in micro_missed
        ],
    }


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _evidence_line(evidence: dict) -> str:
    where = "unique" if evidence["topics_sharing"] == 1 else "shared x{}".format(
        evidence["topics_sharing"]
    )
    via = "" if evidence["via"] == "direct" else " [backed off to common ancestor]"
    return "        {:<6} {:<6} {:>5.2f}  {!r}{}".format(
        evidence["kind"], where, evidence["weight"], evidence["phrase"], via
    )


def _render_header(out: List[str], report: dict) -> None:
    prov = report["deck"]
    add = out.append
    add("=" * 78)
    add("PROPOSED OUTLINE TAGS -- {}".format(prov["filename"]))
    add("=" * 78)
    add("deck              {}".format(prov["path"]))
    add("deck sha256       {}".format(prov["sha256"]))
    add("collection member {}".format(report["collection_member"]))
    add("outline           {}".format(report["outline"]["path"]))
    add("outline sha256    {}".format(report["outline"]["sha256"]))
    add("generated (UTC)   {}".format(report["generated_utc"]))
    add("")
    add("NOTHING HERE HAS BEEN APPLIED. These are PROPOSALS. The source package")
    add("was opened read-only and its sha256 is unchanged: {}".format(report["source_unchanged"]))
    add("")
    cfg = report["config"]
    add("matcher configuration")
    add("  index entries kept            {}".format(cfg["index_entries"]))
    add("  dropped as generic            {}".format(cfg["dropped_generic"]))
    add("  dropped as used by > {} topics {}".format(MAX_DOC_FREQUENCY, cfg["dropped_common"]))
    add("  weights                       {}".format(BASE_WEIGHT))
    add("  shared-evidence discount      {}".format(IDF_FACTOR))
    add("  common-ancestor discount      {} (min level {})".format(LCA_FACTOR, MIN_LCA_LEVEL))
    add("  MEDIUM threshold              {}".format(MEDIUM_MIN))
    add("  min confidence proposed       {}".format(cfg["min_confidence"]))
    add("  curated organism aliases      {}".format(len(ORGANISM_ALIASES)))
    add("")


def _render_summary(out: List[str], summary: dict) -> None:
    add = out.append
    total = summary["notes_total"] or 1
    add("-" * 78)
    add("COVERAGE OF THE DECK")
    add("-" * 78)
    add(
        "  notes tagged      {} of {}  ({:.1f}%)".format(
            summary["notes_tagged"], summary["notes_total"],
            100.0 * summary["notes_tagged"] / total,
        )
    )
    add(
        "  notes UNTAGGED    {} of {}  ({:.1f}%)".format(
            summary["notes_untagged"], summary["notes_total"],
            100.0 * summary["notes_untagged"] / total,
        )
    )
    add("  tags proposed     {}".format(summary["tags_proposed_total"]))
    add("  best confidence per note (every note shown at its own best candidate):")
    for key in ("HIGH", "MEDIUM", "LOW", "NONE"):
        add("      {:<7} {}".format(key, summary["notes_by_best_confidence"].get(key, 0)))
    add("")
    add(
        "  outline topics hit exactly            {} of {}".format(
            summary["outline_topics_hit_exact"], summary["outline_topics_total"]
        )
    )
    add(
        "  outline topics hit incl. ancestors    {} of {}".format(
            summary["outline_topics_hit_including_ancestors"],
            summary["outline_topics_total"],
        )
    )
    add("")


def _render_notes(out: List[str], results: Sequence[dict], index: Index) -> None:
    add = out.append
    add("-" * 78)
    add("PROPOSALS, NOTE BY NOTE (tagged notes)")
    add("-" * 78)
    for record in results:
        if not record["proposed_tags"]:
            continue
        add("note {}  {}".format(record["note_id"], record["excerpt"]))
        if record["aliases_fired"]:
            add("    aliases fired: {}".format(", ".join(record["aliases_fired"])))
        if record["truncated_to_max_tags"]:
            add("    NOTE: more than {} topics qualified; kept the top {} by score.".format(
                MAX_TAGS_PER_NOTE, MAX_TAGS_PER_NOTE))
        for topic_id in record["proposed_topic_ids"]:
            candidate = next(c for c in record["candidates"] if c["topic_id"] == topic_id)
            add("    -> {}".format(index.tag[topic_id]))
            add("       {} | {} | score {:.2f}".format(
                candidate["confidence"], candidate["topic_name"], candidate["score"]))
            for evidence in candidate["evidence"][:6]:
                add(_evidence_line(evidence))
        add("")


def _render_untagged(out: List[str], results: Sequence[dict]) -> None:
    add = out.append
    add("-" * 78)
    add("LEFT UNTAGGED -- for human adjudication, NOT counted as coverage")
    add("-" * 78)
    for level in ("MEDIUM", "LOW", "NONE"):
        group = [
            r for r in results
            if not r["proposed_tags"] and r["best_confidence"] == level
        ]
        add("{} ({} notes)".format(level, len(group)))
        for record in group:
            add("  note {}  {}".format(record["note_id"], record["excerpt"]))
            if record["candidates"]:
                best = record["candidates"][0]
                add("      best candidate: {} (score {:.2f}) {}".format(
                    best["topic_id"], best["score"], best["topic_name"]))
                for evidence in best["evidence"][:3]:
                    add(_evidence_line(evidence))
        add("")


def _render_topics(out: List[str], summary: dict, index: Index) -> None:
    add = out.append
    add("-" * 78)
    add("OUTLINE TOPICS WITH AT LEAST ONE PROPOSED NOTE")
    add("-" * 78)
    for topic_id, count in sorted(
        summary["notes_per_topic"].items(), key=lambda kv: (-kv[1], kv[0])
    ):
        add("  {:>4}  {}".format(count, topic_id))
        add("        {}".format(index.name[topic_id]))
    add("")
    add("-" * 78)
    add("MICROBIOLOGY-RELEVANT OUTLINE TOPICS WITH NO CARD")
    add("-" * 78)
    add("  rule: topic NAME matches {} -- the outline's own wording,".format(
        summary["micro_relevant_rule"]))
    add("  no clinical judgement of ours layered on top.")
    add("  {} of {} such topics have at least one proposed note (counting a".format(
        len(summary["micro_relevant_hit"]), summary["micro_relevant_total"]))
    add("  parent as hit when a child is hit).")
    add("")
    for entry in summary["micro_relevant_no_card"]:
        add("  [{}] {}".format(entry["axis"], entry["id"]))
        add("       {}".format(entry["name"]))
    add("")


def render(report: dict, results: Sequence[dict], index: Index) -> str:
    out: List[str] = []
    _render_header(out, report)
    _render_summary(out, report["summary"])
    _render_notes(out, results, index)
    _render_untagged(out, results)
    _render_topics(out, report["summary"], index)
    out.append("-" * 78)
    out.append("KNOWN LIMITATIONS")
    out.append("-" * 78)
    for line in report["known_limitations"]:
        out.append("  * " + line)
    out.append("")
    return "\n".join(out)


KNOWN_LIMITATIONS = [
    "The 11 discipline-axis topics (Pathology, Microbiology, Pharmacology, ...) "
    "carry a one-word name and NO examples in outline.json, so there is no "
    "vocabulary to match against and this matcher proposes zero discipline "
    "tags. coverage.py will therefore report the whole discipline axis as "
    "uncovered. That is a fact about the outline's shape and about keyword "
    "matching, NOT evidence that the deck contains no microbiology.",
    "Matching is lexical. A card that teaches a topic without naming it -- "
    "mechanism-only cards on Gram staining, toxin biochemistry, plasmid "
    "transfer, antibiotic targets -- cannot be matched, because the outline "
    "gives those no vocabulary either. Those notes are reported as NONE.",
    "The outline states its examples are 'just examples', so a topic's "
    "vocabulary is incomplete by construction. Absence of a hit is weak "
    "evidence of absence of coverage.",
    "Head-noun evidence throws a modifier away, so it only supports a proposal "
    "unless the discarded modifier was itself generic ('bacterial "
    "endocarditis' -> 'endocarditis' keeps full strength; 'lobar pneumonia' -> "
    "'pneumonia' does not).",
    "A lone word may only decide a proposal if it carries a clinical suffix "
    "(-itis, -osis, -emia, -oma, -uria, ...). Without that rule the words the "
    "outline and the deck use in different senses -- shock, colon, hemolysis, "
    "adherence, penicillins, transfers -- mis-tagged 38 note/tag pairs on this "
    "deck. The rule also costs real matches: 'gangrene', 'tetanus', "
    "'impetigo', 'erysipelas', 'syphilis' and 'botulism' name real entities "
    "and carry no suffix, so notes resting on them alone fall to MEDIUM.",
    "A comma-separated outline fragment is ambiguous between a list and an "
    "index-style inversion, so a lone trailing word after a comma is treated "
    "as a modifier. That is right for 'myositis, infective' and wrong for "
    "'cellulitis, erysipelas, impetigo', where it demotes two real disease "
    "names.",
    "Some outline fragments are truncated phrases in their own right -- the "
    "bare 'hospital-acquired' matched a card about hospital-acquired "
    "pneumonia and proposed a musculoskeletal trauma topic. Proposals are "
    "printed with their deciding evidence precisely so a reviewer can catch "
    "this class of error before anything is applied.",
    "Nothing here has been applied to any collection. Applying is a separate, "
    "explicit step.",
]


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------


def _fixture_outline(path: Path) -> None:
    def topic(topic_id, name, level, parent, path_parts, examples):
        return {
            "id": topic_id,
            "name": name,
            "axis": "system",
            "level": level,
            "parent_id": parent,
            "path": path_parts,
            "tag": TAG_PREFIX + "::".join(path_parts),
            "weight_low": None,
            "weight_high": None,
            "weight_source": "UNKNOWN",
            "weight_note": "fixture",
            "examples": examples,
        }

    topics = [
        topic("sys.chest", "Chest", 1, None, ["system", "chest"], []),
        topic("sys.chest.lung", "Respiratory System", 2, "sys.chest",
              ["system", "chest", "lung"], []),
        topic(
            "sys.chest.lung.upper", "Infectious disorders", 3, "sys.chest.lung",
            ["system", "chest", "lung", "upper"], ["pharyngitis; shared marker disease"],
        ),
        topic(
            "sys.chest.lung.lower", "Infectious disorders", 3, "sys.chest.lung",
            ["system", "chest", "lung", "lower"], ["lobar pneumonia; shared marker disease"],
        ),
        topic(
            "sys.skin", "Skin", 1, None, ["system", "skin"],
            [
                "folliculitis; staphylococcal scalded skin syndrome; sunburn; "
                "myositis, infective (Fusobacterium necrophorum)"
            ],
        ),
    ]
    path.write_text(json.dumps({"topics": topics}), encoding="utf-8")


def _fixture_apkg(path: Path, notes: Sequence[Tuple[int, str]]) -> None:
    workdir = Path(tempfile.mkdtemp(prefix="tagger-selftest-"))
    try:
        db = workdir / "collection.anki21"
        con = sqlite3.connect(str(db))
        con.executescript(
            "create table col (id integer primary key, crt integer, mod integer, "
            "ver integer, models text, decks text);"
            "create table notes (id integer primary key, mid integer, tags text, flds text);"
            "create table cards (id integer primary key, nid integer, did integer);"
        )
        con.execute(
            "insert into col values (1, 0, 0, 11, ?, ?)",
            (
                json.dumps({"1": {"name": "Basic", "type": 0,
                                  "flds": [{"name": "Front"}, {"name": "Back"}],
                                  "tmpls": [{"name": "Card 1"}]}}),
                json.dumps({"1": {"name": "Default"}}),
            ),
        )
        for note_id, text in notes:
            con.execute("insert into notes values (?, 1, '', ?)", (note_id, text))
            con.execute("insert into cards values (?, ?, 1)", (note_id + 1, note_id))
        con.commit()
        con.close()
        with zipfile.ZipFile(str(path), "w") as archive:
            archive.write(str(db), "collection.anki21")
            archive.writestr("media", "{}")
            archive.writestr("meta", b"\x08\x02")
    finally:
        shutil.rmtree(str(workdir), ignore_errors=True)


def self_test() -> int:
    failures: List[str] = []

    def check(label: str, actual: object, expected: object) -> None:
        if actual != expected:
            failures.append("{}: expected {!r}, got {!r}".format(label, expected, actual))

    root = Path(tempfile.mkdtemp(prefix="tagger-selftest-root-"))
    try:
        outline_path = root / "outline.json"
        apkg_path = root / "fixture.apkg"
        _fixture_outline(outline_path)
        _fixture_apkg(
            apkg_path,
            [
                (1001, "What causes folliculitis?\x1fStaphylococcus aureus."),
                (1002, "What is a shared marker disease?\x1fA shared thing."),
                (1003, "Explain the Krebs cycle\x1fIt makes ATP."),
                (1004, "Which bug causes scalded skin?\x1fS. aureus exfoliatin."),
                (1005, "Name a lung infection\x1flobar pneumonia."),
                (1006, "What is sunburn?\x1fA burn, from the sun."),
                (1007, "Is this infective?\x1fYes, infective."),
                (1008, "Name a bug\x1fFusobacterium necrophorum."),
            ],
        )
        topics, _ = load_outline(outline_path)
        index = build_index(topics)
        notes, prov, member = read_notes(str(apkg_path))
        check("notes read", len(notes), 8)
        check("collection member", member, "collection.anki21")
        results = analyse(notes, index, "high")
        by_id = {r["note_id"]: r for r in results}

        check(
            "unique term tags the topic",
            by_id[1001]["proposed_topic_ids"],
            ["sys.skin"],
        )
        check(
            "evidence shared by siblings backs off to their parent",
            by_id[1002]["proposed_topic_ids"],
            ["sys.chest.lung"],
        )
        check("no evidence means no tag", by_id[1003]["proposed_tags"], [])
        check("no evidence is reported as NONE", by_id[1003]["best_confidence"], "NONE")
        check(
            "alias expansion is recorded",
            by_id[1004]["aliases_fired"],
            ["staphylococcus aureus"],
        )
        check(
            "multiword phrase tags the specific child",
            by_id[1005]["proposed_topic_ids"],
            ["sys.chest.lung.lower"],
        )
        check(
            "a lone word with no clinical suffix cannot decide",
            by_id[1006]["proposed_tags"],
            [],
        )
        check(
            "an inverted comma modifier cannot decide",
            by_id[1007]["proposed_tags"],
            [],
        )
        check(
            "an organism named inside brackets cannot decide",
            by_id[1008]["proposed_tags"],
            [],
        )
        check("bracketed organism is indexed, but weakly",
              index.postings.get("fusobacterium necrophorum"), {"sys.skin": "weak"})
        check("a lone non-clinical word is indexed weakly",
              index.postings.get("sunburn"), {"sys.skin": "weak"})

        sha_before = import_deck.sha256_of(str(apkg_path))
        copy_path = root / "copy.anki2"
        extract_collection_copy(str(apkg_path), copy_path)
        stamped = stamp_tags(copy_path, {1001: [TAG_PREFIX + "system::skin"]})
        check("stamped one note", stamped, 1)
        check(
            "source package untouched by stamping",
            import_deck.sha256_of(str(apkg_path)),
            sha_before,
        )
        con = sqlite3.connect("file:{}?mode=ro".format(copy_path), uri=True)
        try:
            (tags,) = con.execute("select tags from notes where id = 1001").fetchone()
        finally:
            con.close()
        check("copy carries the tag", tags.strip(), TAG_PREFIX + "system::skin")

        reread, _, _ = read_notes(str(apkg_path))
        check("source still has zero tags", [n["existing_tags"] for n in reread].count([]), 8)
        check("provenance sha matches", prov["sha256"], sha_before)
    finally:
        shutil.rmtree(str(root), ignore_errors=True)

    if failures:
        print("SELF-TEST FAILED ({} problem(s)):".format(len(failures)))
        for line in failures:
            print("  - " + line)
        return EXIT_SELFTEST
    print("SELF-TEST PASSED: matching, confidence policy and read-only guarantee.")
    return EXIT_OK


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        prog="tag_deck.py",
        description="Propose USMLE-outline tags for an Anki deck. Never writes to the deck.",
    )
    parser.add_argument("apkg", nargs="?", help="path to the .apkg file")
    parser.add_argument(
        "--outline",
        type=Path,
        default=here.parent / "outline" / "outline.json",
        help="path to outline.json (default: speedrun-analysis/outline/outline.json)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=here / "out",
        help="directory for tag_proposals.json and tag_report.txt",
    )
    parser.add_argument(
        "--min-confidence",
        choices=("high", "medium"),
        default="high",
        help="lowest confidence that becomes a proposed tag (default: high)",
    )
    parser.add_argument(
        "--emit-collection",
        type=Path,
        default=None,
        help="write a THROWAWAY COPY of the collection with the proposals stamped "
        "on, for coverage.py to read. The source .apkg is not touched.",
    )
    parser.add_argument("--quiet", action="store_true", help="do not print the report")
    parser.add_argument(
        "--self-test", action="store_true", help="run the built-in fixture checks"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.apkg:
        parser.print_usage(sys.stderr)
        sys.stderr.write("tag_deck.py: an .apkg path is required (or --self-test)\n")
        return EXIT_USAGE
    if not os.path.isfile(args.apkg):
        sys.stderr.write("not a file: {}\n".format(args.apkg))
        return EXIT_INPUT

    try:
        topics, outline_sha = load_outline(args.outline)
        index = build_index(topics)
        notes, provenance, member = read_notes(args.apkg)
    except TaggerError as exc:
        sys.stderr.write(str(exc) + "\n")
        return EXIT_INPUT

    results = analyse(notes, index, args.min_confidence)
    summary = summarise(results, topics, index)

    report = {
        "what_this_is": (
            "PROPOSED speedrun::topic:: tags for an Anki deck, matched against "
            "the published USMLE outline. Nothing has been applied to any "
            "collection; applying is a separate explicit step."
        ),
        "generated_utc": import_deck.utc(time.time()),
        "deck": provenance,
        "collection_member": member,
        "outline": {"path": str(args.outline.resolve()), "sha256": outline_sha},
        "source_unchanged": True,
        "config": {
            "index_entries": len(index.postings),
            "dropped_generic": index.dropped_generic,
            "dropped_common": index.dropped_common,
            "max_doc_frequency": MAX_DOC_FREQUENCY,
            "base_weight": BASE_WEIGHT,
            "idf_factor": {str(k): v for k, v in IDF_FACTOR.items()},
            "lca_factor": LCA_FACTOR,
            "min_lca_level": MIN_LCA_LEVEL,
            "medium_min": MEDIUM_MIN,
            "max_tags_per_note": MAX_TAGS_PER_NOTE,
            "min_confidence": args.min_confidence,
            "organism_aliases": len(ORGANISM_ALIASES),
        },
        "known_limitations": KNOWN_LIMITATIONS,
        "summary": summary,
        "notes": results,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "tag_proposals.json"
    text_path = args.out_dir / "tag_report.txt"
    text = render(report, results, index)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")

    if args.emit_collection is not None:
        try:
            extract_collection_copy(args.apkg, args.emit_collection)
            stamp_tags(
                args.emit_collection,
                {r["note_id"]: r["proposed_tags"] for r in results},
            )
        except TaggerError as exc:
            sys.stderr.write(str(exc) + "\n")
            return EXIT_MUTATED

    if import_deck.sha256_of(args.apkg) != provenance["sha256"]:
        sys.stderr.write("the source .apkg changed during this run; refusing to report\n")
        return EXIT_MUTATED

    if not args.quiet:
        print(text)
    print("wrote {}".format(json_path))
    print("wrote {}".format(text_path))
    if args.emit_collection is not None:
        print("wrote {} (throwaway tagged COPY, for coverage.py)".format(args.emit_collection))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
