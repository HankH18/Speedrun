> Covers three tools observed hands-on. AnKing/AnkiHub findings are vendor-documentation tier and live in `BRAINLIFT.md` §4.

# Speedrun — Teardown Observation Log (Stage 1, complete)

**Observer:** Hank · **Date:** 2026-07-31 · **Method:** live hands-on, screenshots retained

## Method disclosure — read this before citing any number below

All sessions were answered at **1–4 seconds per item**, against tool-displayed targets of roughly 90 seconds. This was a deliberate zero-effort probe, not a study session. It corresponds directly to the adversarial case in the project brief's Section 10: _"a student tapping Good without reading."_

**What this licenses:** claims about how each tool behaves when input data is worthless — specifically whether it abstains, bands, or warns.

**What this does NOT license:** any claim about these tools' accuracy, usefulness, or behavior under genuine study. Those were not observed and must not be asserted.

Evidence tier for everything in this document: **[O] directly observed**, unless marked otherwise.

---

## Capture table

| Field                   | MDSteps                                                    | AMBOSS                                                                                  | 7Sage                                               |
| ----------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------- |
| Account state           | Free, no signup                                            | 5-day trial                                                                             | $1 fee-waiver tier                                  |
| Questions answered      | 10                                                         | 40 (2×20)                                                                               | 50 (2 drills)                                       |
| Accuracy                | 3/10 (30%)                                                 | 13% (5/40)                                                                              | 12% (6/50)                                          |
| Headline metric name    | _(none — pattern labels only)_                             | "Probability of passing"; "Equated Percent Correct (EPC)"; "Peer group comparison"      | "PT equivalent score"; "Accuracy"; "Score progress" |
| Headline value          | —                                                          | 0% · 28.5% · 0th percentile                                                             | ~128 on the 120–180 LSAT scale                      |
| **Band / CI / range**   | **None**                                                   | **None**                                                                                | **None**                                            |
| **Abstention observed** | **Partial** — emits no score at all                        | **Split** — Score Predictor requires uploaded real exams; Analysis tab does not abstain | **None**                                            |
| Min-data threshold      | None stated                                                | None stated                                                                             | None stated                                         |
| Timing tracked          | Not surfaced                                               | Yes — per-question, and "0h 00m" total                                                  | Yes — per-question **vs. target**, all ≈ −01:20     |
| Rewording / paraphrase  | Not observed                                               | Not observed                                                                            | Not observed                                        |
| Volume as progress      | "10-question diagnostic"                                   | "40 attempts across 40 unique questions"; topic % completed                             | "Questions drilled: 50"; "Drills taken: 2"          |
| Uncertainty language    | "an early read"; "not just a score"; "starts turning into" | None on Analysis tab                                                                    | None visible; unopened "?" tooltip on PT equivalent |

---

## Per-tool findings

### 7Sage — the strongest exhibit

**Observed:** 50 questions at 12% accuracy, answered in 1–4 seconds each, converted into a **"PT equivalent score" of ~128 plotted on the official 120–180 LSAT scale**, at both the individual-drill level ("ACTUAL PT EQUIVALENT 128") and the aggregate Drills dashboard, with a toggle between "% score" and "PT equivalent score."

**Why it matters:** the same interface displays **timing versus target** for every question, every one flagged at roughly −01:20. The tool held direct, displayed evidence that the input was invalid and produced a projection on the real score scale regardless. This is the brief's "inventing a readiness number / dressing a guess as a measurement" failure, observed in a shipping product, with the disconfirming signal one screen away.

**Credit where due:** the difficulty tooltip exposes item calibration as a score-scale location with bounds — _avg. score of students with a 50% chance of getting this right: 138; 25%: 128; 75%: 149_. This is the most psychometrically sophisticated surface observed in any tool, and it is not marketed anywhere. A teardown that finds nothing good is a vibe; this is the counterexample.

**Unexplained:** per-tag accuracy goals (91%, 99%, 90%) with no stated provenance.

**Open:** the "?" tooltip beside PT equivalent was not opened. It may contain a caveat. Do not claim "no caveat exists" — claim "no caveat is visible on the surface where the number is displayed."

### AMBOSS — split behavior, borrowed vocabulary

**Prediction falsified:** the Score Predictor did **not** display a number at zero data. It requires the user to "Share exams" — upload real practice-exam results. This is abstention by construction and a genuine point in AMBOSS's favor. _(My pre-registered expectation was wrong; logged here rather than quietly dropped.)_

