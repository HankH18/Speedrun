# Licence provenance for speedrun source documents

**Retrieval date for everything in this directory: 2026-08-03 (UTC).**
Repository licence: **AGPL-3.0-or-later**. Every source admitted here must be compatible with
that, and must not carry terms forbidding the use we make of it.

This file records:

1. why **OpenStax was rejected**, on **two independent grounds**, with the AI clause quoted verbatim;
2. the **stale-footer trap** that makes licence checking treacherous;
3. the **two-gate check** that is now a permanent convention for this project;
4. **every article vetted**, with its gate results — accepted and rejected alike.

The tool that performs the check is
[`vet_source.py`](vet_source.py) (stdlib only, `--self-test` runs 40 offline assertions).
It exits non-zero if either gate fails, so it can be used as a hard gate in a pipeline.

---

## 1. Why OpenStax was rejected — both reasons

OpenStax is the obvious first stop for free medical text. It fails here twice, and either failure
alone is disqualifying.

### Reason (a): the licence is CC BY-NC-SA 4.0, not CC BY 4.0

Verified live on 2026-08-03 against OpenStax's own CMS API (`https://openstax.org/apps/cms/api/books/<slug>`),
which is the machine-readable form of the per-book licence shown on the book page:

| Book                      | `license_name` (verbatim)                                       | `license_version` | `license_url`                                        |
| ------------------------- | --------------------------------------------------------------- | ----------------- | ---------------------------------------------------- |
| Anatomy and Physiology 2e | `Creative Commons Attribution-NonCommercial-ShareAlike License` | `4.0`             | `https://creativecommons.org/licenses/by-nc-sa/4.0/` |
| Microbiology              | `Creative Commons Attribution-NonCommercial-ShareAlike License` | `4.0`             | `https://creativecommons.org/licenses/by-nc-sa/4.0/` |

Both terms are fatal for us:

- **NC (NonCommercial)** — AGPL-3.0-or-later grants recipients the right to use and convey the work
  commercially. A file inside an AGPL repository that may not be used commercially cannot be
  distributed under the repository's own licence. The two are incompatible.
- **SA (ShareAlike)** — CC BY-NC-SA requires derivatives be licensed under CC BY-NC-SA. That is not
  AGPL-3.0-or-later, and CC BY-NC-SA 4.0 lists no compatible licences. Also incompatible.

### Reason (b): an explicit prohibition on LLM training

Fetched live on 2026-08-03 from `https://openstax.org/books/microbiology/pages/preface` and
`https://openstax.org/books/anatomy-and-physiology-2e/pages/preface`. Both pages carry, in the
"Citation/Attribution" block, this sentence **verbatim**:

> This book may not be used in the training of large language models or otherwise be ingested into
> large language models or generative AI offerings without OpenStax's permission.

That prohibits our use case outright. It would still prohibit it if the licence were CC BY 4.0.
**This is why the check has a second gate: a licence audit alone would have missed it.**

---

## 2. The stale-footer trap

**Rule: never take a licence from a site-wide footer, a catalogue entry, a third-party OER index,
or a "similar articles" sidebar. Read the work's own licence statement.** A site footer describes
the site's default, is maintained separately from the per-work metadata, and drifts.

### What the live evidence actually shows — read this, it is not what you may expect

The trap was described to this task as: _openstax.org's site-wide footer still says CC BY 4.0 while
the per-book licence is CC BY-NC-SA._ **That does not reproduce as of 2026-08-03.** The live
footer, fetched from `https://openstax.org/apps/cms/api/footer/`, reads verbatim:

> © 1999-2026, Rice University. Except where otherwise noted, textbooks on this site are licensed
> under a Creative Commons Attribution-NonCommerical-ShareAlike 4.0 International License.

So today the footer **agrees** with the per-book licence. Whatever it said historically, it now says
CC BY-NC-SA. This is recorded rather than repeated as fact because inventing a citation would be
worse than reporting an inconvenient result. **The lesson survives regardless — the footer is a
separately-maintained string, which is precisely why it must never be the source of truth.**

Two things are worth keeping from that live fetch:

