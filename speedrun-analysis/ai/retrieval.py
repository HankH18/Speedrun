# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Three retrieval arms (BUILD-DOC 7.3). Standard library only.

    "Baselines: BM25 keyword search, and embedding vector search. ... Report
     precision@k for all three on a held-out query set. If the AI method does
     not win, report that and use the baseline."

The two baselines are real and run here. The AI arm is a declared stub with
status NOT_YET_RUN: it needs an API key and a real source corpus, and it has
neither, so it raises rather than returning anything scoreable. An arm that
cannot run scores nothing and therefore cannot win -- see
`evals/retrieval_compare.py`, which prints SHIP THE BASELINE whenever the AI
arm fails to beat both baselines, including for this reason.

DETERMINISM
-----------
Both baselines are exactly reproducible across runs and machines:

  * tokenisation is fixed (NFKC, casefold, split on non-alphanumeric);
  * the vector arm hashes with `hashlib.blake2b`, **not** Python's builtin
    `hash()`, which is randomised per process by PYTHONHASHSEED and would make
    the reported precision@k unreproducible;
  * ranking ties break on `passage_id`, so equal scores never reorder.

WHY A HASHING EMBEDDING
-----------------------
BUILD-DOC 7.3 asks for "embedding vector search" as a baseline. A downloaded
neural embedding model is a dependency this project does not take (stdlib
only), and -- more to the point -- a baseline exists to be beaten, so it should
be the cheap thing anyone can rerun. This is the hashing trick: tokens are
hashed into a fixed number of buckets with signed weights, weighted by TF-IDF,
L2-normalised, and compared by cosine. It captures term co-occurrence in a
dense vector without a model file.

It is NOT a semantic embedding, and the report says so: it will not match
"kidney" to "renal". That is a real limitation of this baseline and is stated
where the numbers are printed, because a baseline that is quietly weaker than
it looks makes the AI arm look better than it is.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Tuple

from ai.flags import AiDisabled  # noqa: F401  (re-exported for callers)
from ai.flags import ai_enabled
from ai.flags import api_key_present
from ai.flags import require_ai

#: Standard Robertson/Sparck Jones defaults. NOT tuned on the query set --
#: tuning them on the held-out queries would be the leakage this project is
#: about. Stated here so the number is auditable.
BM25_K1 = 1.5
BM25_B = 0.75

#: Hashing-embedding dimensionality. 256 is small enough to be cheap and large
#: enough that collisions are rare on a few-hundred-term vocabulary.
VECTOR_DIM = 256

_TOKEN_SPLIT = re.compile(r"[^0-9a-z]+")


def tokenize(text: str) -> List[str]:
    """NFKC -> casefold -> split on non-alphanumeric. No stemming, no stoplist.

    No stoplist on purpose: BM25's IDF already discounts ubiquitous terms, and
    a hand-written stoplist is a tuning knob that would need to be justified.
    """
    normalised = unicodedata.normalize("NFKC", text).casefold()
    return [tok for tok in _TOKEN_SPLIT.split(normalised) if tok]


@dataclass(frozen=True)
class Passage:
    passage_id: str
    text: str


class ArmNotRunnable(RuntimeError):
    """An arm exists but cannot produce results. It scores nothing."""


class RetrievalArm:
    """Common interface. `search` returns ranked passage ids, best first."""

    name = "abstract"
    kind = "baseline"
    status = "READY"
    note = ""

    def search(self, query: str, k: int) -> List[str]:
        raise NotImplementedError


# -- arm 1: BM25 -----------------------------------------------------------


class Bm25Arm(RetrievalArm):
    name = "bm25"
    kind = "baseline"
    status = "READY"
    note = "Robertson BM25, k1={}, b={}, untuned defaults".format(BM25_K1, BM25_B)

    def __init__(
        self,
        passages: Sequence[Passage],
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.passages = list(passages)
        self.doc_tokens: List[List[str]] = [tokenize(p.text) for p in self.passages]
        self.doc_len = [len(toks) for toks in self.doc_tokens]
        self.avg_len = (
            sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0
        )
        self.tf: List[Dict[str, int]] = []
        df: Dict[str, int] = {}
        for toks in self.doc_tokens:
            counts: Dict[str, int] = {}
            for tok in toks:
                counts[tok] = counts.get(tok, 0) + 1
            self.tf.append(counts)
            for tok in counts:
                df[tok] = df.get(tok, 0) + 1
        self.df = df
        self.n_docs = len(self.passages)

    def idf(self, term: str) -> float:
        # Robertson-Sparck Jones IDF with the +1 that keeps it non-negative.
        df = self.df.get(term, 0)
        return math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))

    def score(self, query: str) -> List[Tuple[float, str]]:
        q_terms = tokenize(query)
        scored: List[Tuple[float, str]] = []
        for i, passage in enumerate(self.passages):
            total = 0.0
            counts = self.tf[i]
            length = self.doc_len[i] or 1
            for term in q_terms:
                freq = counts.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (
                    1 - self.b + self.b * length / (self.avg_len or 1)
                )
                total += self.idf(term) * freq * (self.k1 + 1) / denom
            scored.append((total, passage.passage_id))
        return scored

    def search(self, query: str, k: int) -> List[str]:
        scored = self.score(query)
        ranked = sorted(scored, key=lambda pair: (-pair[0], pair[1]))
        return [pid for score, pid in ranked[:k] if score > 0.0]


# -- arm 2: hashed bag-of-words vector search ------------------------------


