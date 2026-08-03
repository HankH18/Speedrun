# AI evals — the checks that need no API key and no source document

BUILD-DOC §7. Pure Python 3, **standard library only**. No dependencies, no
virtualenv, no `pip install`. Every command below exits non-zero on failure.

```
python3 speedrun-analysis/evals/run_evals.py            # all of it, one command
python3 speedrun-analysis/evals/leakage.py --self-test  # 7.5, standalone
python3 speedrun-analysis/evals/retrieval_compare.py    # 7.3, three arms
python3 speedrun-analysis/evals/test_traceability.py    # 7.1, build-error proof
python3 speedrun-analysis/evals/test_ai_off.py          # 7.6, AI off as a test
```

`test_ai_off.py` calls the real Rust `topic_mastery` query. If `anki` is not
importable it re-runs itself under `out/pyenv/bin/python` with `out/pylib` on
the path, and exits **4** if the backend has not been built — never 0.

---

## What has been measured, and what has not

| BUILD-DOC | Check                      | State                                                                                |
| --------- | -------------------------- | ------------------------------------------------------------------------------------ |
| 7.1       | Traceability build error   | **BUILT AND TESTED.** 23 tests, incl. real documents in `../sources/`.               |
| 7.5       | Leakage check              | **BUILT AND SELF-TESTED.** Catches a planted near-copy at containment 0.500.         |
| 7.3       | Retrieval comparison       | **HARNESS BUILT.** Two baselines score; the AI arm is NOT YET RUN. Synthetic corpus. |
| 7.6       | AI off                     | **TESTED**, for the paths that exist. Two of the three scores do not exist.          |
| 7.1       | Card generation            | **NOT RUN.** No source document, no key. No card has been generated.                 |
| 7.2       | Rewording / paraphrase gap | **NOT RUN.** The gap is UNMEASURED, not zero.                                        |
| 7.4       | AI card check              | **NOT RUN.** `ai_card_cutoff.json` is pre-registered and unmeasured against.         |

`ai_card_cutoff.json` was committed **before** any generation — see
`git log --follow speedrun-analysis/evals/ai_card_cutoff.json`. Nothing in this
directory modifies it.

---

## 7.1 — traceability is a build error, not a lint

A generated note is traceable only if **all five** hold:

1. `source_id` present _and registered_;
2. `span_start` / `span_end` present, integral, non-negative, `end > start`,
   inside the document;
3. `quote` character-identical to `source.text[start:end]` — this is what makes
   the span _resolve into the cited source_ rather than merely be two numbers of
   the right shape;
4. `source_sha256` matching the registered document, because an offset is only
   meaningful against one exact version of a text;
5. the `speedrun::ai::generated` tag.

It is a build error because of _where_ it sits, not how it is worded:
`ai/generation.py::emit_notes()` is the only sanctioned way a generated note
leaves the generator, and it routes every note through `enforce()` first. There
is no warn mode and no `strict=` parameter —
`test_enforce_has_no_warn_only_switch` asserts the escape hatch stays absent.
Run as a build step, `ai/traceability.py` exits **2** with a banner.

```
python3 speedrun-analysis/ai/traceability.py --notes NOTES.json --sources MANIFEST.json
```

The enforcement is exercised against real text, not only fixtures:
`RealSourceDocuments` loads the licence-vetted documents in
`speedrun-analysis/sources/` with `SourceStore.from_directory()`, resolves a span
inside one, and confirms that shifting the same span by **one character** is
caught as `SPAN_TEXT_MISMATCH`. That is the failure mode that still looks
perfectly well-formed at scale.

## 7.5 — leakage

Normalisation is NFKC → casefold → non-alphanumeric to space → collapse.
Comparison is **word 5-gram containment**, `|ngrams(H) ∩ ngrams(I)| / |ngrams(H)|`,
**threshold 0.30**. Containment rather than Jaccard because the realistic leak is
asymmetric — a 30-word held-out item inside a 5,000-word input has a Jaccard near
zero and a containment near one, so Jaccard would reliably miss the case the
check exists to catch.

Measured by `--self-test`, which builds its own fixtures:

| Case                                        | Containment | Result        |
| ------------------------------------------- | ----------- | ------------- |
| Clean set                                   | 0.000       | clean, exit 0 |
| Planted near-copy (3 words changed, buried) | **0.500**   | `NEAR_COPY`   |
| Exact copy                                  | 1.000       | `EXACT_COPY`  |
| Same topic, independently worded            | **0.000**   | not flagged   |

The negative control matters as much as the positive one: a check that fires on
everything is as useless as one that never fires. The measured floor is 0, not
something just under 0.30.

## 7.3 — retrieval, three arms, built to lose

| Arm             | Method                                               | Status        |
| --------------- | ---------------------------------------------------- | ------------- |
| `bm25`          | Robertson BM25, k1 = 1.5, b = 0.75, untuned defaults | READY         |
| `vector-hashed` | TF-IDF signed hashing embedding, dim 256, cosine     | READY         |
| `ai`            | —                                                    | `NOT_YET_RUN` |

The three are entries in one list; the scoring code does not know which arm is
"ours". The AI arm wins only by **strictly** beating **both** baselines. Losing,
tying, or not running all print **SHIP THE BASELINE**. A tie is not a win: equal
precision at higher cost and lower auditability is a loss.

The vector baseline hashes with `hashlib.blake2b`, not Python's `hash()`, which
is salted per process by `PYTHONHASHSEED` and would make every number
irreproducible.

The harness runs the leakage check on its own inputs first and refuses to print
any precision@k if it is not clean (exit 3). It compares the **held-out query set
against the dev/tuning split** — not against the corpus, which is the thing being
retrieved from and is _supposed_ to match. `--plant-leak` proves the gate blocks.

**Measured on the bundled fixture, `k = 3`, 12 held-out queries, seed 1729:**

```
arm              kind      status        precision@3   recall@3
bm25             baseline  READY              0.3611     0.9167
vector-hashed    baseline  READY              0.3333     0.8750
ai               ai        NOT_YET_RUN            --         --
ceiling                                         0.4167
VERDICT: SHIP THE BASELINE   (winning arm: bm25)
```

**These numbers describe the fixture, not the product.** The corpus in
`fixtures/retrieval_fixture.json` is synthetic — passages and relevance labels
written by the project author, at the same time, which is the weakest possible
labelling protocol. It is harness validation: evidence that the arms are wired
up, scored symmetrically, and that a loss is reportable. The BUILD-DOC 7.3
result needs a real source corpus and a real held-out query set. The report
prints that warning on every run.

## 7.6 — AI off

With the flag off (which is the **default**, because the pre-registered cutoff
has not been measured against):

- **no generation** — every entry point raises `AiDisabled`, with the network
  poisoned so a refusal cannot be a silent success. `network_poisoned()` is
  itself tested, so the guard cannot pass vacuously;
- **no AI retrieval** — the AI arm raises, and retrieval still returns results by
  falling back to BM25;
- **scores** — one of the three has a real input and it is exercised for real:
  the Rust `topic_mastery` query is called through the actual backend with the
  network poisoned. Its score _assembly_ is not built, and Performance and
  Readiness do not exist at all.

`test_unbuilt_score_paths_are_still_unbuilt` is a tripwire. It asserts
`rslib/src/speedrun/scoring.rs` is still absent and that `speedrun.proto` still
mentions neither score, so it **fails the day someone builds one** — which is the
reminder to extend this test rather than quietly drop the requirement.