1. **The footer misspells the licence** — `NonCommerical` (sic), not `NonCommercial`. The first
   version of the prose licence detector in `vet_source.py` required the correct spelling and
   therefore matched only the leading `Creative Commons Attribution`, silently reporting the
   OpenStax footer as **plain CC BY**. That is the stale-footer failure mode manufactured by a
   typo. The detector now uses the loose stem `Non[\s-]?Commer\w*`, and a self-test asserts that
   the misspelt string is still read as `by-nc-sa`.
2. Because the footer says _"Except where otherwise noted"_, it was never authoritative for any
   individual book even when it was correct.

### The trap did reproduce — on a different work

See **PMC11601064** in §4. Its PMC machine-readable licence field says CC BY 4.0, while the
publisher's own site (`jornaldepneumologia.com.br`) carries a site-wide
`<a rel="license" href="http://creativecommons.org/licenses/by-nc/4.0/">` banner. Two statements,
two different licences, one work. The gate refused it and it was **not** committed. This is a live,
reproducible instance of exactly the failure mode OpenStax illustrates.

---

## 3. The two-gate check — permanent convention

**No document enters `speedrun-analysis/sources/` unless it passes both gates. Both gates are run
by `vet_source.py`, which exits non-zero on any failure.**

### Gate A — LICENCE

Requires an **explicit, machine-readable Creative Commons licence field** whose URI normalises to
exactly `creativecommons.org/licenses/by/4.0`.

Rejected, with the reason recorded:

| Rejected                                        | Why                                                                                 |
| ----------------------------------------------- | ----------------------------------------------------------------------------------- |
| CC BY-NC, CC BY-NC-SA, CC BY-NC-ND              | NonCommercial is incompatible with AGPL-3.0-or-later                                |
| any `-SA`                                       | ShareAlike is incompatible with AGPL-3.0-or-later                                   |
| any `-ND`                                       | NoDerivatives forbids the transformation into flashcards                            |
| CC BY **3.0** (or any version ≠ 4.0)            | Different terms; not the licence we vetted                                          |
| CC0 / public-domain dedication alone            | Rejected as unclear: a waiver leaves attribution and third-party-rights status open |
| prose licence text with no machine-readable URI | Not verifiable at scale; prose is not a licence field                               |
| no `<license>` element at all                   | There is nothing to check                                                           |

Gate A also runs the **stale-footer cross-check**: every CC licence stated on the article's landing
page — as a URI _and_ in prose — is compared against the machine-readable field. Any disagreement
**fails the gate**. The gate never picks the more convenient of two conflicting statements.

### Gate B — AI / LLM / TEXT-MINING TERMS

The landing page is fetched and scanned for prohibitions on AI training, LLM ingestion, generative
AI use, or text-and-data mining. Matches are classified:

- **PROHIBITION** — an AI/TDM term within ±320 characters of a permission-shaped restriction
  (`may not be used`, `is prohibited`, `without … permission`, `expressly reserves`, `opt out`, …).
  **Fails the gate.** The matched text is reported verbatim.
- **REVIEW** — a weaker signal (`all rights reserved`, `restricted`, `terms of use`). Reported
  verbatim, does **not** auto-fail; deliberately, so that ordinary biomedical prose
  ("fetal growth _restriction_") does not block a clean article. A human decides.
- **incidental mention** — an AI word with no restrictive context, e.g. a paper that merely
  _applies_ machine learning. Listed, never a failure.

A page that cannot be fetched is recorded as **UNKNOWN**, never as a pass. If the _required_ page
(PMC) cannot be fetched, the gate fails.

### Honest limits of the check — do not over-read a PASS

1. Gate B is a heuristic over one or two HTML pages. It does not read linked PDFs, separate Terms
   of Service pages, click-through agreements, `robots.txt`, or `ai.txt`. **A PASS means "no
   prohibition was found on the pages fetched", not "no prohibition exists."**