def _bucket_and_sign(token: str, dim: int = VECTOR_DIM) -> Tuple[int, float]:
    """Deterministic bucket and sign for a token.

    `hashlib.blake2b`, not `hash()`: the builtin is salted per process by
    PYTHONHASHSEED, which would make every reported number irreproducible.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    # Top bit gives the sign; signed hashing makes collision errors cancel in
    # expectation instead of always inflating similarity.
    sign = 1.0 if (value >> 63) & 1 else -1.0
    return value % dim, sign


class HashedVectorArm(RetrievalArm):
    name = "vector-hashed"
    kind = "baseline"
    status = "READY"
    note = (
        "TF-IDF weighted signed hashing embedding, dim={}, cosine. Lexical, "
        "not semantic: it will not match 'kidney' to 'renal'.".format(VECTOR_DIM)
    )

    def __init__(self, passages: Sequence[Passage], dim: int = VECTOR_DIM) -> None:
        self.dim = dim
        self.passages = list(passages)
        tokens = [tokenize(p.text) for p in self.passages]
        n_docs = len(self.passages)
        df: Dict[str, int] = {}
        for toks in tokens:
            for tok in set(toks):
                df[tok] = df.get(tok, 0) + 1
        self.df = df
        self.n_docs = n_docs
        self.vectors = [self._embed(toks) for toks in tokens]

    def _idf(self, term: str) -> float:
        # Smoothed: unseen query terms get the weight of a hapax rather than
        # a division by zero.
        return math.log(1.0 + self.n_docs / (self.df.get(term, 0) + 1))

    def _embed(self, tokens: Sequence[str]) -> Dict[int, float]:
        counts: Dict[str, int] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        vec: Dict[int, float] = {}
        for term, freq in counts.items():
            bucket, sign = _bucket_and_sign(term, self.dim)
            # Sublinear TF, the standard damping, so one repeated word cannot
            # dominate a passage.
            weight = (1.0 + math.log(freq)) * self._idf(term)
            vec[bucket] = vec.get(bucket, 0.0) + sign * weight
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm == 0.0:
            return {}
        return {b: v / norm for b, v in vec.items()}

    @staticmethod
    def _cosine(a: Mapping[int, float], b: Mapping[int, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(value * b.get(bucket, 0.0) for bucket, value in a.items())

    def score(self, query: str) -> List[Tuple[float, str]]:
        q_vec = self._embed(tokenize(query))
        return [
            (self._cosine(q_vec, self.vectors[i]), passage.passage_id)
            for i, passage in enumerate(self.passages)
        ]

    def search(self, query: str, k: int) -> List[str]:
        ranked = sorted(self.score(query), key=lambda pair: (-pair[0], pair[1]))
        return [pid for score, pid in ranked[:k] if score > 0.0]


# -- arm 3: the AI method (STUB) -------------------------------------------


class AiRetrievalArm(RetrievalArm):
    """NOT YET RUN. Declared so it can lose, not so it can be assumed to win.

    Requires an API key and a registered real source corpus. It has neither,
    so `search` raises and the comparison harness records the arm as unscored.
    """

    name = "ai"
    kind = "ai"
    status = "NOT_YET_RUN"
    note = (
        "STUB. Needs (a) the AI feature flag on, (b) an API key, (c) a real "
        "source corpus. No AI retrieval has been executed; there is no number "
        "for this arm and none is implied."
    )

    def __init__(
        self,
        passages: Sequence[Passage],
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.passages = list(passages)
        self.env = env

    def unavailable_reason(self) -> Optional[str]:
        """Why this arm cannot run, or None if it could (it never can yet)."""
        if not ai_enabled(self.env):
            return "AI feature flag is OFF (BUILD-DOC 7.6)"
        if not api_key_present(self.env):
            return "AI feature flag is ON but no API key is set"
        return (
            "AI feature flag is ON and a key is present, but the AI retrieval "
            "method is NOT IMPLEMENTED -- no request has ever been made"
        )

    def search(self, query: str, k: int) -> List[str]:
        require_ai("AI retrieval", self.env)
        raise ArmNotRunnable(
            "AI retrieval is NOT YET RUN: {}".format(self.unavailable_reason())
        )


# -- assembly --------------------------------------------------------------


def build_arms(
    passages: Sequence[Passage], env: Optional[Mapping[str, str]] = None
) -> List[RetrievalArm]:
    """The three arms, in a list, so the harness treats them symmetrically.

    The AI arm is one entry among three with no special status in the ranking
    code. Nothing in the comparison knows which arm is "ours".
    """
    return [
        Bm25Arm(passages),
        HashedVectorArm(passages),
        AiRetrievalArm(passages, env=env),
    ]


def retrieve(
    query: str,
    passages: Iterable[Passage],
    k: int = 5,
    arm: str = "auto",
    env: Optional[Mapping[str, str]] = None,
) -> Tuple[str, List[str]]:
    """Retrieve for one query. Returns `(arm_name_used, passage_ids)`.

    `arm="ai"` raises `AiDisabled` when the flag is off -- callers must not be
    able to get AI retrieval by accident. `arm="auto"` falls back to BM25, so
    the app keeps retrieving with AI off (BUILD-DOC 7.6, and the "AI offline"
    adversarial case in BUILD-DOC 13).
    """
    passage_list = list(passages)
    if arm == "bm25":
        return "bm25", Bm25Arm(passage_list).search(query, k)
    if arm == "vector-hashed":
        return "vector-hashed", HashedVectorArm(passage_list).search(query, k)
    if arm == "ai":
        return "ai", AiRetrievalArm(passage_list, env=env).search(query, k)
    if arm != "auto":
        raise ValueError("unknown arm {!r}".format(arm))
    if ai_enabled(env) and api_key_present(env):
        try:
            return "ai", AiRetrievalArm(passage_list, env=env).search(query, k)
        except (ArmNotRunnable, AiDisabled):
            pass  # degrade to the baseline rather than failing the caller
    return "bm25", Bm25Arm(passage_list).search(query, k)
