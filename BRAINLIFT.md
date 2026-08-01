# Brainlift v0.9 — Speedrun

**Exam: USMLE Step 1** (pass/fail since 26 January 2022)
**Author:** Hank Holcomb · **Status:** early submission · **Sections 6 and 8 incomplete — see §0**

---

## 0. Status disclosure — read first

This is a partial Brainlift submitted at the Friday deadline. Rather than present it as complete, here is exactly what stands and what does not.

| Required section | Status |
|---|---|
| 1. Purpose and scope | Complete |
| 2. DOK 1 — named sources | Complete (7 primary + systems lineage) |
| 3. DOK 2 — own words, took/rejected | Complete |
| 4. DOK 3 — disagreements, assumptions, teardown | Complete |
| 5. DOK 4 — three Spiky POVs with falsifiers | Complete |
| 6. AI consensus check transcripts | **NOT RUN** — harness designed, not executed |
| 7. Traceability table | Complete as specification; no code yet |
| 8. What changed by Sunday | **PENDING** — Sunday deliverable |

Additional known gaps, disclosed rather than hidden:

- **Teardown depth.** Three tools observed hands-on (MDSteps, AMBOSS, 7Sage). A fourth (Anki/AnkiHub/AnKing) is covered by vendor documentation plus database inspection, not full UI observation. UWorld is covered by documented claims only — excluded on cost, labeled as such throughout.
- **Zero-effort probe.** All hands-on sessions were answered at 1–4 seconds per item against ~90-second targets. This was deliberate (see §4.3) and is disclosed everywhere it is used. It licenses claims about tool behavior on worthless input. It licenses **nothing** about these tools' accuracy under genuine study.
- **Source verification.** Several source-code citations are marked UNVERIFIED because `git clone` was blocked by an egress proxy and GitHub's rendered line gutter was unreadable through the fetch layer. These are labeled VERIFIED / UNVERIFIED / UNKNOWN inline. None were upgraded by guessing a plausible line number.
- **No code exists yet.** The traceability table in §7 specifies what each POV forces; it does not yet point at commits.

---

## 1. Purpose and scope

**Purpose.** Build a desktop and mobile study app on a fork of Anki that reports three separately-derived scores for USMLE Step 1 — Memory (DOK 1), Performance (DOK 2/3), and Readiness (DOK 4) — each with an explicit range, each refusing to report when the data underneath it is insufficient.

**Why Step 1.** Step 1 has been pass/fail since 26 January 2022, with a minimum passing standard of 196 reaffirmed through 2026. Every alternative exam (MCAT, LSAT, GMAT Focus) requires inventing and defending a mapping from question performance to a scaled score that cannot be validated against ground truth in one week. Step 1's binary outcome makes the readiness model a **classifier**, where Brier score, log loss, and reliability curves fall out natively and honestly.

**The trap this creates, stated up front.** 2024 first-attempt pass rates were 91% (US MD), 86% (US DO), 73% (IMG). A classifier that always outputs "pass" therefore scores roughly 91% accuracy while being a constant function. **Accuracy is a forbidden metric in this project.** Calibration is reported via Brier score and log loss, stratified by predicted-probability band, with particular attention near the low-pass region where the base rate stops doing the work.

**Out of scope.**
- Content generation at scale. AI is used for card generation and item rewording only, always traced to a named source and always evaluated against a held-out gold set.
- Any claim about long-run learning outcomes. One week does not permit a learning-outcomes study.
- Step 2 CK and Step 3.
- Reproducing NBME's equating. We map to pass probability, not to any numeric score, because Step 1 has no numeric score.

---

## 2. DOK 1 — Sources

### Learning science (primary literature)

