# AI Consensus Check — verbatim transcripts

## Run metadata

- **Model:** claude-sonnet-4-6, Anthropic Messages API
- **Context:** fresh, no access to BRAINLIFT.md, the repo, or any prior conversation
- **max_tokens:** 1000 per pass
- **POV framing:** supplied as a third party's claim ("A researcher makes the following claim. Assess it.") rather than first person, to reduce politeness bias
- **Protocol:** pass one cold with no evidence; pass two supplies the evidence packet once, without argument, with instructions forbidding agreement that cannot name a specific cause
- **Runs:** one. No re-rolls.
- **Known defect:** pass two is truncated mid-sentence by the 1000-token cap. The cut is preserved exactly as returned and is not reconstructed.

---

## POV as supplied (pass one input)

> Consensus says that more flashcards means more exam readiness — the market's flagship USMLE Step 1 deck ships 28,000 notes to 185,000 subscribers, and multiple published studies show a dose-response between flashcard volume and Step 1 score.
>
> I think card mastery's predictive power degrades as item complexity rises, and that transfer from memorized facts to novel exam vignettes is governed by three measurable moderators — response congruency, initial retrieval accuracy, and elaboration — none of which any shipping study tool measures or optimizes. Spaced-repetition schedulers optimize WHEN you see a card. Nothing optimizes whether the card's response structure resembles the item you will actually face on the exam.

*(Note: this is the POV as it stood at the time of the check. It has since been revised in response to objections 1 and 3 — see §5.)*

---

## PASS ONE — cold, no evidence

ASSESSMENT

This claim is partly contrarian and partly a restatement of well-established cognitive science dressed up as novel critique. The core theoretical points — that transfer depends on encoding specificity, retrieval practice quality, and elaboration — are consensus findings in learning science going back decades (Tulving & Thomson, 1973; Roediger & Karpicke, 2006; Chi et al. on elaborative interrogation). The researcher is not discovering these moderators; they are applying them to a specific applied context where they are underexplored. That is worth doing, but the framing as original theoretical insight is overstated. The claim that "nothing optimizes" these moderators is empirically testable but asserted without evidence. The opening characterization of the consensus position is also a strawman.

---

OBJECTIONS

1. The "consensus" position is fabricated. The researcher claims the field holds that more flashcards means more exam readiness. No serious learning scientist holds this. The relevant literature emphasizes quality of retrieval, spacing, and interleaving — not raw volume. The researcher has constructed a naive straw consensus to make the contrarian claim easier to land. Ankidroid's market dominance is a commercial fact, not an epistemic claim by the field.

2. The dose-response evidence is mischaracterized. The researcher says "multiple published studies show a dose-response between flashcard volume and Step 1 score." This needs immediate scrutiny. Most correlational studies in this area confound volume with total study time, engagement, prior knowledge, and self-regulation. A dose-response between card count and score is not the same as a causal relationship between volume and learning. If these studies exist as described, they almost certainly cannot distinguish between "more cards caused better scores" and "more disciplined students use more cards and also score higher."

3. The three moderators are real but not novel, and two are already partially addressed. Response congruency maps onto transfer-appropriate processing, a well-documented framework. Initial retrieval accuracy maps onto the well-established finding that testing below-threshold retrieval (i.e., failing to retrieve at all) is less effective than desirable difficulty — also not new. Elaboration is a standard finding. The claim that "no shipping study tool measures or optimizes" these is asserted flatly. Anki's algorithm does factor in retrieval accuracy (the "Again/Hard/Good/Easy" grading directly encodes it). The researcher may mean that current tools don't optimize these well or exhaustively, which is a weaker and more defensible claim.

4. "Card mastery's predictive power degrades as item complexity rises" is stated as a hypothesis but supported only by theoretical reasoning. This is the most interesting empirical claim in the passage and the least supported. Where is the evidence that the predictive validity of Anki retention actually flattens or inverts at higher Bloom's levels? Without data showing that mastery of complex cards specifically fails to transfer — relative to simple cards — this is an untested assumption scaffolding the rest of the argument.

5. The USMLE Step 1 context cuts against the researcher's framing in one important way. Step 1 has a high factual load. A meaningful proportion of vignette-based questions are still anchored in recognition of discrete facts (receptor pharmacology, enzyme deficiencies, pathogen characteristics). The researcher's framework may be most powerful in contexts where near-transfer is rare. For Step 1 specifically, the proportion of items where response congruency actually fails deserves an empirical answer, not an assumption.

6. "Response structure resembles the item you will actually face" is undefined with enough precision to be measured. The construct of response congruency needs operationalization before the claim that tools fail to optimize it can be evaluated. How similar does a card response need to be to a four-option vignette response to count as congruent? Without a measurement model, this is an unfalsifiable design principle dressed as a testable claim.

7. The researcher implies that optimizing these three moderators would meaningfully improve outcomes, but offers no effect size estimate or comparison. Even if all three moderators are valid and measurable, it's possible their combined effect on Step 1 score variance is small relative to total study time, baseline aptitude, or other factors. The policy implication — that tools should be redesigned around these moderators — is not justified without knowing how much variance they actually explain.

---

## PASS TWO — evidence supplied once, no argument

OBJECTION STATUS

**Objection 1 (strawman consensus):** ANSWERED by items 2 and 6. The flagship deck's own marketing claims transfer while its course structure outsources application to question banks. The commercial ecosystem operationally endorses the volume-equals-readiness framing even if academic learning scientists do not. The strawman critique of the researcher's framing loses most of its force.

