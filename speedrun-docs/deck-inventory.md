# Deck inventory: Manozzita_Microbiology_USMLE_Step_1.apkg

**Status: COMPLETE for the shipped artifact.** Every count below was read out of the actual file, not estimated. Fields marked UNKNOWN are things I tried to establish and could not; the reason is given each time.

**This file is third-party content. It is NOT committed to this repository, and it must not be.** See [Redistribution status](#redistribution-status).

---

## How to reproduce these numbers

```
python3 speedrun-analysis/deck/import_deck.py \
    ~/Downloads/Manozzita_Microbiology_USMLE_Step_1.apkg
```

That command reproduces the [Provenance](#provenance), [Package structure](#package-structure) and
[What is actually in the deck](#what-is-actually-in-the-deck) figures. It does **not** emit the
[Content shape](#content-shape) statistics; those were derived separately and their method is
stated in that section.

Add `--json` for machine-readable output. The script is standard library only (verified on Python 3.9.7 and on the repo's own 3.13.13 at `out/pyenv/bin/python`). It opens the package read-only, unpacks the inner SQLite collection into a temp directory that it deletes on exit, opens every database handle with `mode=ro`, and hashes the source `.apkg` before and after the run to prove it did not modify the user's file. That check passed: `source .apkg unchanged by this run: True`.

---

## Provenance

| Field      | Value                                                                                      |
| ---------- | ------------------------------------------------------------------------------------------ |
| Filename   | `Manozzita_Microbiology_USMLE_Step_1.apkg`                                                 |
| Local path | `/Users/hankholcomb/Downloads/Manozzita_Microbiology_USMLE_Step_1.apkg` (outside the repo) |
| Size       | 96,624 bytes                                                                               |
| SHA-256    | `5b99672b855b8ae6cf9b6b4e8dbdae7fb675adb910c6c4c3c35cec04c97e5d02`                         |
| Origin     | AnkiWeb shared deck **ID 1030312320** — <https://ankiweb.net/shared/info/1030312320>       |
| Downloaded | 2026-07-31T16:36:44Z, via Google Chrome                                                    |

The origin is not a guess. macOS recorded it in the file's extended attributes at download time:

```
$ mdls -name kMDItemWhereFroms Manozzita_Microbiology_USMLE_Step_1.apkg
kMDItemWhereFroms = (
    "https://ankiweb.net/svc/shared/download-deck/1030312320?t=<signed token, redacted>",
    "https://ankiweb.net/shared/info/1030312320"
)
$ xattr -p com.apple.quarantine Manozzita_Microbiology_USMLE_Step_1.apkg
0081;6a6ccf23;Chrome;...
```

`0x6a6ccf23` = 1785515811 = 2026-07-31T16:36:51Z (quarantine stamp); the signed download token carried `iat: 1785515804` = 2026-07-31T16:36:44Z. The token itself is deliberately not recorded here — it is a credential.

**UNKNOWN: the AnkiWeb listing's own title, author name, description, and download count.** `https://ankiweb.net/shared/info/1030312320` is a client-rendered SvelteKit page; fetching it returns only the app shell (`<noscript>JavaScript is required.</noscript>`), and the `/svc/shared/*` JSON endpoints did not answer unauthenticated GET or POST probes. Accessed 2026-08-02.

**Author, inferred but NOT confirmed.** Two independent signals point the same way, and neither is proof:

- The filename's `Manozzita` matches a public handle belonging to Manoela Medeiros (@manozzita), described in public profiles as a Brazilian physician studying for the USMLE in the United States — <https://www.famousbirthdays.com/people/manozzita.html>, <https://www.instagram.com/manozzita/> (accessed 2026-08-02).
- The collection's own metadata is in Portuguese while every card is in English: the notetype is `Básico`, its fields are `Frente`/`Verso`, and its template is `Cartão 1`. That is what Anki produces when a Portuguese-locale install creates a Basic note type. Consistent with a Brazilian author writing English USMLE material.

Correlation, not attribution. Treat authorship as UNCONFIRMED until the listing page is read in a real browser.

---

## Licence status

**UNKNOWN in the specific — the deck carries no licence text of its own.** I checked: the deck description is the empty string, the `Default` deck description is the empty string, there are no licence notes in any of the 156 notes, and the package contains no README or LICENSE member (its four zip entries are listed below).

What _is_ known is the platform default. AnkiWeb's Terms and Conditions (<https://ankiweb.net/account/terms>) set a Shared Deck License under which a downloader receives a permanent, worldwide, royalty-free, non-exclusive licence to use the material **in their personal studies only**, with redistribution, re-upload, and republication prohibited without the copyright holder's explicit permission; AnkiWeb also states shared decks are third-party material that it does not review.

**Caveat on that citation:** the terms page is JS-rendered and I could not fetch its body directly (accessed 2026-08-02). The summary above comes from search-engine extraction of that page, not from my own read of the HTML. Before relying on the exact wording, open the page in a browser.

The practical consequence is unambiguous either way, and it is the conservative reading: personal study, no redistribution.

---

## Redistribution status

- The `.apkg` lives in `~/Downloads`, outside the repository tree.
- The `.gitignore` exclusions still hold, verified by `git check-ignore -v` rather than by reading the file: `*.anki2` (line 31), `*.apkg` (line 41), `*.colpkg` (line 42). A probe path under `speedrun-analysis/` with each extension is correctly matched and ignored.
- One honest correction. `git ls-files` is _not_ empty of these extensions — nine files match:

  ```
  pylib/tests/support/anki2-alpha.anki2
  pylib/tests/support/diffmodels2-{1,2}.apkg
  pylib/tests/support/diffmodeltemplates-{1,2}.apkg
  pylib/tests/support/{media,update1,update2}.apkg
  rslib/tests/support/mediacheck.anki2
  ```

  All nine are upstream Anki's own test fixtures, committed upstream and inherited by this fork. None is Speedrun content and none is user data. The relevant claim — that no user deck is tracked — holds: `git status` stages nothing with these extensions, and no Speedrun tree contains one.
- Nothing in `speedrun-analysis/` or `speedrun-docs/` embeds the card content. This document quotes five cards as a sample for verification; that is fair-use-scale excerpting, not redistribution of the deck.

Anyone reproducing this work must download the deck themselves from the AnkiWeb link above.

---

## Package structure

Anki package format **version 2** (read from the `meta` protobuf: field 1 = 2). The inner collection is plain SQLite that the zip itself deflates, so the standard library reads it directly. **No zstd fallback was needed.** (Format v3 would store `collection.anki21b` as a raw zstd stream, which stdlib cannot decode before Python 3.14; `import_deck.py` detects that case, refuses to guess, and prints the pylib-based fallback instead of failing silently.)

| Zip member          | Uncompressed | Stored   |
| ------------------- | ------------ | -------- |
| `meta`              | 2 B          | 2 B      |
| `collection.anki21` | 249,856 B    | 45,010 B |
| `collection.anki2`  | 51,200 B     | 51,200 B |
| `media`             | 2 B          | 2 B      |

`media` is the two-byte JSON literal `{}` — **zero media files**. Confirmed independently at the card level: 0 of 156 notes contain a `[sound:…]`, `<img`, or `[anki:…]` reference. The deck is pure text.

`collection.anki2` is not deck content. It is Anki's backwards-compatibility stub, holding one note reading _"Please update to the latest Anki version, then import the .colpkg/.apkg file again."_ The script reports it separately and labels it as a stub so its single note is never mistaken for real data. **All figures below come from `collection.anki21`.**

---

## What is actually in the deck

Schema version 11.

| Measure                  | Value                                                   |
| ------------------------ | ------------------------------------------------------- |
| Notes                    | **156**                                                 |
| Cards                    | **156** (1:1 — single template, no reverses, no clozes) |
| Notetypes in use         | **1**                                                   |
| Decks                    | **1** (`Microbiology`)                                  |
| Distinct tags            | **0**                                                   |
| Review-log entries       | **0**                                                   |
| Media files              | **0**                                                   |
| Collection created       | 2023-09-25T07:00:00Z                                    |
| Collection last modified | 2025-11-24T17:51:38Z                                    |
| First note authored      | 2025-11-13T13:32:50Z                                    |
| Last note authored       | 2025-11-24T02:28:22Z                                    |

The 156 notes were written over an 11-day stretch in November 2025.

### Notetype

One notetype, used by all 156 notes:

| Property        | Value                                  |
| --------------- | -------------------------------------- |
| Name            | `Básico`                               |
| ID              | 1695666701902                          |
| Kind            | standard (not cloze)                   |
| Fields          | `Frente`, `Verso`                      |
| Templates       | `Cartão 1`                             |
| Question format | `{{Frente}}`                           |
| Answer format   | `{{FrontSide}}<hr id=answer>{{Verso}}` |

A stock Basic note type from a Portuguese-locale Anki, unmodified apart from a 126-byte CSS block. Field names are Portuguese; all card content is English.

### Decks

| Deck           | ID            | Cards                                  |
| -------------- | ------------- | -------------------------------------- |
| `Microbiology` | 1763040622709 | 156                                    |
| `Default`      | 1             | 0 (empty, ships with every collection) |

No subdecks.

### Tag vocabulary

**There are no tags. Zero distinct tags across the whole deck; all 156 of 156 notes are untagged.** The collection-level tag registry (`col.tags`) is the empty JSON object `{}`, and every row of `notes.tags` is empty.

This is a real finding, not a gap in the tooling — the script prints a per-tag note count table and that table came back empty. Any downstream design that assumed this deck carries topic tags, a `#AK_Step1` style hierarchy, or First Aid section tags needs to be revisited: **the only structural signal available in this deck is deck membership (one deck) and the card text itself.**

### Card states

All **156 cards are `new`** (`type = 0`, `queue = 0`), and `revlog` is empty.

Worth being blunt about: **this file contains no personal review history.** It is a clean download of a published deck, not a snapshot of a studied collection. It cannot support any analysis of the user's actual scheduling, retention, FSRS parameters, or difficulty — there is nothing in it to analyse. If review history is needed, a `.colpkg` export of the live collection is required instead.

### Content shape

**These seven rows are the one part of this document `import_deck.py` does NOT emit.** The script
reports the inventory above; it computes no character statistics. The figures below were derived by
a separate ad-hoc pass over `collection.anki21`, so the exact definition of "plain-text chars"
matters and is stated here:

> Per field: delete every `<...>` tag with the regular expression `<[^>]+>`, then `html.unescape`
> the result, then replace U+00A0 (`&nbsp;`) with an ordinary space, then trim leading and trailing
> whitespace. Interior whitespace is **not** collapsed. Length is counted in Unicode code points,
> so one emoji counts as one character.

| Measure                                      | Value         |
| -------------------------------------------- | ------------- |
| Notes containing HTML markup                 | 155 of 156    |
| Notes containing emoji / symbol characters   | 85 of 156     |
| Front, plain-text chars (min / median / max) | 11 / 57 / 157 |
| Back, plain-text chars (min / median / max)  | 9 / 136 / 705 |
| Total plain-text characters (front + back)   | 36,038        |
| Fronts phrased as a question (ending `?`)    | 140 of 156    |
| Empty fields                                 | 0             |

**Correction, 2026-08-02.** Two of these numbers were wrong in the first version of this document:
the back-field maximum read 717 and the total read 36,127. Re-deriving them showed those two came
from a different normalization than the other five rows — 717 is the back maximum when HTML
entities are left un-unescaped (so `&nbsp;` counts as six characters), and under that same rule the
front median is 58 and the total is 36,309, neither of which was what the document reported. A
sweep of 64 combinations of {unescape or not} x {tag deleted or replaced by a space} x {`<br>` to
newline or not} x {collapse whitespace or not} x {trim or not} x {NBSP to space or not} produced no
single pipeline yielding 157 / 717 / 36,127 together. The table above is now one consistent
pipeline, the one defined in the block above, and every row was re-derived under it.

Cards are HTML-formatted `<ul>`/`<li>` lists with `<strong>` emphasis and emoji section markers (🧠 "In simple terms", 🧪 "In precise terms", 💡 "Mnemonic"). Fronts are short questions; backs are multi-bullet answers. Subject matter is bacteriology — Gram staining, catalase/coagulase/novobiocin differentiation, _Staphylococcus_, _Streptococcus_, _Enterococcus_ — with heavy mnemonic use.

Two defects found in the source deck, both minor and both in the original:

- One duplicated front: _"Which bacteria are beta-hemolytic?"_ appears on 2 notes.
- One truncated front: _"hat is an easy mnemonic to remember Enterococcus diseases?"_ is missing its leading `W`.

### Sample of 5 notes

Copied verbatim out of `import_deck.py --json --width 200`, so the raw HTML is visible rather than rendered away. Note IDs are Anki's creation timestamps in milliseconds. Whitespace is collapsed and long fields are truncated with the dropped character count shown.

```
[1]  note 1763040770514   created 2025-11-13T13:32:50Z   notetype Básico   tags: (none)
     Frente: How do you differentiate <strong>Staphylococcus</strong> from <strong>Streptococcus</strong> using the <strong>catalase test</strong>?
     Verso: <ul><li><div><strong>Catalase-positive → Staphylococcus</strong> 🟡</div> </li> <li> <div><strong>Catalase-negative → Streptococcus / Enterococcus</strong> 🔵<br> 💡 <strong>Mnemonic:</strong> <em>“Strep ... [+57 chars]

[2]  note 1763040840194   created 2025-11-13T13:34:00Z   notetype Básico   tags: (none)
     Frente: How do you distinguish between <strong>Staphylococcus aureus</strong> and other Staph species?
     Verso: <div>🧠 <strong>In simple terms:</strong> Only <strong>S. aureus</strong> makes clots.<br> 🧪 <strong>In precise terms:</strong></div> <ul> <li> <div><strong>Coagulase-positive → S. aureus</strong> (mos ... [+114 chars]

[3]  note 1763040914684   created 2025-11-13T13:35:14Z   notetype Básico   tags: (none)
     Frente: How do you differentiate <strong>coagulase-negative Staphylococcus</strong> species using <strong>Novobiocin</strong>?
     Verso: <div>🧠 <strong>In simple terms:</strong> One lives on your skin, the other in your urinary tract — and the skin one is <em>sensitive</em> (easily killed).<br> 🧪 <strong>In precise terms:</strong></div ... [+421 chars]

[4]  note 1763040967649   created 2025-11-13T13:36:07Z   notetype Básico   tags: (none)
     Frente: What are the key structural features of <strong>Gram-positive bacteria</strong>?
     Verso: <ul><li><div><strong>Stain:</strong> Purple (P → Positive → Purple)</div> </li> <li> <div><strong>Wall:</strong> <strong>Thick peptidoglycan (murein)</strong></div> </li> <li> <div><strong>Teichoic ac ... [+309 chars]

[5]  note 1763040983553   created 2025-11-13T13:36:23Z   notetype Básico   tags: (none)
     Frente: What are the key structural features of <strong>Gram-negative bacteria</strong>?
     Verso: <ul><li><div><strong>Stain:</strong> Pink (N in piNk → Negative)</div> </li> <li> <div><strong>Wall:</strong> <strong>Thin peptidoglycan</strong></div> </li> <li> <div><strong>Outer membrane</strong>  ... [+306 chars]
```

---

## Everything still UNKNOWN

| Question                                           | Status            | Why                                                                                                                              |
| -------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| AnkiWeb listing title, description, download count | UNKNOWN           | Listing page is JS-rendered; `/svc/shared/*` endpoints did not answer unauthenticated probes (2026-08-02). Needs a real browser. |
| Author identity                                    | UNCONFIRMED       | Filename handle plus Portuguese-locale metadata both point at Manoela Medeiros (@manozzita). Circumstantial.                     |
| Deck-specific licence                              | NONE FOUND        | No licence text in the package, deck descriptions, or any note. Platform default applies.                                        |
| Exact wording of AnkiWeb's Shared Deck License     | PARTIALLY SOURCED | Terms page body could not be fetched directly; summary is search-engine extraction of <https://ankiweb.net/account/terms>.       |
| Whether the deck has been updated since download   | UNKNOWN           | Not checked. Local copy is pinned by the SHA-256 above.                                                                          |

---

## Sources

- <https://ankiweb.net/shared/info/1030312320> — origin listing (from the file's own download metadata; page body not retrievable, accessed 2026-08-02)
- <https://ankiweb.net/account/terms> — AnkiWeb Terms and Conditions / Shared Deck License (accessed 2026-08-02, body not directly retrievable)
- <https://www.famousbirthdays.com/people/manozzita.html> — public profile for the `manozzita` handle (accessed 2026-08-02)
- <https://www.instagram.com/manozzita/> — public profile for the `manozzita` handle (accessed 2026-08-02)