1. **Pan, S. C., & Rickard, T. C. (2018).** Transfer of test-enhanced learning: Meta-analytic review and synthesis. *Psychological Bulletin*, 144(7), 710–756. 192 effect sizes, 122 experiments, N = 10,396.
2. **Frappa, Chernov, Dillon & Alben (2026).** Systematic review of Anki use and academic outcomes in medical education. *Medical Science Educator*, 36, 1015–1025. DOI 10.1007/s40670-026-02643-5. 11 studies, 1,135 students, PRISMA, MERSQI-scored. Open access.
3. **Price, D. W., Wang, T., O'Neill, T. R., et al. (2025).** The effect of spaced repetition on learning and knowledge transfer in a large cohort of practicing physicians. *Academic Medicine*, 100(1), 94–102. 26,000+ physicians. *(Counter-evidence to POV 1 — see §3.3.)*
4. **Deng, F., Gluckstein, J. A., & Larsen, D. P. (2015).** Student-directed retrieval practice is a predictor of medical licensing examination performance. *Perspectives on Medical Education*, 4(6), 308–313.
5. **Macnamara, B. N., Hambrick, D. Z., & Oswald, F. L. (2014).** Deliberate practice and performance. *Psychological Science*, 25, 1608–1618. 88 studies, N = 11,135.
6. **Bjork, R. A., Dunlosky, J., & Kornell, N. (2013).** Self-regulated learning: Beliefs, techniques, and illusions. *Annual Review of Psychology*.
7. **Dunlosky, J., et al. (2013).** Improving students' learning with effective learning techniques. *Psychological Science in the Public Interest*, 14(1), 4–58.

### Test-maker documentation

8. **NBME Comprehensive Basic Science Self-Assessment** — published sample score report (test date 12/9/2024; pass-probability model last updated 20 August 2024) and accompanying guidance document.
9. **USMLE Content Outline** (© FSMB and NBME) — organ systems × physician tasks; the coverage map's authority.

### Systems lineage

10. **Woźniak, P.** SuperMemo SM-0 through SM-18; the two-component model of memory (retrievability, stability), later extended to DSR.
11. **Ye, J. (Jarrett).** FSRS — Free Spaced Repetition Scheduler. DSR model, 21 parameters in FSRS-6. `github.com/open-spaced-repetition/fsrs-rs`. Integrated into Anki core in v23.10 (31 October 2023); default scheduler since.
12. **open-spaced-repetition/srs-benchmark** — published comparison of FSRS against SM-2 and alternatives across ~10,000 collections.
13. **Elmes, D.** Anki. `github.com/ankitects/anki`. Rust core (`rslib`), protobuf bridge to Python (`pylib`) and TypeScript, Qt frontend, SQLite collection, scheduler v3, `OpChanges`-based undo. Licensed **AGPL-3.0-or-later with portions under BSD-3-Clause**.
14. **AnkiDroid** — `ankidroid/Anki-Android-Backend`, JNI bridge to the shared `rslib` core.
15. **amgi** — `github.com/antigluten/amgi`. Open-source SwiftUI iOS client running the official Anki Rust backend through its C FFI. Existence proof that the iOS requirement is tractable.

### Vendor documentation examined as evidence

16. **AnKing / AnkiHub official course** — Lesson 6 "The fundamentals: Learn → remember → apply"; Supplemental C (missed-question workflow); Supplemental D (research and science).
17. **AMBOSS support documentation** — "How does the Analysis work."

---

## 3. DOK 2 — Sources in my own words: what I took, what I rejected

### 3.1 Pan & Rickard (2018) — the keystone

**Took.** Retrieval practice transfers, at d = 0.40 (95% CI [0.31, 0.50]). More importantly, the paper identifies *moderators* that govern whether transfer happens. Response congruency: when the transfer item requires a different response than trained, the effect is d = 0.28; when congruency holds, congruency adds an estimated d = 0.30 for a total of 0.58. Initial test accuracy: transfer rises by roughly 0.0058 per percentage point of initial accuracy, and **disappears entirely at particularly poor initial performance**. Elaborated retrieval practice (broad encoding, constructing detailed explanations) adds d = 0.23.

Each of these three moderators is measurable from data Anki already logs or could log. That is the whole build.

**Rejected — and this killed my first thesis.** I initially believed retrieval practice transfers poorly to application items. Pan & Rickard say the opposite: transfer is *greatest* across changed test formats, to application and inference questions, and specifically to problems involving medical diagnoses. Any POV asserting "cards don't transfer to vignettes" is contradicted by the strongest evidence in the field. The surviving claim is narrower and conditional — see POV 1.

### 3.2 Frappa et al. (2026) — the dose-response evidence and its ceiling

**Took.** Three independent studies associate Anki use with higher Step 1 scores (Lu: 241.1 vs 235.5, p = 0.012; Deng: ~1,700 unique cards per additional point, p = 0.024; Wothe: 238 vs 233.5, p = 0.039). Winter et al. is the most useful single result: mature-card count was the **only** independent predictor of CBSE score (β = 0.649, p = 0.026) with **R² = 0.427** — meaning roughly 57% of variance is unexplained by card mastery, from objectively logged data rather than self-report.

