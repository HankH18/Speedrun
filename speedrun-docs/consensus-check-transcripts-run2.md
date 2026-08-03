# AI Consensus Check — Run 2, verbatim transcripts

## Run metadata

- **Model:** claude-sonnet-4-6, Anthropic Messages API
- **Context:** fresh, no access to BRAINLIFT.md, the repo, or any prior conversation
- **max_tokens:** 8000 requested, with automatic continuation on `stop_reason == "max_tokens"` using a purely structural resume prompt. Neither pass required continuation.
- **POV framing:** supplied as a third party's claim ("A researcher makes the following claim. Assess it.")
- **Protocol:** pass one cold; pass two supplies the evidence packet once, without argument, with instructions forbidding agreement that cannot name a specific cause
- **Changes from run 1:** POV revised in response to run 1 objections 1 and 3; evidence packet item 7 added (NBME physician-task weighting)

### ⚠ Provenance note — reconcile before citing

The POV text submitted in run 2 was a **draft supplied in conversation**, not copied out of `BRAINLIFT.md`. It carries the intended objection-1 and objection-3 revisions but may differ in wording from the committed POV 1 in §5. Before §6 treats run 2 as a test of the committed POV, diff the two and either reconcile the file to what was tested or note the divergence explicitly.

---

## Run log — all attempts

| Attempt           | Outcome                                                                                                                                                                                                                            |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Run 1             | Both passes completed. Pass two truncated mid-sentence at the 1000-token cap. Transcript retained in `consensus-check-transcripts.md`.                                                                                             |
| Discarded attempt | Placeholder text left in the POV field. The model correctly declined to assess an incomplete claim. No usable output. Harness subsequently patched to block submission when the field is empty or still contains placeholder text. |
| Run 2             | Both passes completed in full. Reported below.                                                                                                                                                                                     |

---

## POV as submitted (run 2)

> The market's revealed consensus — expressed in what it ships and sells — is that more flashcards means more exam readiness. The flagship USMLE Step 1 deck ships 28,000 notes to 185,000 subscribers, its paid tiers sell content freshness and AI search rather than any measure of learning, and multiple published studies report a dose-response between card volume and Step 1 score. This is a claim about the market, not about the field: no serious learning scientist holds that volume equals readiness.
>
> I think card mastery's predictive power degrades as item complexity rises, and that transfer from memorized facts to novel exam vignettes is governed by three moderators — response congruency, initial retrieval accuracy, and elaboration. These moderators are not my discovery. They are established findings, traceable to transfer-appropriate processing (Tulving & Thomson, 1973) and quantified in later meta-analytic work. My claim is narrower: nothing in this applied context measures or optimizes them.
>
> The nearest counterexample makes the point rather than refuting it. Anki's Again/Hard/Good/Easy grading does encode retrieval accuracy, and FSRS consumes that signal — to time the next review. Nothing uses it to decide what kind of practice a student should get. Recording a variable and optimizing against it are different operations, and the gap between them is where the transfer problem lives.

---

## PASS ONE — cold, no evidence

OBJECTIONS

1. The "dose-response" citation is doing critical work but goes unverified. The claim that "multiple published studies report a dose-response between card volume and Step 1 score" is presented as establishing market consensus. But correlational studies between Anki usage and Step 1 performance (e.g., Schmitz et al., studies cited in medical education journals) typically report hours of use or cards reviewed, not cards owned or deck size. Card ownership is not card review. If the evidence actually shows that review volume — not deck size — predicts scores, the market critique collapses: the market may be selling something students don't use in the way being criticized.

2. The three moderators are asserted without justification for their selection or completeness. "Response congruency, initial retrieval accuracy, and elaboration" are presented as the governing moderators of transfer from flashcards to vignettes, but no argument is made for why these three and not others — interleaving, variability of practice, desirable difficulties more broadly, prior knowledge activation, metacognitive monitoring. Choosing three established constructs and calling them the governing set is not a theoretical contribution; it's a framing choice that needs defense.

3. The Anki/FSRS counterexample is mishandled. The author concedes that FSRS consumes retrieval accuracy signal and then argues this doesn't count because it uses that signal only for scheduling, not for "deciding what kind of practice a student should get." This is a meaningful distinction, but the author then claims the gap "is where the transfer problem lives" without demonstrating that changing practice type based on retrieval accuracy would actually improve transfer outcomes in this domain. That causal claim needs evidence. The gap exists; whether closing it matters for Step 1 performance is an empirical question the author doesn't address.

