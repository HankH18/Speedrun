# USMLE Step 1 content outline — provenance

`outline.json` in this directory is a machine-readable rendering of the **real, published**
USMLE Step 1 content outline and its two Step 1 weight tables (plus the discipline table).

Every percentage in `outline.json` was read off a live USMLE page or PDF on the access date
below. **No weight was estimated, interpolated, or invented.** Where USMLE publishes no figure,
`weight_low` / `weight_high` are `null` and `weight_source` is the literal string `"UNKNOWN"`.

**Access date: 2026-08-02.** All fetches returned HTTP 200; usmle.org did **not** block
automated fetching, and all three PDFs parsed.

---

## Sources

| # | Document                                            | URL                                                                                                                                                                                                                      | What it supplied                                           |
| - | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| A | Step 1 Content Outline & Specifications (HTML)      | Requested `https://www.usmle.org/prepare-your-exam/step-1-materials/step-1-content-outline-and-specifications` → 301 → `https://www.usmle.org/exam-resources/step-1-materials/step-1-content-outline-and-specifications` | **All three weight tables. Every percentage in the file.** |
| B | USMLE Content Outline (PDF, 42 pp.)                 | `https://www.usmle.org/sites/default/files/2022-01/USMLE_Content_Outline_0.pdf`                                                                                                                                          | Topic hierarchy only. **Contains no percentages.**         |
| C | USMLE Physician Tasks/Competencies (PDF, 10 pp.)    | `https://www.usmle.org/sites/default/files/2022-01/USMLE_Physician_Tasks_Competencies_2.pdf`                                                                                                                             | Competency hierarchy only. **Contains no percentages.**    |
| D | NBME/USMLE recategorization infographic (PDF, 1 p.) | `https://www.usmle.org/sites/default/files/2024-01/NBME_USMLE_Infographic_final.pdf`                                                                                                                                     | Corroborates the 18-section list. **No percentages.**      |

Document B self-identifies in its running footer as **"For Public Release: USMLE Content Outline
(2026)"**, copyright 2026; HTTP `Last-Modified: Tue, 16 Jun 2026 18:18:51 GMT`. Document C is
copyright 2025. Note that the `2022-01` path segment in the B and C URLs is a stale CMS directory
name, **not** the edition year.

Checksums of the exact bytes parsed:

```
3d793f7c80655e364ed4216dcc5b5e4d14e6331225d97ecdf6ccbcb372fb21a9  USMLE_Content_Outline_0.pdf
15ccc90db23dd37ee3121257a6c65640dff95e659aceab2d8553f9e2e83c27fd  USMLE_Physician_Tasks_Competencies_2.pdf
```

---

## The weights, exactly as published

The single most important fact about provenance here: **all three tables live on the HTML page
(source A). Neither PDF contains a single Step 1 percentage.** The PDFs supply structure; the page
supplies weights.

### Table 1 — Step 1 Content Specifications (source A)