2. **Publisher-site terms could not be checked for five of the ten accepted articles.** MDPI
   (`www.mdpi.com`) and Wiley (`onlinelibrary.wiley.com`) return **HTTP 403 to automated requests**,
   including for `https://www.mdpi.com/about/terms` and `https://www.mdpi.com/robots.txt`. Those
   are marked UNKNOWN per article in §4. What we rely on for those articles is the CC BY 4.0 grant
   attached to the article itself, and the fact that the text was obtained from the **PMC Open
   Access Subset**, not from the publisher's website.
3. The PMC OA web service reports a coarse, **unversioned** licence string (`CC BY`). It cannot
   distinguish 4.0 from 3.0 and is recorded only for cross-checking. The versioned URI in the JATS
   `<license>` element is authoritative — see PMC10652663 in §4, which the OA service calls
   `CC BY` but which is CC BY **3.0**.
4. Gate A checks the _article's_ licence. Third-party material inside an article (figures reused
   under a different licence) is explicitly excluded from several of the CC BY grants below — see
   the Springer wording in §4. Figures were dropped during extraction; captions were kept.

---

## 4. Every article vetted

### Organ system selected

`outline.json` node **`system.respiratory_and_renal_urinary_systems.respiratory_system`**
("Respiratory System"), inside the Table 1 weighted group **`Respiratory & Renal/Urinary Systems`,
11–15 %** — the largest single organ-system band in the Step 1 content specifications. Sources
target its infectious category and both leaf topics:

| Outline id                                                                           | Name                                                                                                     |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `…respiratory_system.infectious_immunologic_and_inflammatory`                        | Infectious, immunologic, and inflammatory disorders, including microbiologic and host response to insult |
| `…infectious_immunologic_and_inflammatory.infectious_immunologic_and_inflammatory`   | infectious, immunologic, and inflammatory disorders of the **upper airways**                             |
| `…infectious_immunologic_and_inflammatory.infectious_immunologic_and_inflammatory_2` | infectious, immunologic, and inflammatory disorders of the **lower airways**                             |

This is the micro-heavy choice the brief asked for: it also feeds the Table 3 discipline
`discipline.microbiology` (10–20 %). Organism coverage was chosen against the outline's own
verbatim example strings for those nodes (_Streptococcus pneumoniae_, _Mycoplasma_, _Legionella_,
_Klebsiella_, MRSA, _Bordetella pertussis_, pulmonary tuberculosis, influenza A/B, RSV,
parainfluenza, aspergillosis, histoplasmosis, coccidioidomycosis, _Pneumocystis jirovecii_).

### 4.1 Accepted — 10 articles, both gates PASS

All ten: **Gate A = PASS**, **Gate B = PASS**, licence URI
`https://creativecommons.org/licenses/by/4.0/` taken from the JATS `<license>` element via
`ali:license_ref`, retrieved **2026-08-03 (UTC)** from the PMC article page, PMC OA web service
string `CC BY`, no AI/LLM/TDM prohibition found. Text committed as `<PMCID>.txt`; the full
machine-readable gate record is `<PMCID>.provenance.json`.