The Step 2 CK result is the sharpest finding in the review: daily Anki users scored 252.5 vs 247.0, **p = 0.440, not significant**, and not an independent predictor once Step 1 score and class rank were controlled. The authors' own reading is that Anki suits foundational fact-based material and matters less where higher-order clinical reasoning dominates. Same tool, same students, higher-DOK assessment, effect vanishes.

Two studies found **no** performance benefit while 87% and 74% of participants rated the intervention favorably (Sun: p = 0.54; Magro: p = 0.43). That is a published fluency illusion, measured twice.

**Rejected.** All of it is observational. None randomized. Self-selection is unaddressed by the authors' own admission, and at least one study (Rocky Vista, COMLEX) found no significant association. I do not claim causation and neither should anyone citing these.

### 3.3 Price et al. (2025) — my strongest counter-evidence

**Took.** 26,000+ practicing physicians; spaced repetition improved knowledge retention **and transfer**. This is the largest, cleanest study in the space and it cuts directly against a naive version of my thesis. I state it here rather than burying it.

**Why POV 1 survives it.** Price measured practicing physicians on clinical knowledge over an extended horizon. My claim concerns novice students on high-DOK vignette items within an exam-prep window, and — critically — it does not deny that transfer occurs. It asserts that transfer is *conditional on measurable moderators* and that no tool measures them. Price is consistent with that: it demonstrates transfer happens, not that it happens uniformly or that anyone can tell you whether it happened for you.

### 3.4 Macnamara et al. (2014)

**Took.** Deliberate practice explains far less variance than the popular account claims: 26% in games, 21% music, 18% sports, **4% education**, under 1% in professions. In education specifically, practice volume is a weak explanation of performance. This is the empirical backbone for treating volume as a poor proxy.

**Rejected.** Ericsson disputes the meta-analysis on definitional grounds and the exchange is unresolved. I present these figures as one side of a live debate, not settled fact.

### 3.5 Bjork/Dunlosky/Kornell and Dunlosky et al. (2013)

**Took.** Learners are poor judges of their own learning; fluency creates confidence without durable recall; practice testing and distributed practice rank high-utility while rereading and highlighting rank low. This is the mechanism behind the fluency illusion measured in §3.2.

**Rejected.** Nothing here shows that *telling* a learner they are miscalibrated fixes it. My app therefore reports calibration rather than assuming that reporting it changes behavior — a claim I am not equipped to test in a week.

### 3.6 NBME CBSSA — the honest benchmark

**Took.** The published sample report shows Total Equated Percent Correct 73%, likely score range 69–77, estimated probability of passing 99%, and a longitudinal history across forms (26 → 56, 27 → 69, 28 → 73). The band is ±4 at the 68% level. NBME states plainly that a 90% estimated probability still means 1 in 10 examinees at that performance level will fail, and that the estimate is not the same as the percentage of content mastered. Content-area scores carry an explicit warning that they are less precise than total scores.

**Directly shippable:** NBME's rule that if the precision lines for two administrations overlap, performance was not significantly different. Applied to the sample's own data: 56±4 (52–60) vs 69±4 (65–73) do not overlap — real gain. 69±4 (65–73) vs 73±4 (69–77) **do** overlap — the 69→73 "improvement" is noise. A student reading that as progress is reading noise, and the instrument says so.

**Rejected.** I do not reproduce NBME's equating. Their EPC is equated across CBSSA, CBSE, and live Step 1 forms with a published annually-updated model. Mine would be neither equated nor validated, so I do not use their metric name.

### 3.7 Systems lineage

**Took.** SuperMemo established the two-component model that FSRS's DSR formalizes. FSRS ships in Anki core as the default scheduler and exposes per-card difficulty, stability, and retrievability — meaning **the Memory score's primitive already exists, open source, for free**. Anki's `rslib` Rust core with a protobuf bridge to Python and TypeScript is a genuine three-layer architecture, and AnkiDroid already consumes the same core over JNI. `amgi` proves the iOS-via-C-FFI path is real and not theoretical.

**Rejected.** The frequently-cited "FSRS needs 20–30% fewer reviews at equal retention" figure comes from simulation, not a controlled trial, and SM-2 was never designed to emit probabilities — the log-loss comparison flatters FSRS somewhat. I use FSRS because it produces a calibrated per-card probability, not because of that marketing number.

