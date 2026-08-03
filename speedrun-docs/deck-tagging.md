# Tagging the microbiology deck against the USMLE outline

**Status: PROPOSED. Nothing in this document has been applied to any Anki
collection.** The source `.apkg` was opened read-only, its SHA-256 was taken
before and after every run, and the two match. Applying the tags is a separate,
explicit step that a human has to take; no code in this repo does it.

- Tagger: [`speedrun-analysis/deck/tag_deck.py`](../speedrun-analysis/deck/tag_deck.py)
- Outline: [`speedrun-analysis/outline/outline.json`](../speedrun-analysis/outline/outline.json)
- Coverage map: [`speedrun-analysis/outline/coverage.py`](../speedrun-analysis/outline/coverage.py)

## 1. Inputs, with hashes

|                        |                                                                                              |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| deck                   | `Manozzita_Microbiology_USMLE_Step_1.apkg`                                                   |
| deck sha256            | `5b99672b855b8ae6cf9b6b4e8dbdae7fb675adb910c6c4c3c35cec04c97e5d02`                           |
| collection member read | `collection.anki21` (the `collection.anki2` sibling is Anki's "please upgrade" stub)         |
| notes / cards          | 156 / 156                                                                                    |
| existing tags          | **zero** — the deck carries no tags at all                                                   |
| review log entries     | 0                                                                                            |
| outline                | `outline.json`, sha256 `652a29a832f0b73f3cf43e8d5422bf07d9b5c23e296c818cf6acbdb7370085bb`    |
| outline topics         | 390, of which **26 carry a published weight** and 364 are `weight_source: UNKNOWN` by design |

Reproduce:

```
python3 speedrun-analysis/deck/tag_deck.py <deck.apkg> \
    --emit-collection speedrun-analysis/deck/out/proposed_tags.anki2
python3 speedrun-analysis/outline/coverage.py \
    --collection speedrun-analysis/deck/out/proposed_tags.anki2
```

Outputs land in `speedrun-analysis/deck/out/`, which is **gitignored**: the
report and the JSON quote the note text of a third-party deck, so they are
regenerable artefacts, not repo content. `--emit-collection` writes a
throwaway _copy_ of the collection with the proposals stamped on, purely so
`coverage.py` has something to read. The user's package is never opened for
writing.

## 2. Method

The matching vocabulary is derived from `outline.json` itself — the outline's
own verbatim `examples` strings — not from a keyword list invented for this
task. Each examples string is taken apart the way the outline punctuates it,
and each fragment is classified STRONG or WEAK:

| outline punctuation | treated as                                               | why                                                                                                                                                                                                                          |
| ------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `( … )`, `[ … ]`    | **WEAK**                                                 | the outline puts causative organisms and "eg" lists in brackets. A card that names the bug is not thereby a card about that organ system's disorder.                                                                         |
| `;`, `/`, newline   | **STRONG**                                               | coordinate list items.                                                                                                                                                                                                       |
| `:`                 | **STRONG** both sides                                    | introduces a breakdown of the item before it.                                                                                                                                                                                |
| `,`                 | first part STRONG; a later part STRONG only if ≥ 2 words | the comma is genuinely ambiguous: `cellulitis, erysipelas, impetigo` is a list, `myositis, infective` and `otitis, externa, media` are index-style inversions. A lone trailing word is more often a modifier than a disease. |
| topic **names**     | **WEAK**                                                 | names are structural labels ("Infectious disorders", "Shock"), not mentions of an entity.                                                                                                                                    |

Fragments become index entries of four kinds:

- `phrase` — STRONG, multi-word (`staphylococcal scalded skin syndrome`). May **decide** a proposal.
- `term` — STRONG, single word (`osteomyelitis`). May decide a proposal, subject to the suffix rule below.
- `head` — the head noun of a STRONG phrase (`pneumonia` from `lobar pneumonia`). Corroborates only. Exception: if every discarded modifier was generic, nothing specific was lost, so `bacterial endocarditis` → `endocarditis` keeps full `term` strength.
- `weak` — everything ruled WEAK above. Corroborates only.

An entry used by more than 3 topics discriminates nothing and is dropped (51
entries); entries used by 2–3 topics are discounted (×0.5, ×0.3). 3078 entries
survive.

**The clinical-suffix rule.** A lone word may only decide a proposal if it
carries a clinical suffix (`-itis`, `-osis`, `-emia`, `-oma`, `-uria`,
`-pathy`, `-algia`, `-penia`, …). This was added after measuring the damage
without it: the words the outline and this deck use in _different senses_ —
`shock`, `colon`, `hemolysis`, `adherence`, `penicillins`, `transfers`,
`tricuspid`, `cough` — produced **38 wrong note/tag pairs** on this deck. The
rule is a net _reduction_ in tags and it has a real cost, stated in §5.

**Backing off instead of guessing.** When one fragment belongs to several
topics, the proposal moves to their lowest common ancestor rather than picking
a child — but only if that ancestor is at level ≥ 2, never a whole level-1 exam
section. `meningitis` therefore proposes _Nervous System & Special Senses_, not
a guess between its children.

**The one hand-written list** is 26 organism aliases: pure abbreviation
expansion (`S. aureus` → `Staphylococcus aureus`) so deck shorthand can be
found in outline spelling. It invents no clinical equivalences, ambiguous
abbreviations are deliberately absent (`GBS` is Group B _Streptococcus_ or
Guillain-Barré; `GAS` is Group A _Streptococcus_ or gas gangrene), and every
alias that fires is recorded in the evidence trail. Because organism names are
almost always bracketed in the outline, alias hits are WEAK evidence — they
corroborate, they never decide.

## 3. Confidence policy

|            | rule                                                                                                     | tagged? |
| ---------- | -------------------------------------------------------------------------------------------------------- | ------- |
| **HIGH**   | ≥ 1 `phrase` or `term` hit belonging to exactly one topic, or resolved to a common ancestor at level ≥ 2 | yes     |
| **MEDIUM** | score ≥ 0.9 but every hit is shared between unrelated topics, bracketed, or head-only                    | **no**  |
| **LOW**    | a trace of evidence below that                                                                           | **no**  |
| **NONE**   | nothing in the outline's vocabulary appears in the note                                                  | **no**  |

Only HIGH is proposed. Every MEDIUM/LOW note is printed in the report with its
best candidate and that candidate's evidence, so a human can adjudicate. **An
untagged note is honest; a wrongly tagged one silently corrupts the coverage
number, which is the only thing this pipeline exists to produce.** A note may
carry more than one tag (a card listing five _S. aureus_ diseases legitimately
hits five topics); when a parent and a child both qualify, only the child is
kept.

`tag_deck.py --self-test` builds a synthetic outline and a synthetic `.apkg`
and checks all of the above end to end, including that stamping a copy leaves
the source package byte-identical.

## 4. The real match rate

**Keyword matching confidently tags a minority of this deck: 46 of 156 notes,
29.5%.** That is the headline finding, and it is a fact about the deck and the
outline, not a bug in the script.

|                                | count         | of 156    |
| ------------------------------ | ------------- | --------- |
| notes tagged (HIGH)            | **46**        | **29.5%** |
| notes left UNTAGGED            | **110**       | **70.5%** |
| — best candidate MEDIUM        | 76            | 48.7%     |
| — best candidate LOW           | 14            | 9.0%      |
| — no evidence at all (NONE)    | 20            | 12.8%     |
| tags proposed                  | 70            | —         |
| distinct outline topics hit    | **19** of 390 | 4.9%      |
| topics hit including ancestors | 44 of 390     | 11.3%     |

**Why the majority is untagged, honestly:** this deck is mostly _basic-science_
microbiology — Gram stain architecture, catalase/coagulase/novobiocin lab
identification, exotoxin and endotoxin mechanism, plasmid/phage/transposon
genetics, the bacterial growth curve, normal flora, antibiotic targets and
resistance mechanisms. The USMLE content outline organises disease by **organ
system**, and gives none of that material any vocabulary to match against. A
card reading _"What are the key structural features of Gram-positive
bacteria?"_ has no outline topic to land on, and inventing one would be worse
than leaving it blank. The deck is also narrow in a second way: it is
Gram-positive cocci plus pharmacology. There is no card on HIV, hepatitis,
enteric pathogens, STIs, TB, fungi or parasites.

### Microbiology-relevant outline topics with NO card

"Microbiology-relevant" uses the **outline's own wording**, not our judgement:
topic name matches `\b(infectious|infections?|hiv)\b`. That selects **27
topics**; 16 have at least one proposed note (counting a parent as hit when a
child is hit), and **11 do not**:

| outline topic                                                                                 |                                       |
| --------------------------------------------------------------------------------------------- | ------------------------------------- |
| `…immune_system.hiv_aids`                                                                     | HIV/AIDS                              |
| `…blood_and_lymphoreticular_system.infectious_and_immunologic_including.infectious_disorders` | infectious disorders (blood)          |
| `…nervous_system_and_special_senses.infectious_immunologic_and_inflammatory`                  | and its `.infectious_disorders` child |
| `…disorders_of_the_eye_and_eyelid.infectious_and_inflammatory_disorders_of_the`               | eye/eyelid infection                  |
| `…renal_and_urinary_system.infectious_immunologic_and_inflammatory.infectious_disorders`      | UTI/pyelonephritis level              |
| `system.gastrointestinal_system.infectious_immunologic_and_inflammatory`                      | and its `.infectious_disorders` child |
| `…female_reproductive_system.infectious_immunologic_and_inflammatory`                         | STIs, vaginitis                       |
| `…male_and_transgender_reproductive_system.infectious_immunologic_and_inflammatory`           | and its `.infectious_disorders` child |

Two of these are _matcher_ misses rather than true gaps: the deck's meningitis
and cystitis cards resolved to the **parent** node (`Nervous System & Special
Senses`, `renal … infectious/immunologic/inflammatory`) because the deciding
word was shared, so the leaf below shows as uncovered. The rest — HIV, GI
infection, genital infection, eye infection — are real holes in this deck.

## 5. What the confidence policy costs

Being strict is not free, and the losses are specific:

- Entity names with no clinical suffix cannot decide: **gangrene, tetanus,
  botulism, impetigo, erysipelas, syphilis, pneumonia**. Notes resting on one
  of those alone fall to MEDIUM and go untagged.
- A lone word after a comma is read as a modifier, which is right for
  `myositis, infective` and wrong for `cellulitis, erysipelas, impetigo` —
  it demotes two real disease names.
- The outline itself contains truncated fragments. The bare `hospital-acquired`
  matched a card about hospital-acquired _pneumonia_ and proposed a
  musculoskeletal trauma topic — one visibly wrong tag out of 70, left in the
  output on purpose, with its deciding evidence printed, because that is what
  a review step is for.
- The outline states its examples are "just examples", so every topic's
  vocabulary is incomplete by construction. **Absence of a hit is weak evidence
  of absence of coverage.**

## 6. Coverage map against the proposed tagging

Real output of `coverage.py` against `proposed_tags.anki2` (156 cards, 70
carrying a tag, 19 distinct tags; **zero orphan tags** — every proposed tag is
a real outline topic).

**Unweightable topics: 364 of 390** publish no weight (`weight_source:
UNKNOWN`). They are excluded from every weighted figure, and are counted
neither as 0% nor as 100%. Under `exact` 19 of them are covered and 345 are
not; under `subtree`, 36 covered and 328 not. By axis: system 337 unweightable
of 348, task 27 of 31, discipline 0 of 11.

**Topic-count coverage (context only, not the headline):** exact 19/390 =
4.87%; subtree 44/390 = 11.28%.

**Weighted coverage, per axis, never summed across axes:**

| axis       | mode            | weighted topics covered | covered share (exact published range) |
| ---------- | --------------- | ----------------------- | ------------------------------------- |
| system     | exact           | 0 of 11                 | 0.00% – 0.00%                         |
| system     | **subtree**     | **8 of 11**             | **79.78% – 90.35%**                   |
| task       | exact / subtree | 0 of 4                  | 0.00%                                 |
| discipline | exact / subtree | 0 of 11                 | 0.00%                                 |

### Read that 79.78–90.35% correctly

It is **not** "this deck covers 80–90% of Step 1." Every published weight in
this outline sits at an axis root, so `subtree` asks only: _does at least one
card land anywhere inside this organ-system group?_ Eight of the eleven
weighted system groups get a single "yes", and those eight happen to carry
71–103 of the 82–121 published percentage points. It is a **breadth-touched**
measure at the coarsest possible grain. The three groups with nothing at all
are Human Development (1–3%), Biostatistics & Epidemiology (4–6%) and Social
Sciences: Communication (6–9%) — which is exactly what you would expect of a
microbiology deck.

The `exact` row is 0.00% for the honest reason that no card is tagged at an
axis root, which is where the weights live. Neither number alone is the deck's
"coverage"; both are printed, and they are never blended.

### The discipline axis reads 0% and that is a limitation, not a finding

All 11 discipline topics (Pathology, Physiology, **Microbiology**, Pharmacology,
Immunology, …) carry a one-word name and **no `examples` at all** in
`outline.json`. There is no vocabulary to match against, so the matcher
proposes zero discipline tags and `coverage.py` reports the whole axis —
including Microbiology, weighted 10–20% — as uncovered.

This is plainly wrong as a statement about a microbiology deck. It is stated
here rather than papered over: assigning `discipline::microbiology` would have
required a keyword rule invented by us, with no basis in the published outline,
and the project rule is that an absent deliverable beats a fabricated one. The
same applies to the task axis, whose topics describe physician _tasks_ and have
no disease vocabulary either.

## 7. What has to happen before these tags mean anything

1. A human reviews `tag_report.txt` — every proposal prints the exact phrase
   that decided it and where that phrase came from.
2. The 76 MEDIUM notes are adjudicated by hand. Many are correct matches the
   policy deliberately refused (the impetigo, tetanus and botulism cards among
   them).
3. Only then does anyone write tags into a collection. There is still no code
   in this repo that does that, and the user's `.apkg` remains untouched.