**Objection 2 (dose-response confounded):** ANSWERED by item 2. Mature-card count from objectively logged data as the only independent predictor, with R²=0.427, is substantially stronger than typical self-report correlational work. Confounding is not eliminated but is meaningfully reduced.

**Objection 3 (moderators not novel, tools partially address them):** SURVIVES in part. Pan & Rickard (item 1) confirms all three moderators are real and quantified. But the novelty objection survives: these are established findings being applied, not discovered. The partial-address objection is answered — Anki's grading encodes retrieval accuracy crudely, but no tool closes the loop on whether transfer actually occurred for a given student, which item 6 confirms directly.

**Objection 4 (complexity-degradation hypothesis unsupported):** ANSWERED by item 3. Same tool, same students, Step 1 association significant, Step 2 CK association absent after controls. This is the cleanest piece of evidence in the set. It is a natural experiment in complexity, not a randomized design, but the effect is the pattern the researcher predicted.

**Objection 5 (Step 1 factual load cuts against the claim):** ANSWERED by item 3 in the same move. If Step 1's factual anchor were sufficient to make card mastery predictive regardless of complexity considerations, the Step 2 CK null would need a different explanation. The researcher's framework provides the most parsimonious one.

**Objection 6 (response congruency undefined and unmeasurable):** SURVIVES. Item 1 quantifies the moderator's effect but the operationalization problem remains. Pan & Rickard define congruency at the level of experimental conditions; no one has produced a student-level instrument that scores congruency between a specific Anki card and a specific vignette item. The claim that tools fail to optimize an unmeasured construct is still not falsifiable at the individual card level.

**Objection 7 (effect size and variance unestablished):** PARTIALLY ANSWERED. Item 1 gives d=0.30 for congruency and d=0.23 for elaboration — modest but non-trivial. Item 2's R²=0.427 confirms ~57% of CBSE variance is unexplained by card mastery, which is the space the researcher claims these moderators occupy. Whether they explain that residual variance is still undemonstrated, but the residual is real and large.

---

WHAT MOVED ME

Item 3 moved me most. The Step 1 versus Step 2 CK dissociation — same tool, same students, significance disappears at higher complexity after controls — is the empirical pattern the researcher's framework predicts and that a pure volume hypothesis cannot easily explain. I had no prior basis to discount it, and the researcher supplied it from a systematic review rather than a single study.

Item 2 moved me on objection 2. Objectively logged mature-card count as the sole independent predictor shifts this from plausible correlation to a finding that survives at least basic confound control.

Item 4 (fluency illusion in two no-benefit studies) moved me on the practical stakes. Self-rated benefit dissociating from measured performance is not a theoretical curiosity — it is a signal that the feedback loop students rely on is broken in exactly the way the researcher claims.

The researcher's own counter-evidence (items 3 note and 5) did not move me against them — Price et al. covers practicing physicians maintaining existing knowledge, not students acquiring and transferring novel clinical reasoning under exam conditions. The populations and transfer demands differ enough that the conflict is less sharp than it appears.

---

WHAT REMAINS THE CRUX

The strongest surviving disagreement is this: the researcher claims that response congruency, initial retrieval accuracy, and elaboration are the governing moderators of transfer failure — but no study has yet measured these variables at the individual

**[TRANSCRIPT ENDS HERE — output truncated at the 1000-token cap. Not reconstructed.]**

---

## Evidence packet as supplied in pass two

1. Pan & Rickard (2018), Psychological Bulletin 144(7):710-756. Meta-analysis, 192 effect sizes, 122 experiments, N=10,396. Overall transfer of retrieval practice d=0.40 [95% CI 0.31, 0.50]. Response congruency: when the transfer item requires a different response than trained, d=0.28; congruency adds an estimated d=0.30, total 0.58. Initial test accuracy: transfer rises ~0.0058 per percentage point and disappears entirely at very poor initial performance. Elaborated retrieval practice adds d=0.23.

NOTE AGAINST MY OWN CLAIM: the same paper finds transfer is GREATEST across changed test formats, to application and inference questions, and specifically to problems involving medical diagnoses.

2. Winter et al., via Frappa et al. (2026) systematic review, Medical Science Educator 36:1015-1025 (11 studies, 1,135 students, PRISMA). Mature-card count was the ONLY independent predictor of CBSE score, B=0.649, p=0.026, R-squared=0.427 — leaving ~57% of variance unexplained by card mastery, from objectively logged data.

3. Same review: Anki use associates with Step 1 across three studies (Lu p=0.012; Deng p=0.024; Wothe p=0.039) but NOT with Step 2 CK (252.5 vs 247.0, p=0.440, not significant, and not an independent predictor after controlling for Step 1 score and class rank). Same tool, same students, higher-complexity assessment, effect vanishes.

4. Same review: two studies found no performance benefit while 87% and 74% of participants rated the intervention favorably (Sun p=0.54; Magro p=0.43). A measured fluency illusion.

5. COUNTER-EVIDENCE I AM SUPPLYING DELIBERATELY: Price et al. (2025), Academic Medicine 100(1):94-102. 26,000+ practicing physicians. Spaced repetition improved knowledge retention AND transfer. This is the largest, cleanest study in the space and it cuts against a strong version of my claim.

6. Market observation: the flagship deck's official course states that application "is done primarily with question banks such as AMBOSS & UWorld" — handing the apply stage to a different vendor — while the same course's science page claims spaced repetition delivers knowledge transfer, citing Price et al. Neither ships any instrument measuring whether transfer occurred for a given student.