---

## 4. DOK 3 — Disagreements, assumptions, and what the teardown exposed

### 4.1 Where sources disagree

**a) The incumbent contradicts itself.** AnKing's Supplemental D asserts that spaced repetition delivers knowledge transfer, citing Price et al. Their Lesson 6 states that Anki covers *remember*, and that *apply* "is done primarily with question banks such as AMBOSS & UWorld," where you "apply it in novel situations." One document claims the benefit; the other routes users to a competitor to obtain it. **Neither ships an instrument that tells a student whether it happened.**

**b) The field cannot agree on the sign of its own instruments' bias.** One review source claims UWSA1 overpredicts by 10–15 points; another claims NBMEs underpredict by 10–20. Opposite directions, comparable authority. I cite neither as fact; the disagreement *is* the finding.

**c) Perception versus performance.** 87% and 74% favorability in studies measuring no performance effect (p = 0.54, p = 0.43).

**d) DOK-dependent efficacy.** Anki associates with Step 1 across three studies and not with Step 2 CK (p = 0.440).

**e) Deliberate practice.** Ericsson vs Macnamara/Hambrick, unresolved and definitional.

### 4.2 What the field assumes and nobody checks

1. **That card count is a progress signal.** AnkiHub's product card for the AnKing Step Deck displays exactly two numbers — 28k notes and 185k subscribers. Volume and popularity. Neither measures learning. Winter et al. put the ceiling on this at R² = 0.427.
2. **That a readiness number needs no error bar.** IRT theta estimates have standard errors by construction. AMBOSS computes theta and reports bare point estimates.
3. **That the exam blueprint is the organizing principle.** The market-leading deck is tagged by vendor resource (`#AK_Step1_v12 → #B&B → 06_Cardio → 02_Cardiac_Ischemia → …`), not by the USMLE content outline. A student using it **cannot answer "what percentage of the exam have I covered?"**
4. **That adding AI means adding measurement.** AnkiHub's $10/month Premium tier buys AI Smart Search and AI chat — retrieval and explanation. Not one feature measures whether you can use what you found.

### 4.3 What the teardown exposed

**Method disclosure.** All sessions were answered at 1–4 seconds per item against displayed targets of roughly 90 seconds. This was a deliberate zero-effort probe corresponding to the brief's own adversarial case — "a student tapping Good without reading." It tests whether a tool abstains on worthless input. It says nothing about accuracy under genuine study, and no claim below extends that far.

**7Sage [O] — the automatic-fail exhibit.** 50 questions, 12% accuracy, 1–4 seconds each, converted into an "ACTUAL PT EQUIVALENT" of 128 plotted on the official 120–180 LSAT scale, at both drill and dashboard level. The same interface displays timing-versus-target for every question, each flagged at roughly −01:20. **The tool held displayed evidence that the input was invalid and emitted a scaled projection anyway.** Per-tag accuracy goals (91%, 99%, 90%) appear with no stated provenance.

*Credit where due:* 7Sage's difficulty tooltip exposes item calibration as a score-scale location with bounds — average score of students with a 50% chance of answering correctly: 138; 25th percentile 128, 75th 149. This is the most psychometrically sophisticated surface observed anywhere in the teardown, and it is not marketed.

**AMBOSS [O/V] — machinery present, uncertainty discarded.** Prediction falsified: the Score Predictor does *not* emit a number at zero data; it requires uploading real practice-exam results. Abstention by construction, and a genuine point in their favor. But the adjacent Analysis tab computed "Probability of passing: 0%", "EPC: 28.5%", and "0th percentile" from 40 rapid-clicked questions with no band and no threshold. Their documentation states the method: theta scores converted into per-question success probabilities, averaged into EPC, with recent answers weighted more strongly. That is IRT. **An IRT theta estimate has a standard error by construction; they compute it and report a bare point estimate.** They also scope honestly — probability of passing for Step 1, estimated score for Step 2 CK, and percentile explicitly labeled "not a prediction of your exam score."

**MDSteps [O] — declines to score, overclaims the pattern.** The AI-native entrant marketing the transfer framing produces *no* readiness number at all: 3/10 correct, "Missed pivot clue — dominant signal," a pattern mix of 3/3/1/3, and per-item deciding-clue traces under a heading reading "PROOF FROM YOUR ANSWERS — the result is based on the choices you made." Claim traced to evidence — the traceability principle, implemented by a competitor. The overclaim is elsewhere: "dominant signal" is asserted where two categories are tied at 3/10 each.

