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
| Appendix A — Thesis test design (brief §9) | **NOT WRITTEN** — stub only; referenced from POV 1 and §7 |
| Appendix B — Score model and calibration plan (brief §10) | **NOT WRITTEN** — stub only; every §7 threshold depends on it |

Additional known gaps, disclosed rather than hidden:

- **Teardown depth.** Three tools observed hands-on (MDSteps, AMBOSS, 7Sage). A fourth (Anki/AnkiHub/AnKing) is covered by vendor documentation plus database inspection, not full UI observation. UWorld is covered by documented claims only — excluded on cost, labeled as such throughout.
- **Zero-effort probe.** All hands-on sessions were answered at 1–4 seconds per item against ~90-second targets. This was deliberate (see §4.3) and is disclosed everywhere it is used. It licenses claims about tool behavior on worthless input. It licenses **nothing** about these tools' accuracy under genuine study.
- **Source verification — now resolved, with two claims falsified.** Source-code citations were previously marked UNVERIFIED because `git clone` was blocked by an egress proxy and GitHub's rendered line gutter was unreadable through the fetch layer. None were upgraded by guessing a plausible line number. They have since been checked against a full clone pinned to commit `d735cd25`; the audit is in `speedrun-docs/source-citations.md`. **Two claims did not survive:** the FSRS optimizer review-count threshold I cited in §7 does not exist, and my revlog SQL approximation was over-inclusive. Both corrections are recorded in §8 rather than quietly applied.
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

### POV 1 — the thesis tested in Appendix A (assignment brief §9)

> **Consensus says** more cards means more readiness — the market's flagship deck ships 28,000 notes to 185,000 subscribers, and three published studies show a dose-response between card volume and Step 1 score.
>
> **I think** card mastery's predictive power degrades as item DOK rises, and that transfer is governed by three *measurable* moderators — response congruency, initial retrieval accuracy, and elaboration — none of which any shipping tool measures or optimizes. FSRS optimizes *when* you see a card. Nothing optimizes whether the card's response structure resembles the item you will actually face.
>
> **My evidence:** Pan & Rickard — transfer falls to d = 0.28 when the required response differs from training, versus an estimated 0.58 when it matches, and rises with initial accuracy at 0.0058 per percentage point, vanishing entirely at very poor initial performance. Winter et al. — mature-card count is the only independent CBSE predictor at R² = 0.427, leaving 57% unexplained. Frappa et al. — the Anki association holds for Step 1 and vanishes for Step 2 CK (p = 0.440), the higher-DOK assessment.
>
> **What would prove me wrong:** if FSRS-derived memory mastery predicts vignette accuracy at r > 0.7 on matched paraphrase pairs, the gap I am claiming is not there. If the congruency-structured condition shows no advantage over plain cards at equal study time in the Appendix A ablation (assignment brief §9), the moderator is not actionable even if it is real.
>
> **Known counter-evidence:** Price et al. (2025), 26,000+ physicians, found spaced repetition improved retention *and* transfer. My claim is conditional, not a denial — but this is the study that would most likely defeat a stronger version of it.

### POV 2 — calibration