| PMCID           | Title                                                                                                                                                  | Journal, year                         | JATS type                               | Airway | chars  | Publisher page (gate B)                 |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------- | --------------------------------------- | ------ | ------ | --------------------------------------- |
| **PMC7533148**  | Etiology of community-acquired pneumonia in adults: a systematic review                                                                                | Pneumonia, 2020                       | Review                                  | lower  | 29 046 | Springer — SCANNED, clean               |
| **PMC10950989** | Childhood community-acquired pneumonia                                                                                                                 | European Journal of Pediatrics, 2023  | Mini Review                             | lower  | 24 700 | Springer — SCANNED, clean               |
| **PMC10477518** | Mycobacterium tuberculosis: Pathogenesis and therapeutic targets                                                                                       | MedComm, 2023                         | Review                                  | lower  | 95 236 | Wiley — **403, UNKNOWN**                |
| **PMC8570039**  | Differential Diagnosis of Latent Tuberculosis Infection and Active Tuberculosis                                                                        | Frontiers in Microbiology, 2021       | Review                                  | lower  | 74 198 | Frontiers — SCANNED, clean              |
| **PMC11809256** | Respiratory syncytial virus: A review of current basic and clinical knowledge                                                                          | Qatar Medical Journal, 2024           | Review                                  | lower  | 32 013 | QScience — SCANNED, clean               |
| **PMC8231868**  | Bacterial and Viral Coinfections with the Human Respiratory Syncytial Virus                                                                            | Microorganisms, 2021                  | Review                                  | lower  | 42 925 | MDPI — **403, UNKNOWN**                 |
| **PMC8067422**  | Antivirals Targeting the Surface Glycoproteins of Influenza Virus: Mechanisms of Action and Resistance                                                 | Viruses, 2021                         | Review                                  | lower  | 30 991 | MDPI — **403, UNKNOWN**                 |
| **PMC9027852**  | Current Landscape of Coccidioidomycosis                                                                                                                | Journal of Fungi, 2022                | Review                                  | lower  | 34 729 | MDPI — **403, UNKNOWN**                 |
| **PMC8604168**  | JMM Profile: Bordetella pertussis and whooping cough (pertussis): still a significant cause of infant morbidity and mortality, but vaccine-preventable | Journal of Medical Microbiology, 2021 | JMM Profiles (a structured mini-review) | upper  | 14 606 | Microbiology Society — **403, UNKNOWN** |
| **PMC10728601** | Viruses in chronic rhinosinusitis: a systematic review                                                                                                 | Frontiers in Allergy, 2023            | Systematic Review                       | upper  | 41 922 | Frontiers — SCANNED, clean              |

Total committed text: **420 366 characters** across 10 articles.

Per-article licence detail. The **`license-p` text is quoted verbatim** — this is the licence
field as the publisher wrote it, and it is reproduced in the header of each `.txt` file.

---

**PMC7533148** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC7533148/> — retrieved 2026-08-03T03:18:46+00:00
Attribution: _Shoar Saeed, Musher Daniel M.. Etiology of community-acquired pneumonia in adults: a systematic review. Pneumonia. 2020;12:11. doi:10.1186/s41479-020-00074-3. PMC7533148. Licensed CC BY 4.0._
`license-type="OpenAccess"`; copyright statement: `© The Author(s) 2020`
`license-p`, verbatim:

> Open AccessThis article is licensed under a Creative Commons Attribution 4.0 International License, which permits use, sharing, adaptation, distribution and reproduction in any medium or format, as long as you give appropriate credit to the original author(s) and the source, provide a link to the Creative Commons licence, and indicate if changes were made. The images or other third party material in this article are included in the article's Creative Commons licence, unless indicated otherwise in a credit line to the material. If material is not included in the article's Creative Commons licence and your intended use is not permitted by statutory regulation or exceeds the permitted use, you will need to obtain permission directly from the copyright holder. To view a copy of this licence, visit http://creativecommons.org/licenses/by/4.0/.

---

**PMC10950989** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC10950989/> — retrieved 2026-08-03T03:18:49+00:00
Attribution: _Meyer Sauteur Patrick M.. Childhood community-acquired pneumonia. European Journal of Pediatrics. 2023;183(3):1129-1136. doi:10.1007/s00431-023-05366-6. PMC10950989. Licensed CC BY 4.0._
Copyright statement: `© The Author(s) 2023`
`license-p`, verbatim:

> Open Access This article is licensed under a Creative Commons Attribution 4.0 International License, which permits use, sharing, adaptation, distribution and reproduction in any medium or format, as long as you give appropriate credit to the original author(s) and the source, provide a link to the Creative Commons licence, and indicate if changes were made. The images or other third party material in this article are included in the article's Creative Commons licence, unless indicated otherwise in a credit line to the material. If material is not included in the article's Creative Commons licence and your intended use is not permitted by statutory regulation or exceeds the permitted use, you will need to obtain permission directly from the copyright holder. To view a copy of this licence, visit http://creativecommons.org/licenses/by/4.0/.

---