**AnkiHub / AnKing [V] — the structural finding.** The AnKing Step Deck (28k notes, 185k subscribers) is gated behind a paid membership. What the membership buys is content freshness and collaborative editing. There is no readiness measure anywhere in the product, and the official course explicitly hands the *apply* stage to AMBOSS and UWorld.

**Cross-tool synthesis.** Honesty ranks *inversely* to the size of the claim: MDSteps (no score) > AMBOSS (score, predictor demands real data) > 7Sage (official-scale score from 50 rapid clicks). Zero of three displayed a band. Zero rewords items to test transfer rather than recognition. Two capture per-question latency and neither gates on it — the signal is collected and discarded at exactly the moment it would have prevented an error.

---

## 5. DOK 4 — Spiky POVs

### POV 1 — the thesis tested in §9

> **Consensus says** more cards means more readiness — the market's flagship deck ships 28,000 notes to 185,000 subscribers, and three published studies show a dose-response between card volume and Step 1 score.
>
> **I think** card mastery's predictive power degrades as item DOK rises, and that transfer is governed by three *measurable* moderators — response congruency, initial retrieval accuracy, and elaboration — none of which any shipping tool measures or optimizes. FSRS optimizes *when* you see a card. Nothing optimizes whether the card's response structure resembles the item you will actually face.
>
> **My evidence:** Pan & Rickard — transfer falls to d = 0.28 when the required response differs from training, versus an estimated 0.58 when it matches, and rises with initial accuracy at 0.0058 per percentage point, vanishing entirely at very poor initial performance. Winter et al. — mature-card count is the only independent CBSE predictor at R² = 0.427, leaving 57% unexplained. Frappa et al. — the Anki association holds for Step 1 and vanishes for Step 2 CK (p = 0.440), the higher-DOK assessment.
>
> **What would prove me wrong:** if FSRS-derived memory mastery predicts vignette accuracy at r > 0.7 on matched paraphrase pairs, the gap I am claiming is not there. If the congruency-structured condition shows no advantage over plain cards at equal study time in the §9 ablation, the moderator is not actionable even if it is real.
>
> **Known counter-evidence:** Price et al. (2025), 26,000+ physicians, found spaced repetition improved retention *and* transfer. My claim is conditional, not a denial — but this is the study that would most likely defeat a stronger version of it.

### POV 2 — calibration

> **Consensus says** a readiness number is a readiness number; students want one figure.
>
> **I think** every uncalibrated point estimate in this market is overconfident, and the damning part is that the machinery to band it is already present and deliberately discarded. AMBOSS runs an IRT theta model — which produces a standard error by construction — and prints "0%" and "28.5%" bare. 7Sage projects onto the official scale while displaying, one column over, that every answer arrived 80 seconds early.
>
> **My evidence:** zero of three tools observed hands-on displayed any band, range, or confidence indicator. The only instrument in the space that publishes a validated model — NBME's CBSSA — attaches a ±4 likely-score range, an annual model-update date, and an explicit statement that 90% still means 1 in 10 will fail. The honest instrument is the non-commercial one.
>
> **What would prove me wrong:** back-test incumbent point estimates against outcomes. If their reliability curves already sit within ±5% of the diagonal, they are calibrated and simply do not display it, and my criticism reduces to a UI complaint.

### POV 3 — the structural frame

> **Consensus says** students who plateau need more volume, better cards, or more questions.
>
> **I think** the transition from memory to application is unmeasured because it falls between two business models. Remember and Apply are separate products from separate companies with separate subscriptions. No instrument spans the boundary because no vendor owns both sides of it — and the incumbent says so in its own courseware.
>
> **My evidence:** AnKing's Lesson 6 states that application "is done primarily with question banks such as AMBOSS & UWorld." Their Supplemental D simultaneously claims spaced repetition delivers knowledge transfer, citing Price et al. The deck is tagged by vendor resource rather than the USMLE outline, so coverage of the actual exam is unanswerable from it. AnkiHub's AI tier adds search and chat — retrieval, not measurement. UWorld does not read your Anki memory state; Anki does not see your QBank performance.
>
> **What would prove me wrong:** if any single product conditions performance on novel items against that user's own card-level memory state, the "nobody owns both sides" claim is false. MDSteps is the closest existing candidate and generates cards from missed questions — but that runs apply → remember. I have found nothing running remember → apply.