> **Consensus says** a readiness number is a readiness number; students want one figure.
>
> **I think** every uncalibrated point estimate in this market is overconfident, and the damning part is that the machinery to band it is already present and deliberately discarded. AMBOSS runs an IRT theta model — which produces a standard error by construction — and prints "0%" and "28.5%" bare. 7Sage projects onto the official scale while displaying, one column over, that every answer arrived 80 seconds early.
>
> **My evidence:** zero of three tools observed hands-on displayed any band, range, or confidence indicator. The only instrument in the space that publishes a validated model — NBME's CBSSA — attaches a ±4 likely-score range, an annual model-update date, and an explicit statement that 90% still means 1 in 10 will fail. The honest instrument is the non-commercial one.
>
> **Additional evidence — and it is not all in my favour.** Anki once enforced a review-count gate on FSRS optimization and then removed enforcement in two steps ([PR #3106](https://github.com/ankitects/anki/pull/3106), 2024-04-05, on the parameter optimizer; [PR #3246](https://github.com/ankitects/anki/pull/3246), 2024-06-28, on minimum recommended retention), leaving `AnkiError::FsrsInsufficientReviews` and `deck-config-must-have-400-reviews` in the tree as dead code. That a serious project built an abstention gate is weak support for abstention being a real design concern. That the same project *removed* it, on benchmark evidence, is stronger evidence against my particular threshold. Both directions are recorded here rather than only the convenient one.
>
> **What would prove me wrong (1):** back-test incumbent point estimates against outcomes. If their reliability curves already sit within ±5% of the diagonal, they are calibrated and simply do not display it, and my criticism reduces to a UI complaint.
>
> **The strongest surviving objection to this POV is shrinkage, not calibration.** Every criticism above assumes the alternative to a bare point estimate is a *band or a refusal*. It is not. The third option is a shrunk estimate: report a number, but pull it toward a known-good prior in proportion to how little data supports it. Upstream chose exactly this when it retired its own gate — Damien Elmes's "stop showing an error, and just fall back on the default parameters instead," and Expertium's weighted blend in [fsrs-optimizer#116](https://github.com/open-spaced-repetition/fsrs-optimizer/issues/116). If shrinkage dominates abstention, then my complaint against the incumbents narrows sharply: they would be wrong to omit the band, but not wrong to emit a number.
>
> **My response, and it is a conditional one.** The mechanism depends entirely on whether an informative prior exists, and that differs by score. For Memory it does — FSRS ships default parameters fitted across ~20k collections — so shrinkage is right and I have adopted it (§7). For Readiness it does not. The only available population prior is the first-attempt pass rate (91% US MD, 86% US DO, 73% IMG), which is a near-constant that already encodes the answer. Shrinking toward it tells every data-poor student they will pass at roughly the base rate, which is the *exact* degenerate classifier §1 forbids. **Shrinkage is not a universal improvement on abstention; it is an improvement wherever the prior carries information the student does not already have.** Where the prior is the answer, abstention is the only honest mechanism.
>
> **Abstention now has to beat four rivals, not one.** The A6 audit of `fsrs-rs` v6.6.0 found that upstream's answer to thin data is not one mechanism but a stack of them, and each is a distinct alternative my give-up rule must outperform rather than assume away: (i) **hard refusal below a floor**, which upstream does apply — at 8 items, 25× below my 200; (ii) **partial fitting**, estimating only the parameters the data can support and defaulting the rest (the 8–63 band); (iii) **regularization toward a prior**, as an L1 penalty on distance from the default rather than an explicit weighted average; and (iv) **accept-only-if-better**, fitting freely and then discarding the result unless it beats the incumbent on log loss. The fourth is the one I find most threatening to my position, because it needs no threshold at all — it tests the thing a threshold is only a proxy for. Appendix B must compare against it directly, and a give-up rule that cannot beat "fit it and check whether it helped" is not defensible merely because it is more cautious.
>
> **What would prove me wrong (3) — the load-bearing test.** If a shrinkage estimator toward the population base rate outperforms abstention on Brier score in the low-data regime, then abstention is the wrong mechanism and POV 2 needs rewriting, not patching. This is a direct empirical comparison on held-out reviews, it is scheduled for Appendix B (assignment brief §10), and I have no result yet. Note the asymmetry that makes this a real test rather than a safe one: abstention cannot be scored by Brier at all on the sessions where it fires, so the comparison has to be run on the sessions where *both* would have produced an output, and abstention has to justify the information it destroys on the rest.
>
> **What would prove me wrong (2) — NOT FIRED. Correcting an overstatement of my own.** An earlier revision of this section claimed this falsifier had fired, on the strength of [issue #3094](https://github.com/ankitects/anki/issues/3094)'s finding that **"after approximately 16 reviews optimising FSRS performs better than the default parameters."** That was a scoping error and I am retracting it. The 16-review benchmark compares **fitting custom parameters against using default parameters**. My give-up rule governs **whether to show a student a score at all**. Those are different operations with different loss functions, and a result about the first does not transfer to the second. Nothing in #3094 tested abstention.
>
> What #3094 does establish is narrower but still uncomfortable: at the point Anki's maintainers were willing to fit parameters, the data requirement was of order tens of items, not hundreds. That is a reason to distrust 200 as a *magnitude*. It is not evidence that abstention is the wrong *mechanism*. The mechanism question is falsifier (3), which remains open and untested.
>
> A second objection from the same thread is independently damaging and does survive: raw graded-review count is the wrong unit, because a user can log 1,000 reviews that are all *first* reviews and yield zero trainable items. My original rule counted graded reviews; §7 now counts `fsrs_items`. **The 200 figure has no empirical backing and must be re-derived against held-out data or abandoned — but on grounds of provenance (§8) and unit error, not because a benchmark refuted it.**

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
| 3 | POV 1 | Congruency-aware card structuring — the thesis feature ablated in Appendix A (assignment brief §9) | Three-arm comparison at equal study time. No advantage over plain cards = moderator not actionable |
| 4 | POV 2 | All three scores ship with ranges; Brier score, log loss, reliability curve on held-out reviews | Reliability curve deviation from diagonal, stratified by probability band |
| 5 | POV 2 | Give-up rule, **split by score**: shrinkage for Memory and Performance, abstention for Readiness, plus coverage and **response-latency plausibility** gates | Brier score of shrinkage vs abstention in the low-data regime, per score. If shrinkage toward the population base rate beats abstention on Readiness, the split is wrong and POV 2 needs rewriting |
| 6 | POV 2 | Never report accuracy for the pass/fail classifier | Brier and log loss vs an always-predict-pass baseline at the 91% base rate |
| 7 | POV 3 | Coverage map to the official USMLE content outline, not vendor tags | % of outline covered; app abstains below stated threshold |
| 8 | POV 3 | One engine consuming both card-level FSRS memory state and novel-item performance | Does the performance model read per-card D/S/R? Verifiable in code, yes or no |
| 9 | POV 1 + 3 | Rust change: per-topic mastery query returning mastery and average recall over 50,000 cards | Benchmark p50/p95/worst-case; dashboard first load under 1s |

**Provisional decision, flagged as open:** the Rust change is currently scoped to the mastery query (option 3 in the brief's §8) because all three scores plus the coverage map depend on per-topic aggregation being fast enough for the dashboard on a 50,000-card collection, which is a genuine reason for it to live in Rust rather than Python. The points-at-stake queue remains a candidate if the ablation needs the thesis feature to sit in the scheduler itself.

### The give-up rule, written down

**One blanket refusal rule was wrong.** The three scores have different priors available to them, and the right mechanism follows from that, not from a single policy applied uniformly. The split below is the correction.

**Unit change, applied throughout: `fsrs_items`, not graded reviews.** The denominator is not a quantity I get to define — it is the count Anki computes and hands back to callers in the `ComputeFsrsParamsResponse`, and whose doc comment instructs callers to inspect it in place of the gate Anki does not apply. Using anything else means measuring something the engine does not.

Counting graded revlog rows overcounts in three separate ways, all verified against [`fsrs_items_for_training`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L351):

1. **A card's first review yields nothing** — items are emitted only from index ≥ 1 ([`params.rs:506`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L506)).
2. **Same-day repeats yield nothing** — the same guard requires `delta_t > 0`, so drilling one card six times in an afternoon contributes at most one item.
3. **Cram reviews are dropped before item construction** ([`params.rs:412`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L412)).

A card with *k* qualifying reviews therefore yields **up to *k* − 1** items, and a student who does 1,000 first-reviews of 1,000 new cards has 1,000 graded reviews and **zero** `fsrs_items`.

**Every numeric threshold below is TBD and must be derived from the Appendix B calibration analysis (assignment brief §10), not asserted.** This is not hedging. The previous figure — 200 — was **lifted from the worked example in the assignment brief, not derived from anything**, and then defended with a fabricated appeal to upstream precedent. A threshold that is an *input* to the calibration analysis cannot also be validated by it. See §8.

| Score | Mechanism | Why this mechanism | Threshold |
|---|---|---|---|
| **Memory** | Shrinkage toward default FSRS parameters | An informative prior exists and is already in the product: FSRS ships default parameters fitted across ~20k collections, and upstream's own benchmark says fitting beats them from roughly 16 items. Refusing to report is strictly worse than reporting a shrunk estimate when the fallback is that good. | Shrinkage weight `n / (50 + n)`, *n* = `fsrs_items`. Constant 50 is TBD — see caveat below. |
| **Performance** | Shrinkage toward a topic-level prior, **plus** abstention below a floor | A topic-level prior is informative (other students' performance on that topic), so shrinkage applies. But unlike Memory there is no validated population model underneath it, so a floor remains where the prior itself is unmeasured. | Minimum scored novel items: **TBD by calibration.** |
| **Readiness** | **Abstention. No shrinkage.** | Shrinkage requires an informative prior, and here the prior is the first-attempt pass rate — 91% US MD, 86% US DO, 73% IMG (§1). Shrinking toward it means telling every low-data student they will pass, at 91% confidence, on no evidence. That is a degenerate constant wearing a probability's clothing, and it is precisely the failure §1 already forbids by banning accuracy as a metric. A prior that encodes the answer you are trying to measure is not a prior; abstention is the only honest response. | Requires both component floors **and** ≥ 50% coverage of the official USMLE content outline. All TBD. |

**What upstream actually does below the floor — the precedent I earlier said did not exist.** An initial audit concluded there was no low-data handling anywhere upstream. That was wrong: it searched Anki's `rslib` and stopped at the crate boundary. `compute_params` delegates fitting to `fsrs-rs`, and that crate applies a graduated ladder rather than a single rule (read at v6.6.0, [`56a78d97`](https://github.com/open-spaced-repetition/fsrs-rs/commit/56a78d971e73c16d2e9a757edfdc3d9e1f0b3695); Anki pins 6.6.1, which carries no git tag — the gap is unverified):

| `fsrs_items` | What upstream does |
|---|---|
| **< 8** | **Refuses to fit.** Returns `DEFAULT_PARAMETERS` unchanged ([`training.rs:319`](https://github.com/open-spaced-repetition/fsrs-rs/blob/56a78d971e73c16d2e9a757edfdc3d9e1f0b3695/src/training.rs#L319)) |
| **8 – 63** | Fits four initial-stability parameters only; takes the rest from defaults; no gradient training ([`training.rs:333`](https://github.com/open-spaced-repetition/fsrs-rs/blob/56a78d971e73c16d2e9a757edfdc3d9e1f0b3695/src/training.rs#L333)) |
| **≥ 64** | Full training, initialized from the above |
| **> 300** | Only now does Anki run the FSRS health check ([`params.rs:182`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L182)) |

Throughout, two shrinkage mechanisms operate: an **L1 penalty** pulling initial stability toward the default (`(init_s0 - default_s0).abs() / 16.0`) and **Laplace smoothing** of per-bucket recall toward the collection average. And Anki discards a fitted result outright if it fails to beat the existing parameters on log loss ([`params.rs:156`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L156)).

**Three things follow, and only the first is comfortable.** (1) The shrinkage design above is better supported than I thought — upstream shrinks toward defaults in two places. (2) My 200 is **25× stricter** than the strictest refusal upstream applies, which makes it harder to defend, not easier. (3) Every one of these mechanisms governs *whether to fit a model*, never *whether to show a student a number*. **The reporting decision has no precedent anywhere in the stack.** It is ours, and Appendix B has to earn it.

**Caveat on the shrinkage constant, stated because I got this wrong once already.** The `n / (50 + n)` form is taken from [fsrs-optimizer#116](https://github.com/open-spaced-repetition/fsrs-optimizer/issues/116), where Expertium proposes it for smoothing **median review times**, not FSRS parameters:

> "Here `n_reviews` is the number of times the user pressed this particular button, `t_user` is the median time per button estimated from the user's data, and `t_default` is the default median time, estimated from 20k collections. 50 is a constant that determines how quickly the 'smooth' value transitions from the default value to the actual value […] The key idea is that when the number of times the user presses a button is very small, the estimate is not very accurate, and we should rely more on the default time, which we know is accurate."

**I am borrowing the functional form and the reasoning, not a precedent for shrinking FSRS parameters.** No upstream code shrinks FSRS parameters. The Anki-side implementation of #116 shrank *first-rating probabilities* (`DEFAULT_FIRST_RATING_PROB`) in `retention.rs`, and **that code no longer exists** — it was deleted in [`52ce6e6a`](https://github.com/ankitects/anki/commit/52ce6e6a6) ("Feat/FSRS-5", PR #3298). There is no `n / (50 + n)` shrinkage anywhere in `rslib` at commit `d735cd25`. The constant 50 was chosen for review-time medians in a different estimator and carries **no authority** for this application; it is a starting value to be fitted in Appendix B, not a borrowed result.

The app additionally refuses to report any score when:

- **Any score:** if a session's median response latency falls below 20% of the item's target time, that session is flagged and excluded from scoring inputs. *(This rule exists because I ran that exact adversarial probe against three commercial tools and all three responded with a number.)*

---

#### Retracted: the original blanket rule

The rule below is preserved as written for the §8 audit trail. It is superseded by the table above.

- ~~**Memory:** fewer than 200 graded reviews.~~ *(**Our own design decision, at a magnitude with no upstream support.** A later pass found that refusal-below-a-floor *is* upstream precedent after all, at **8** items inside `fsrs-rs` — see the ladder above and Finding G. What has never had precedent is refusing at 200, or refusing to *report a score* as opposed to refusing to *fit a model*.* The earlier claim that this "mirrors FSRS's own optimizer gate" was false and is retracted — see §8. [`Collection::compute_params`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/scheduler/fsrs/params.rs#L78) does not gate on review count at all; its own doc comment says it "does not return an error if there are less than 400 items — the caller should instead check the `fsrs_items` count in the return value." Anki did once enforce such a gate — 1,000 reviews as of [`66d0046b8`](https://github.com/ankitects/anki/commit/66d0046b8a847df3b460207ed4ed52964da44063) (2024-01-08), later 400 — but enforcement was removed from the **parameter optimizer** in [PR #3106](https://github.com/ankitects/anki/pull/3106) ([`10d567f9`](https://github.com/ankitects/anki/commit/10d567f93744ca2d5fb9593f0922475df573c2f9), 2024-04-05) and from **`compute_minimum_recommended_retention`** in [PR #3246](https://github.com/ankitects/anki/pull/3246) ([`6d13221a`](https://github.com/ankitects/anki/commit/6d13221ae50014e42338213d737e28b3af83d6df), 2024-06-28). What survives is dead code: [`AnkiError::FsrsInsufficientReviews`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/rslib/src/error/mod.rs#L120) has no construction site anywhere in the tree, and its string [`deck-config-must-have-400-reviews`](https://github.com/ankitects/anki/blob/d735cd25d076051c6788b5a5acf65b57b9ea7277/ftl/core/deck-config.ftl#L391) is unreachable UI text. Full derivation in `speedrun-docs/source-citations.md`, Findings A and B. **The stated reason for the removal cuts against this rule — see POV 2's falsifier, which has already fired.**)*
- ~~**Performance:** fewer than 50 scored novel items.~~ *(50 was also taken from the brief's example, not derived.)*
- ~~**Readiness:** both of the above, **and** at least 50% coverage of the official USMLE content outline.~~ *(The coverage condition survives into the new rule; the review-count condition does not.)*

The latency rule is unchanged and carried forward above.

---

## 8. What changed

**PENDING — Sunday deliverable.** Three updates already belong here, recorded now because they happened during research rather than during the build:

**The FSRS abstention precedent did not exist, and I had asserted it.** §7's give-up rule claimed the 200-review Memory gate "mirrors FSRS's own optimizer gate, which falls back to default parameters rather than fitting noise — precedent from the codebase being forked, not an invention of mine." Once the fork was cloned and the claim could actually be checked, it failed. `compute_params` does not gate on review count; its doc comment explicitly says it does not error below 400 items and pushes the decision to the caller. Worse for me, Anki *did* once enforce such a gate and **deliberately removed enforcement** — from the parameter optimizer in PR #3106 (2024-04-05) and from minimum recommended retention in PR #3246 (2024-06-28) — leaving `AnkiError::FsrsInsufficientReviews` and `deck-config-must-have-400-reviews` behind as unreachable dead code. So the design I cited as lineage is code upstream decided to delete.

The correction runs deeper than attribution, but not as deep as I first claimed. The benchmark behind the removal ([issue #3094](https://github.com/ankitects/anki/issues/3094)) found fitted parameters outperforming defaults from **~16 reviews**, against my gate of 200. An earlier revision of this section read that as having falsified the give-up rule outright. **That was an overstatement and is retracted:** #3094 compares *fitting against defaults*, whereas the give-up rule governs *reporting against abstaining*. Different operations. What survives is a reason to distrust 200 as a magnitude, not evidence against abstention as a mechanism — see POV 2, falsifiers (2) and (3).

**The corrected version is stronger, but not because it survived intact.** It is stronger because the rule is now labelled as my own design decision defended on my own terms, instead of borrowing authority from a codebase that does the opposite; because the 200 figure is now explicitly flagged as unbacked and owing a derivation; and because the failure mode this exposes — asserting a source-code fact I had not read, in a section whose entire purpose is traceability — is exactly the failure the give-up rule exists to prevent. I ran a rule against myself that I had not yet run against my own citations. Three further claims were checked at the same time: "400 is dead code" was **confirmed**, my revlog SQL approximation was **falsified** (it failed to exclude cram reviews, inflating every review count I had computed), and the insufficient-data string was **verified** verbatim. Full audit trail in `speedrun-docs/source-citations.md`.

**The give-up rule's thresholds were inherited, not derived — and they were pointed the wrong way round.** The assignment brief's Section 5 reads, verbatim: *"Example: no score below 200 graded reviews and 50% topic coverage."* **Both** numbers in my give-up rule came from that one illustrative sentence — the 200-review Memory gate and the 50% coverage floor for Readiness. Neither was computed from anything. Having taken two numbers from an example, I then went looking for authority for them and asserted an FSRS precedent I had not read. That ordering is the actual defect: the thresholds were fixed first and justified afterwards.

**Three different 50s, stated separately because conflating them is easy and I nearly did.** (1) **50% topic coverage** — from the brief's example, as above. (2) **50 scored novel items**, the Performance floor — origin *not* the brief; I cannot now reconstruct where it came from, so it is recorded as **UNKNOWN provenance** rather than attributed to a source it did not come from. (3) **The shrinkage constant 50** in `n / (50 + n)` — from [fsrs-optimizer#116](https://github.com/open-spaced-repetition/fsrs-optimizer/issues/116), where it was tuned for smoothing median *review times* in a different estimator. It has nothing to do with the brief and no authority for this application. All three are TBD pending Appendix B.

The structural fix is to invert the dependency.

A give-up threshold must be an **output** of the calibration analysis, not an **input** to it — the point at which reporting a score stops beating abstaining is a measurable quantity on held-out reviews, and measuring it is the same work as producing the reliability curves POV 2 already demands. A threshold asserted up front and then "validated" by an analysis it constrains is circular, and it is the same circularity I criticise AMBOSS for in §4.2: computing the machinery that would produce an honest bound and then not using it. Every numeric threshold in §7 is now marked TBD pending Appendix B, and the rule has been split by score so that the *mechanism* — shrinkage where an informative prior exists, abstention where it does not — is decided on stated reasoning rather than inherited along with the number.

**POV 1 was rewritten after contact with the evidence.** My original thesis was that retrieval practice fails to transfer to vignette-style items. Pan & Rickard state the opposite — transfer is *greatest* to application and inference questions and to problems involving medical diagnoses. The original claim was not merely unsupported; the keystone citation contradicts it. The surviving POV is narrower and conditional: transfer is real but governed by measurable moderators that nothing in the market measures. A second prediction also failed — I predicted the incumbent's science page would not mention transfer, and it does, citing the strongest study against me.

---

## Appendix A — Thesis test design (assignment brief §9)

**NOT WRITTEN.** Corresponds to **§9 of the assignment brief**, not to a ninth section of this document — BRAINLIFT's own required contents run to eight items, so a bare "§9" was ambiguous and every reference now names which document it means. Referenced from POV 1, §7 (traceability rows 1 and 3) and `rust-change-note.md`; the stub exists so those cross-references resolve rather than dangling.

Planned: the three-arm comparison at equal study time — plain cards, congruency-structured cards, and the matched-pair transfer harness (30 cards × 2 reworded exam-style items). The falsifier is stated in POV 1: no advantage over plain cards means the moderator is not actionable even if it is real.

---

## Appendix B — Score model and calibration plan (assignment brief §10)

**NOT WRITTEN.** Referenced from §7 and POV 2 as the source of every numeric threshold in the give-up rule. Stub added for the same reason as Appendix A.

This section owes four things, and until it exists no threshold in §7 has support:

1. **Reliability curves** for each of the three scores on held-out reviews, stratified by predicted-probability band, with Brier score and log loss — and never accuracy (§1).
2. **The abstention-vs-shrinkage comparison** that POV 2's third falsifier turns on: does a shrinkage estimator toward the population base rate beat abstention on Brier score in the low-data regime? Run on the sessions where both mechanisms would emit an output, with abstention separately accountable for the information it destroys elsewhere.
3. **Derived thresholds** — the review-pair count for Memory, the scored-item floor for Performance, the coverage floor for Readiness — each read off the point where reporting stops beating abstaining, rather than asserted and then checked.
4. **The fitted shrinkage constant**, replacing the 50 borrowed from [fsrs-optimizer#116](https://github.com/open-spaced-repetition/fsrs-optimizer/issues/116), which was chosen for smoothing median review times in a different estimator and has no authority here.

---

## Licensing

This project is a fork of Anki, licensed **AGPL-3.0-or-later**, with portions contributed by Anki users under **BSD-3-Clause**. Credit to Damien Elmes and the Anki contributors. The fork is public and remains under AGPL-3.0-or-later.