4. The market claim is analytically weak. "Revealed consensus" inferred from what a product ships is not the same as what users do, what sellers believe about learning science, or what the product implicitly claims. Deck size may reflect content coverage anxiety, not a theory of learning. A 28,000-card deck covering all of Step 1 content could be defended on the grounds of breadth without any claim that volume equals readiness. The author would need evidence about seller intent or user belief — not just product features — to establish the consensus they're critiquing.

5. "Nothing in this applied context measures or optimizes them" is unfalsifiable as stated. The claim that no applied tool optimizes for response congruency, retrieval accuracy, or elaboration ignores that some Step 1 preparation platforms (UWorld, Amboss, question banks generally) do present information in formats congruent with the exam, do track accuracy by domain and question type, and do embed explanatory feedback. The author may mean specifically flashcard tools, but the scope of "this applied context" is never defined, which allows the claim to shift as counterexamples arise.

6. The theoretical framework is not applied to the domain with enough specificity. Transfer-appropriate processing is cited correctly, but the author doesn't demonstrate what response congruency actually requires for Step 1 vignette transfer — what encoding conditions are needed, how far current practice falls short, or how large the effect size might be. Without this, the framework is invoked as credibility rather than applied as analysis.

7. The author conflates a descriptive critique with an implied prescriptive claim. The piece reads as implying that if tools measured and optimized these three moderators, transfer would improve and scores would rise. But that prescriptive claim is never stated or defended. If it's not the claim, the critique loses most of its practical force — it becomes only "tools don't measure X," not "measuring X would help."

---

WHAT WOULD CHANGE MY MIND

Evidence that deck size, independent of review volume and review quality, predicts Step 1 performance would salvage the market analysis. Right now the causal story between "ships 28,000 cards" and "market believes volume equals readiness" is asserted, not shown.

A pre-registered study showing that flashcard-trained medical students who score well on isolated recall items fail to outperform matched controls on novel vignettes testing the same material would substantiate the transfer gap claim in this specific applied domain. The general phenomenon is established; the domain-specific magnitude is not.

Evidence that manipulating response congruency or elaboration depth during flashcard study produces measurable improvement in vignette-based exam performance — beyond what scheduling optimization already achieves — would validate the claim that the gap between recording and optimizing retrieval accuracy is where the transfer problem lives. Without this, "recording ≠ optimizing" is true but may be practically unimportant.

Finally, evidence that students or educators actually hold the belief that volume equals readiness, rather than simply using large decks for coverage, would justify the market framing. Right now that framing is inferential and the inference is weak.

---

## PASS TWO — evidence supplied once, no argument

OBJECTION STATUS

**Objection 1** (dose-response citation unverified; deck size vs. review volume conflated) — ANSWERED by item 2. The Winter et al. / Frappa et al. data uses objectively logged mature-card count as the predictor, not self-reported hours or deck ownership. The regression is specific enough to distinguish mastered cards from deck size. The market analysis gains a firmer empirical footing than I granted it. The B=0.649 result and R²=0.427 are the relevant numbers; I was wrong to treat the citation as unverified.

**Objection 2** (three moderators asserted without justification for completeness) — SURVIVES. Item 1 quantifies the three moderators within retrieval practice literature and the effect sizes are real. But the author still does not argue why these three and not others — interleaving, variability of practice, desirable difficulties, prior knowledge activation — are the governing set for this specific applied context. Pan & Rickard establishes that the three matter; it does not establish that they are the primary bottleneck for Step 1 vignette transfer as opposed to other factors. The selection remains a framing choice that is supported but not defended.

**Objection 3** (FSRS counterexample mishandled; causal claim that closing the gap matters needs evidence) — ANSWERED in part by items 1 and 3. The Pan & Rickard effect sizes give quantitative stakes to the gap: if response congruency adds ~d=0.30 and elaborated retrieval adds ~d=0.23, those are not trivially small. Item 3 — same tool, same students, effect vanishes at Step 2 CK — is the strongest empirical move in the entire submission. It provides a natural experiment: the gap between recording and optimizing retrieval accuracy becomes consequential precisely when item complexity rises, which is what the author predicts. The causal claim is not proven, but the pattern is consistent and the prior objection that "the gap may be practically unimportant" is weakened.