**Contradiction relocated, not removed:** the adjacent **Analysis** tab computed "Probability of passing: 0%," "EPC: 28.5%," and "0th percentile" from 40 rapid-clicked questions — no band, no minimum threshold, no warning. One surface in the same product abstains; the neighbouring one does not.

**Headline finding — metric-name appropriation:** AMBOSS labels its metric **"Equated Percent Correct (EPC)"**, NBME's exact term. NBME's EPC is statistically equated across CBSSA, CBSE, and Step 1 forms with published methodology and a stated ±4 precision band. AMBOSS's is derived from its own question bank; no equating methodology or precision estimate is shown. Same name, inherited authority, undocumented construct.

**Also observed:** Score Predictor chart axis runs 140–280 — a three-digit scale for an exam that has had no numeric score since 26 Jan 2022. Deltas shown as "−92.4% last 31 days" on an account with no prior history.

**Open:** "How does the analysis work?" and "How does the score predictor work?" links were not opened. These are the cheapest remaining evidence in the entire teardown.

### MDSteps — declines to score, overclaims the pattern

**Observed output:** 3/10 correct · "Missed pivot clue — dominant signal" · "7 answers exposed repair targets" · pattern mix: Missed pivot clue 3/10, Distractor pull 3/10, Sequence error 1/10, Repeatability check 3/10.

**No readiness number of any kind.** No score, no pass probability, no percentile. Despite being the AI-native entrant whose marketing occupies the transfer-gap niche, it is the only tool of the three that declines to emit a readiness figure from thin data.

**Structurally honest element:** "PROOF FROM YOUR ANSWERS — the result is based on the choices you made," followed by per-item deciding clues. Each claim traces to a specific answer. That is the traceability principle the project brief demands, implemented in a competitor.

**The overclaim:** "**dominant signal**" is asserted where two categories are tied at 3/10 each. On n=10 with a tie, "dominant" is a coin flip presented as a diagnosis.

**Do not attack the arithmetic:** the pattern mix is internally consistent (3+3+1 = the 7 incorrect; the 3 correct map to Repeatability check).

---

## Cross-tool synthesis

**1. Honesty ranks inversely to sophistication of claim.**
MDSteps (no score) > AMBOSS (score, but predictor demands real exam data) > 7Sage (official-scale score from 50 rapid clicks). The tool making the smallest claim is the most defensible; the one mapping to the real scale is the least.

**2. Zero of three abstained on the surface that mattered.** One (AMBOSS Score Predictor) abstains by requiring external data, but its sibling tab does not. Abstention exists as an accident of data dependency, not as a designed principle.

**3. Zero of three displayed a band, range, or confidence indicator.** Against this, NBME publishes a ±4 likely-score range plus an explicit "not a guarantee" caveat and an annually-updated model date. The market's most honest instrument is the non-commercial one.

**4. Nobody rewords.** No tool was observed paraphrasing an item to test the same concept differently. The transfer-versus-recognition distinction is untested by every product examined.

**5. Timing is captured but not gated.** AMBOSS and 7Sage both track per-question time; 7Sage tracks it against an explicit target. Neither uses it to suppress a projection. The signal is collected and discarded at exactly the moment it would have prevented an error.

---

## Direct implications for the build

| Observation                                         | Build consequence                                                                             |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| No tool bands its headline number                   | Three scores ship with ranges, always. Never a bare point estimate.                           |
| 7Sage projects from invalid-by-its-own-metric input | Give-up rule must gate on **response-time plausibility**, not just review count and coverage. |
| AMBOSS reuses "EPC" without methodology             | Every metric name in the app links to its own definition and computation.                     |
| MDSteps traces claims to specific answers           | Adopt this — it is the traceability requirement, already validated in-market.                 |
| MDSteps calls a 3/3 tie "dominant"                  | Any pattern claim must carry n and a separation test before it is named.                      |
| 7Sage exposes item difficulty with 25/75 bounds     | Prior art for showing item-level uncertainty. Match or exceed it.                             |

---

## Limitations to state in the Brainlift

1. All observations are zero-effort probes; genuine-engagement behavior was not observed.
2. UWorld was excluded on cost (no meaningful trial; 30-day access in the hundreds of dollars). It is the market leader and is covered by documented claims only — labeled as such, not as observed behavior.
3. No live NBME CBSSA form was purchased. NBME findings derive from the published sample score report (test date 12/9/2024, model last updated 20 Aug 2024). Consequently: whether NBME's caveats appear in the product UI or only in the PDF is **unverified**.
4. Two "how does this work?" documentation links in AMBOSS and one tooltip in 7Sage remain unopened.
5. Sample sizes are 10–50 questions per tool. Sufficient to observe abstention behavior; insufficient for anything else.