**PMC10477518** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC10477518/> — retrieved 2026-08-03T03:18:53+00:00
Attribution: _Yang Jiaxing, Zhang Laiying, Qiao Wenliang, Luo Youfu. Mycobacterium tuberculosis: Pathogenesis and therapeutic targets. MedComm. 2023;4(5):e353. doi:10.1002/mco2.353. PMC10477518. Licensed CC BY 4.0._
Copyright statement: `© 2023 The Authors. MedComm published by Sichuan International Medical Exchange & Promotion Association (SCIMEA) and John Wiley & Sons Australia, Ltd.`
`license-p`, verbatim:

> This is an open access article under the terms of the http://creativecommons.org/licenses/by/4.0/ License, which permits use, distribution and reproduction in any medium, provided the original work is properly cited.

Gate B note: Wiley returned **403** for `https://doi.org/10.1002/mco2.353`; publisher-site terms are **UNKNOWN**. The PMC landing page was scanned and is clean.

---

**PMC8570039** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC8570039/> — retrieved 2026-08-03T03:18:56+00:00
Attribution: _Gong Wenping, Wu Xueqiong. Differential Diagnosis of Latent Tuberculosis Infection and Active Tuberculosis: A Key to a Successful Tuberculosis Control Strategy. Frontiers in Microbiology. 2021;12:745592. doi:10.3389/fmicb.2021.745592. PMC8570039. Licensed CC BY 4.0._
Copyright statement: `Copyright © 2021 Gong and Wu.`
`license-p`, verbatim:

> This is an open-access article distributed under the terms of the Creative Commons Attribution License (CC BY). The use, distribution or reproduction in other forums is permitted, provided the original author(s) and the copyright owner(s) are credited and that the original publication in this journal is cited, in accordance with accepted academic practice. No use, distribution or reproduction is permitted which does not comply with these terms.

Gate B note: both the PMC page and frontiersin.org mention _artificial intelligence_ — classified as **incidental mentions**, no restrictive context, no prohibition.

---

**PMC11809256** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC11809256/> — retrieved 2026-08-03T03:18:59+00:00
Attribution: _Al-leimon Obada, Shihadeh Hani, Yousef Ahmad Ayman, Khraim Anas, Siwwad Rizeq. Respiratory syncytial virus: A review of current basic and clinical knowledge. Qatar Medical Journal. 2024;2024(4):56. doi:10.5339/qmj.2024.56. PMC11809256. Licensed CC BY 4.0._
Copyright statement: `© 2024 Al-leimon, Shihadeh, Yousef, Khraim, Siwwad, licensee HBKU Press.`
`license-p`, verbatim:

> This is an open access article distributed under the terms of the Creative Commons Attribution license CC BY 4.0, which permits unrestricted use, distribution and reproduction in any medium, provided the original work is properly cited.

---

**PMC8231868** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC8231868/> — retrieved 2026-08-03T03:19:02+00:00
Attribution: _Pacheco Gaspar A., Gálvez Nicolás M. S., Soto Jorge A., Andrade Catalina A., Kalergis Alexis M.. Bacterial and Viral Coinfections with the Human Respiratory Syncytial Virus. Microorganisms. 2021;9(6):1293. doi:10.3390/microorganisms9061293. PMC8231868. Licensed CC BY 4.0._
Copyright statement: `© 2021 by the authors.`
`license-p`, verbatim:

> Licensee MDPI, Basel, Switzerland. This article is an open access article distributed under the terms and conditions of the Creative Commons Attribution (CC BY) license (https://creativecommons.org/licenses/by/4.0/).

Gate B note: MDPI returned **403**; publisher-site terms are **UNKNOWN**.

---

**PMC8067422** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC8067422/> — retrieved 2026-08-03T03:19:04+00:00
Attribution: _Bai Yaqin, Jones Jeremy C., Wong Sook-San, Zanin Mark. Antivirals Targeting the Surface Glycoproteins of Influenza Virus: Mechanisms of Action and Resistance. Viruses. 2021;13(4):624. doi:10.3390/v13040624. PMC8067422. Licensed CC BY 4.0._
Copyright statement: `© 2021 by the authors.`
`license-p`, verbatim:

> Licensee MDPI, Basel, Switzerland. This article is an open access article distributed under the terms and conditions of the Creative Commons Attribution (CC BY) license (https://creativecommons.org/licenses/by/4.0/).

Gate B note: MDPI returned **403**; publisher-site terms are **UNKNOWN**.

---

**PMC9027852** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC9027852/> — retrieved 2026-08-03T03:19:07+00:00
Attribution: _Boro Ryan, Iyer Prema C., Walczak Maciej A.. Current Landscape of Coccidioidomycosis. Journal of Fungi. 2022;8(4):413. doi:10.3390/jof8040413. PMC9027852. Licensed CC BY 4.0._
Copyright statement: `© 2022 by the authors.`
`license-p`, verbatim:

> Licensee MDPI, Basel, Switzerland. This article is an open access article distributed under the terms and conditions of the Creative Commons Attribution (CC BY) license (https://creativecommons.org/licenses/by/4.0/).

Gate B note: MDPI returned **403**; publisher-site terms are **UNKNOWN**.

---

**PMC8604168** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC8604168/> — retrieved 2026-08-03T03:21:23+00:00
Attribution: _Fry Norman K., Campbell Helen, Amirthalingam Gayatri. JMM Profile: Bordetella pertussis and whooping cough (pertussis): still a significant cause of infant morbidity and mortality, but vaccine-preventable. Journal of Medical Microbiology. 2021;70(10):001442. doi:10.1099/jmm.0.001442. PMC8604168. Licensed CC BY 4.0._
Copyright statement: `© 2021 The Authors`
`license-p`, verbatim:

> This is an open-access article distributed under the terms of the Creative Commons Attribution License. This article was made open access via a Publish and Read agreement between the Microbiology Society and the corresponding author's institution.

Note: the prose here says only "Creative Commons Attribution License" with **no version**. The
version comes from the machine-readable `ali:license_ref`, `https://creativecommons.org/licenses/by/4.0/`.
This article is the reason gate A insists on the URI rather than the prose. Gate B note: the
Microbiology Society site returned **403**; publisher-site terms are **UNKNOWN**.

---

**PMC10728601** — <https://pmc.ncbi.nlm.nih.gov/articles/PMC10728601/> — retrieved 2026-08-03T03:22:00+00:00
Attribution: _Kumar Nitish, Brar Tripti, Kita Hirohito, Marks Lisa A., Miglani Amar, Marino Michael J., et al.. Viruses in chronic rhinosinusitis: a systematic review. Frontiers in Allergy. 2023;4:1237068. doi:10.3389/falgy.2023.1237068. PMC10728601. Licensed CC BY 4.0._
Copyright statement: `© 2023 Kumar, Brar, Kita, Marks, Miglani, Marino and Lal.`
`license-p`, verbatim:

> This is an open-access article distributed under the terms of the Creative Commons Attribution License (CC BY). The use, distribution or reproduction in other forums is permitted, provided the original author(s) and the copyright owner(s) are credited and that the original publication in this journal is cited, in accordance with accepted academic practice. No use, distribution or reproduction is permitted which does not comply with these terms.

---

### 4.2 Rejected by gate A — 5 articles, not committed

| PMCID           | Title / journal                                                                                        | Licence field verbatim (URI)                         | Gate A | Gate B | Reason                                                                                                                                                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------- | ------ | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PMC11601064** | Croup review: comparative analysis of acute and recurrent croup — J Bras Pneumol 2024                  | `https://creativecommons.org/licenses/by/4.0/`       | FAIL   | PASS   | **Stale-footer conflict, live.** PMC field says CC BY 4.0; publisher site carries a site-wide `rel="license"` banner for `http://creativecommons.org/licenses/by-nc/4.0/`. Two licences, one work — refused rather than resolved in our favour. |
| **PMC10652663** | Tonsillitis and Sinusitis: A Narrative Review of Pathogenesis, Diagnosis, and Management — Cureus 2023 | `https://creativecommons.org/licenses/by/3.0/`       | FAIL   | PASS   | **CC BY 3.0, not 4.0.** The PMC OA web service string is the coarse `CC BY`, which hides the version — exactly why gate A reads the versioned URI.                                                                                              |
| **PMC10982721** | Role of vitamin C in treatment of community-acquired pneumonia … — BMJ Open 2024                       | `https://creativecommons.org/licenses/by-nc/4.0/`    | FAIL   | PASS   | **CC BY-NC 4.0.** NonCommercial conflicts with AGPL-3.0-or-later.                                                                                                                                                                               |
| **PMC7290537**  | Diagnostic markers for community-acquired pneumonia — Ann Transl Med 2020                              | `https://creativecommons.org/licenses/by-nc-nd/4.0/` | FAIL   | PASS   | **CC BY-NC-ND 4.0.** NonCommercial _and_ NoDerivatives; the latter forbids turning it into flashcards.                                                                                                                                          |
| **PMC7094947**  | Challenges in severe community-acquired pneumonia: a point-of-view review — Intensive Care Med 2019    | _(none — no URI in the `<license>` element)_         | FAIL   | PASS   | **No machine-readable licence.** Prose reads "made available via the PMC Open Access Subset … for the duration of the WHO declaration of COVID-19 as a global pandemic" — a time-limited, non-CC permission. Not usable.                        |

### 4.3 Passed both gates but excluded on document type — 3 articles, not committed

The brief asked for **review** articles. These are licence-clean but are not reviews; they were
dropped rather than quietly counted.

| PMCID           | Title / journal                                                                              | JATS `<subject>` type | Why excluded                                                                                                                                                |
| --------------- | -------------------------------------------------------------------------------------------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PMC7281116**  | Mycobacterium tuberculosis Pathogenesis, Infection Prevention and Treatment — Pathogens 2020 | `Editorial`           | Special-issue editorial, 8 615 characters of body text. Not a review.                                                                                       |
| **PMC9444058**  | Antimicrobial therapy in complicated rhinosinusitis — Frontiers in Microbiology 2022         | `Original Research`   | The title reads like a review; the JATS type says primary research.                                                                                         |
| **PMC12148406** | Rhinosinusitis: Evidence and experience – 2024 — Braz J Otorhinolaryngol 2025                | `Original Article`    | Self-describes as "this new guideline … updated Consensus". A clinical guideline, not a review article. 345 155 characters — tempting, and excluded anyway. |

### 4.4 Was the government-works fallback used?

**No.** PMC succeeded. No NIH/CDC/US-federal public-domain material was used, and nothing in this
directory relies on the public-domain fallback. The fallback remains available if a future organ
system has no CC BY 4.0 review coverage; if it is ever taken, it must be declared as loudly as this
sentence declares that it was not.

---

## 5. What is in this directory

| File                      | What it is                                                                                                                                                                    |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vet_source.py`           | The two-gate checker. `--self-test` runs 40 offline assertions; exits non-zero if any gate fails.                                                                             |
| `LICENCE-PROVENANCE.md`   | This file.                                                                                                                                                                    |
| `<PMCID>.txt`             | Article text, flattened from JATS XML, prefixed by a provenance header (PMCID, licence verbatim, retrieval date, attribution, URL, gate results, statement of modifications). |
| `<PMCID>.provenance.json` | The full machine-readable gate record for that article, including the raw `<permissions>` XML and the SHA-256 of the `.txt`.                                                  |
| `vetting-run.json`        | One audit record covering **all 18 PMCIDs** vetted — accepted, rejected, and type-excluded.                                                                                   |

### CC BY 4.0 compliance of the committed text

Each `.txt` carries attribution and a statement of modifications, as CC BY 4.0 §3(a) requires. The
modifications are: article body flattened from JATS XML to plain text; references, affiliations,
funding statements and figure images dropped; figure and table captions kept in `[brackets]`; no
wording altered.

**Figures and other third-party material were not copied.** Several of the grants above explicitly
carve out third-party material (see the Springer wording), so nothing that could fall in that
carve-out was taken.

### How to re-verify

```sh
python3 speedrun-analysis/sources/vet_source.py --self-test          # offline, no network
python3 speedrun-analysis/sources/vet_source.py --publisher PMC7533148 …   # live re-check
```

Re-checking is worth doing periodically: a publisher can change a site banner or add an AI clause
at any time, which is the whole reason gate B exists.