**Objection 4** (market claim analytically weak; "revealed consensus" needs evidence of belief, not just product features) — ANSWERED by item 6. The official course explicitly claims spaced repetition delivers transfer while citing Price et al., and simultaneously outsources application practice to external vendors. That is direct evidence of a stated belief about transfer, not just an inference from product design. The author's self-note in item 5 and item 6 together show the market makes the transfer claim while shipping no instrument to verify it. This objection does not survive.

**Objection 5** ("nothing measures or optimizes" is unfalsifiable; question banks do track accuracy and format) — SURVIVES, but narrowed. Item 6 concedes that application is "handed to a different vendor" — which means the author's claim is scoped to flashcard tools specifically, and the question bank ecosystem is acknowledged rather than ignored. However, the author still does not define the boundary of "this applied context." If UWorld and AMBOSS are in scope, the claim weakens substantially. If they are explicitly out of scope, the claim needs that boundary stated. The unfalsifiability concern is reduced but not eliminated.

**Objection 6** (framework not applied to domain with enough specificity; effect sizes for this population unquantified) — ANSWERED in part by items 3 and 7. Item 3 provides domain-specific evidence of degradation at higher complexity. Item 7 is the author's own candid hedge — it is task weighting, not a measure of response congruency — and I accept that characterization. The domain application remains incomplete, but the author supplies the best available proxy and flags its limitations, which is the intellectually honest move. The objection is weakened, not eliminated.

**Objection 7** (critique implies prescription without defending it) — SURVIVES. Nothing in the evidence package establishes that if tools measured and optimized the three moderators, transfer outcomes would improve in this applied population. Item 1 shows the moderators matter in controlled experiments. Item 5 (Price et al., 26,000+ physicians) shows spaced repetition improved both retention and transfer at scale — and the author supplies this as counter-evidence against themselves. The prescriptive gap remains: the descriptive critique is well-supported; the implied fix is not.

---

WHAT MOVED ME

Three things specifically changed my assessment.

Item 3 is the most important single piece of evidence. The disappearance of the Anki effect at Step 2 CK — same students, same tool, higher-complexity assessment, effect gone — is a natural experiment that the author did not oversell. It is consistent with the complexity-moderates-transfer prediction and it is the kind of domain-specific, within-sample evidence I said was missing.

Item 2 moved me on objection 1. Objectively logged mature-card count as the regression predictor is methodologically cleaner than I assumed the citation to be. I was wrong to treat it as an unverified assertion.

Item 6 moved me on objection 4. A product page that explicitly claims transfer while outsourcing application to another vendor and shipping no transfer measurement is direct evidence of a stated belief, not an inference from product features. That is a real finding about the market, not just a rhetorical observation.

Item 5 (Price et al.) did not move me against the author — they supplied it as counter-evidence themselves — but it appropriately limits how strong a version of the critique is defensible. A very strong claim that spaced repetition cannot produce transfer is not supportable given that paper.

---

WHAT REMAINS THE CRUX

The strongest surviving disagreement is the gap between the descriptive claim and the implied prescriptive one. The author has established, with reasonable empirical support, that applied flashcard tools do not measure or optimize the three moderators, that the transfer effect in this domain is real but bounded, and that complexity moderates it. What is not established is that tools designed to optimize response congruency, initial retrieval accuracy, and elaboration would outperform the current ecosystem — particularly given that question banks, which the official course itself points students toward, already provide formats closer to the exam's response demands.

The author's framework predicts the Step 2 CK finding. It does not yet explain the Price et al. finding, which shows transfer at scale in a high-complexity applied domain using standard spaced repetition. Until those two results are reconciled, the claim that the transfer problem lives specifically in the gap between recording and optimizing retrieval accuracy — rather than in some other feature of the learning environment — remains a hypothesis rather than a conclusion.

---

## Evidence packet as supplied in pass two

Items 1–6 identical to run 1 (see `consensus-check-transcripts.md`). Item 7 added for this run:

7. ADDED IN THIS RUN, bearing on how factual Step 1 actually is: the NBME Comprehensive Basic Science Self-Assessment sample score report weights items by physician task at 60-70% "Medical Knowledge: Applying Foundational Science Concepts", 20-25% "Patient Care: Diagnosis", and 4-6% "Practice-based Learning: Evidence-Based Medicine". The sample examinee scored 74 / 74 / 56 across those three tasks. This is indirect — it is a task weighting, not a measure of response congruency — and it is the closest available evidence on that question.