Reproduced verbatim, including USMLE's own labels. In `outline.json` these are the 11 `axis:
"system"`, `level: 1` topics.

| System (verbatim label)                                 | Range, % |
| ------------------------------------------------------- | -------- |
| Human Development\*\*\*                                 | 1–3      |
| Blood & Lymphoreticular/Immune Systems                  | 9–13     |
| Behavioral Health & Nervous Systems/Special Senses      | 10–14    |
| Musculoskeletal, Skin & Subcutaneous Tissue             | 8–12     |
| Cardiovascular System                                   | 7–11     |
| Respiratory & Renal/Urinary Systems                     | 11–15    |
| Gastrointestinal System                                 | 6–10     |
| Reproductive & Endocrine Systems                        | 12–16    |
| Multisystem Processes & Disorders                       | 8–12     |
| Biostatistics & Epidemiology/Population Health          | 4–6      |
| Social Sciences: Communication and Interpersonal Skills | 6–9      |

USMLE footnotes, verbatim: `* Percentages are subject to change at any time.`
`** Foundational Science content is distributed throughout the organ systems based on disease
process/diagnosis.` `*** The Human Development topic includes Normal Age-Related Findings and Care
of the Well Patient. The remaining content that had been included in the General Principles
category has been distributed to other organ system categories based on disease process/diagnosis.`

Sanity check (not a USMLE figure, computed here): the low ends sum to 82 and the high ends to 121,
so the midpoints sum to ~101.5. Consistent with Table 1 being a genuine partition of the item pool.

### Table 2 — Step 1 Physician Tasks/Competencies Specifications (source A)

| Competency (verbatim label)                               | Range, %                 |
| --------------------------------------------------------- | ------------------------ |
| Medical Knowledge: Applying Foundational Science Concepts | 60–70                    |
| Patient Care: Diagnosis                                   | 20–25                    |
| — History/Physical Examination                            | **(cell empty on page)** |
| — Diagnosis                                               | **(cell empty on page)** |
| Communication and Interpersonal Skills                    | 6–9                      |
| Practice-based Learning & Improvement                     | 4–6                      |

Two things worth flagging:

1. The page renders `History/Physical Examination` and `Diagnosis` as **indented sub-rows of
   `Patient Care: Diagnosis` with literally empty percentage cells** (`<td>&nbsp;</td>` in the
   HTML). They are recorded as `null` / `UNKNOWN`. The 20–25% was **not** split between them.
2. The task brief for this work quoted the fourth row as _"Practice-based Learning:
   Evidence-Based Medicine 4-6%"_. The page's actual label is **"Practice-based Learning &
   Improvement"**, same 4–6%. `outline.json` records the page's wording, not the brief's.

### Table 3 — Step 1 Discipline Specifications (source A)

| Discipline                 | Range, % |
| -------------------------- | -------- |
| Pathology                  | 45–55    |
| Physiology                 | 30–40    |
| Nutrition                  | 15–20    |
| Gross Anatomy & Embryology | 10–20    |
| Microbiology               | 10–20    |
| Pharmacology               | 10–20    |
| Behavioral Sciences        | 10–15    |
| Biochemistry               | 5–15     |
| Histology & Cell Biology   | 5–15     |
| Immunology                 | 5–15     |
| Genetics                   | 5–10     |

These **do not sum to 100% and are not supposed to**. USMLE states verbatim: _"Step 1 test items
are deliberately designed to be integrative; many items are classified to more than one
discipline. Totals add up to greater than 100%."_ (Low ends sum to 150, high ends to 245.) Treating
this table as a partition would be wrong.

---

## What could NOT be extracted

This section is the point of the file. Read it before using any weight.

1. **There is no published weight below the 11 Table 1 groups.** USMLE publishes organ-system
   percentages only for those 11 combined groups. The content outline PDF's 18 sections, 147
   categories, and 176 topic bullets carry **no** percentages anywhere in any USMLE document.
   All 364 such nodes are `null` / `"UNKNOWN"`. Any per-topic weight you see elsewhere on the
   internet is somebody's estimate, not USMLE's.

2. **The Table 1 group → content-outline section mapping is inferred, not published.** Table 1 has
   11 rows; the content outline has 18 sections. USMLE nowhere states which sections compose which
   weighted group. The mapping in `outline.json` was deduced from the labels and is flagged
   per-group via `section_mapping_confidence`:

   - `exact_name_match` (4 groups: Human Development, Cardiovascular System, Gastrointestinal
     System, Multisystem Processes & Disorders) — the Table 1 label is character-identical to one
     content-outline section. These groups are collapsed with their section
     (`collapsed_with_content_outline_section: true`) and the weight is safe to use directly.
   - `inferred_by_name` (5 groups) — the group combines 2–4 sections, e.g. `Reproductive &
     Endocrine Systems` (12–16%) covers Pregnancy/Childbirth/Puerperium, Female and Transgender
     Reproductive System & Breast, Male and Transgender Reproductive System, and Endocrine System.
     **The 12–16% belongs to the group as a whole. It was not divided among the four sections**;
     dividing it would be a fabrication. Member sections are `null` / `"UNKNOWN"`.
   - `inferred_by_name_label_narrower_than_section` (2 groups) — a genuine ambiguity, not just a
     name mismatch. Table 1 says `Social Sciences: Communication and Interpersonal Skills` (6–9%),
     but the outline section `Social Sciences` also contains _Medical ethics and jurisprudence_,
     _Systems-based practice and patient safety_, and _Health care policy and economics_. It is
     **unknown** whether the 6–9% covers the whole section or only the communication part. Same
     issue for `Biostatistics & Epidemiology/Population Health` (4–6%) versus the section
     `Biostatistics, Epidemiology/Population Health, & Interpretation of the Medical Literature`.
     These two groups are **not** collapsed with their section.

3. **No sub-competency weights.** Table 2 weights 4 of the 7 competencies in source C. The other
   three — _Patient Care: Management_, _Professionalism, Including Legal and Ethical Issues_,
   _Systems-based Practice, Including Patient Safety_ — appear in `outline.json` with `null`
   weights and `on_step1_spec_table2: false`. Their absence from Table 2 is a fact about Table 2;
   it is not evidence that they are worth 0%. All 24 second-level competency items are `null`.

4. **No item counts, no scaled-score mapping, no difficulty data.** USMLE publishes ranges only.
   There is no way to convert these percentages into an expected number of questions on a given
   form, and nothing in this file attempts to.

5. **The percentages are explicitly volatile.** Every table carries `* Percentages are subject to
   change at any time.` The figures here are a snapshot of 2026-08-02 and should be re-fetched
   before being relied on.

6. **Content-outline examples are illustrative, not exhaustive.** Source B states: _"The examples
   listed within the outline are just examples. Questions may include diseases, symptoms, etc.,
   that are not included in the outline."_ The `examples` arrays in `outline.json` inherit that
   caveat and are deliberately not separate taggable topics.

---

## Schema

`outline.json` is a single object. `topics` is a flat array of 390 records; hierarchy is expressed
by `parent_id` and `path`, not by nesting. Top-level keys `sources`, `usmle_footnotes_verbatim`,
`schema`, `known_limitations`, and `counts` are self-describing and duplicate the provenance above
so the JSON stands alone.

Each topic record:

| Field                              | Meaning                                                                                                                                       |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                               | Dot-joined path, unique within the file.                                                                                                      |
| `name`                             | Human-readable label, verbatim from the source document.                                                                                      |
| `axis`                             | `system`, `task`, or `discipline` — three **independent** classifications of the same item pool. Never add weights across axes.               |
| `level`                            | 1 at the root of its axis; deeper integers nest.                                                                                              |
| `parent_id`                        | Parent's `id`, or `null` at an axis root.                                                                                                     |
| `path`                             | Ordered slug components.                                                                                                                      |
| `tag`                              | `speedrun::topic::` + `"::".join(path)` — ready to paste into Anki.                                                                           |
| `weight_low` / `weight_high`       | Integer ends of the published range, or **both `null`**.                                                                                      |
| `weight_source`                    | `step1_spec_page#table1_content_specifications`, `…#table2_physician_tasks_competencies`, `…#table3_discipline_specifications`, or `UNKNOWN`. |
| `weight_note`                      | Prose: what the weight means, or precisely why it is `null`.                                                                                  |
| `examples`                         | Verbatim illustrative strings from source B. Present on some topics only.                                                                     |
| `content_outline_pdf_page`         | 1-based page in source B where the topic appears.                                                                                             |
| `maps_to_content_outline_sections` | On Table 1 groups: the sections the group is believed to cover.                                                                               |
| `section_mapping_confidence`       | On Table 1 groups: see limitation 2 above.                                                                                                    |