---

## 6. AI consensus check

**NOT RUN.** Harness designed: two passes against a model with no access to this document — pass one presents POV 1 cold with no evidence or framing; pass two supplies the evidence packet once, without argument, and asks the model to name specifically what changed its mind. Enthusiastic agreement on pass one will be treated as a failure signal indicating the POV restates consensus. Verbatim transcripts and a "what moved" analysis will be attached for the Sunday submission.

---

## 7. Traceability table

Every row states the POV, what it forces into the build, and the number that would show it was wrong. No row is satisfied yet — no code exists at time of submission.

| # | POV | What it forces me to build | How I will know it was wrong |
|---|---|---|---|
| 1 | POV 1 | Matched-pair transfer harness: 30 cards × 2 reworded exam-style items each | Correlation between card recall probability and paraphrase accuracy. r > 0.7 falsifies the gap |
| 2 | POV 1 | Performance score computed independently of Memory score; never blended | Paraphrase-test gap. If the gap ≈ 0, the performance model is copying the memory model |
| 3 | POV 1 | Congruency-aware card structuring — the thesis feature ablated in §9 | Three-arm comparison at equal study time. No advantage over plain cards = moderator not actionable |
| 4 | POV 2 | All three scores ship with ranges; Brier score, log loss, reliability curve on held-out reviews | Reliability curve deviation from diagonal, stratified by probability band |
| 5 | POV 2 | Give-up rule gating on review count, coverage, **and response-latency plausibility** | % of sessions where scoring is refused; correctness of refusals on adversarial input |
| 6 | POV 2 | Never report accuracy for the pass/fail classifier | Brier and log loss vs an always-predict-pass baseline at the 91% base rate |
| 7 | POV 3 | Coverage map to the official USMLE content outline, not vendor tags | % of outline covered; app abstains below stated threshold |
| 8 | POV 3 | One engine consuming both card-level FSRS memory state and novel-item performance | Does the performance model read per-card D/S/R? Verifiable in code, yes or no |
| 9 | POV 1 + 3 | Rust change: per-topic mastery query returning mastery and average recall over 50,000 cards | Benchmark p50/p95/worst-case; dashboard first load under 1s |

**Provisional decision, flagged as open:** the Rust change is currently scoped to the mastery query (option 3 in the brief's §8) because all three scores plus the coverage map depend on per-topic aggregation being fast enough for the dashboard on a 50,000-card collection, which is a genuine reason for it to live in Rust rather than Python. The points-at-stake queue remains a candidate if the ablation needs the thesis feature to sit in the scheduler itself.

### The give-up rule, written down

The app refuses to report a score when any of the following hold:

- **Memory:** fewer than 200 graded reviews. *(Mirrors FSRS's own optimizer gate, which falls back to default parameters rather than fitting noise — precedent from the codebase being forked, not an invention of mine. Exact constant marked UNVERIFIED pending the fork.)*
- **Performance:** fewer than 50 scored novel items.
- **Readiness:** both of the above, **and** at least 50% coverage of the official USMLE content outline.
- **Any score:** if a session's median response latency falls below 20% of the item's target time, that session is flagged and excluded from scoring inputs. *(This rule exists because I ran that exact adversarial probe against three commercial tools and all three responded with a number.)*

---

## 8. What changed

**PENDING — Sunday deliverable.** One update already belongs here, recorded now because it happened during research rather than during the build:

**POV 1 was rewritten after contact with the evidence.** My original thesis was that retrieval practice fails to transfer to vignette-style items. Pan & Rickard state the opposite — transfer is *greatest* to application and inference questions and to problems involving medical diagnoses. The original claim was not merely unsupported; the keystone citation contradicts it. The surviving POV is narrower and conditional: transfer is real but governed by measurable moderators that nothing in the market measures. A second prediction also failed — I predicted the incumbent's science page would not mention transfer, and it does, citing the strongest study against me.

---

## Licensing

This project is a fork of Anki, licensed **AGPL-3.0-or-later**, with portions contributed by Anki users under **BSD-3-Clause**. Credit to Damien Elmes and the Anki contributors. The fork is public and remains under AGPL-3.0-or-later.