Axis shapes:

- `system` — 348 topics. L1 = 11 Table 1 groups (weighted); L2 = content-outline section; L3 =
  category; L4 = topic bullet. L2 is absent where the group collapsed into its section.
- `task` — 31 topics. L1 = 7 competencies (4 weighted); L2 = 24 sub-competencies (all `null`).
- `discipline` — 11 topics, all weighted, all L1, non-exclusive.

Counts: **390 topics; 26 carry a published weight (11 + 4 + 11); 364 are `null` / `UNKNOWN`.**

### Tagging note

Tags are lowercased, non-alphanumerics collapse to `_`, and each component is capped at 48
characters (cut on a word boundary) so deep paths stay usable; the longest emitted tag is 208
characters. Collisions after truncation are disambiguated with a numeric suffix. `name` always
holds the full untruncated label — never reconstruct a topic name from its tag.

---

## Method, and how to re-verify

1. `curl` the page in source A and parse `<table>` elements out of the raw HTML. The three tables
   were read from raw markup rather than from a rendered summary, because a summarizing pass
   mis-paired several rows on the first attempt; the values above are the raw-HTML ones.
2. Download the three PDFs and extract text. No PDF library was available in this environment
   (`pdftotext`, `mutool`, `pypdf`, `PyMuPDF`, Quartz all absent), so extraction used a
   throwaway stdlib-only reader: `zlib`-inflate each `FlateDecode` content stream, tokenize the
   PDF operators, and track the text matrix so every run keeps its `(x, y)`.
3. Hierarchy comes from the x-coordinate, which is exactly regular in source B: heading `x=54`,
   bullet `x=72`, sub-bullet `x=108`, sub-sub-bullet `x=144`, with wrapped continuations at
   `+18`. Wrapped headings were rejoined; a heading was treated as one of the 18 sections only if
   the joined string matched a Table-of-Contents entry **exactly**.
4. Font-subset artifacts were mapped explicitly (`\x00±` → en dash, `\x00²` → em dash, `\x01.` →
   α). Real accented characters (Behçet, Ménière, müllerian, Sjögren) survive unchanged. The
   emitted JSON contains zero control characters.

Verified after generation: all 18 sections found in Table-of-Contents order; 0 unassigned lines;
0 duplicate ids; 0 duplicate tags; 0 dangling `parent_id`; 0 `tag`/`path` mismatches; 0 tags
containing whitespace or quotes; 0 records where a `null` weight carries a non-`UNKNOWN` source or
a non-`null` weight carries `UNKNOWN`.

The extraction tooling was intentionally not committed: it is single-use, depends on files fetched
over the network, and would rot. Re-running the steps above against the URLs and checksums listed
is the reproduction path.
