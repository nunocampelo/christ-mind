"""Unit tests for `find_claims_semantic`. Uses a stub Embedder and a
stub-derived ClaimIndex so torch never loads. Structural tests only: this
proves the shape and dedupe contract mirrors `find_claims_batch`'s, not that
the real MiniLM model retrieves the right things (that is validated by the
live black-box eval at PR-5).
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from application.retrieval.find_claims_semantic import find_claims_semantic
from infrastructure.database.claims import list_claims
from infrastructure.embeddings.claim_index import ClaimIndex


class _StubEmbedder:
    dim = 8
    model_id = "stub-semantic-v1"

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            rng = np.random.default_rng(_stable_hash(text))
            v = rng.standard_normal(self.dim).astype(np.float32)
            v /= np.linalg.norm(v) or 1.0
            out[i] = v
        return out


def _stable_hash(s: str) -> int:
    h = 2166136261
    for byte in s.encode("utf-8"):
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return h


@pytest.fixture
def stub_index_and_embedder() -> tuple[ClaimIndex, _StubEmbedder]:
    """A real-corpus-sized index built with the stub embedder. Query vectors
    are deterministic hashes, so top-k orderings are stable but semantically
    meaningless -- exactly what a shape/contract test wants."""
    embedder = _StubEmbedder()
    claims = list_claims()
    texts = [
        f"{c.subject} {c.verb_phrase} {c.object or ''}" for c in claims
    ]
    matrix = embedder.embed(texts)
    index = ClaimIndex(matrix, tuple(c.claim_id for c in claims))
    return index, embedder


def test_empty_queries_returns_empty(
    stub_index_and_embedder: tuple[ClaimIndex, _StubEmbedder],
):
    index, embedder = stub_index_and_embedder
    assert find_claims_semantic([], index=index, embedder=embedder) == []


def test_whitespace_query_is_skipped(
    stub_index_and_embedder: tuple[ClaimIndex, _StubEmbedder],
):
    # A bare-whitespace query is a no-op, matching lexical find_claims's
    # treatment. Two queries where one is whitespace should behave like the
    # single-real-query case.
    index, embedder = stub_index_and_embedder
    both = find_claims_semantic(["forgiveness", "   "], index=index, embedder=embedder)
    only_real = find_claims_semantic(["forgiveness"], index=index, embedder=embedder)
    assert [c.claim_id for c in both] == [c.claim_id for c in only_real]


def test_global_limit_caps_output(
    stub_index_and_embedder: tuple[ClaimIndex, _StubEmbedder],
):
    index, embedder = stub_index_and_embedder
    result = find_claims_semantic(
        ["forgiveness", "atonement", "peace"],
        limit_per_query=5,
        global_limit=4,
        index=index,
        embedder=embedder,
    )
    assert len(result) == 4


def test_output_is_deduped_by_claim_id(
    stub_index_and_embedder: tuple[ClaimIndex, _StubEmbedder],
):
    # Two identical queries surface the same top-k claim; the merged output
    # must contain each claim_id at most once.
    index, embedder = stub_index_and_embedder
    result = find_claims_semantic(
        ["forgiveness", "forgiveness"], index=index, embedder=embedder
    )
    claim_ids = [c.claim_id for c in result]
    assert len(claim_ids) == len(set(claim_ids))


def test_output_claims_are_real_corpus_claims(
    stub_index_and_embedder: tuple[ClaimIndex, _StubEmbedder],
):
    # A retrieval result is a real domain Claim from list_claims(), not a
    # dict, tuple, or wrapper. The classifier and orchestrator both treat the
    # output as `list[Claim]`; a shape drift here breaks them silently.
    index, embedder = stub_index_and_embedder
    result = find_claims_semantic(
        ["love"], limit_per_query=3, index=index, embedder=embedder
    )
    known_ids = {c.claim_id for c in list_claims()}
    assert result
    for claim in result:
        assert claim.claim_id in known_ids
        assert isinstance(claim.subject, str)


def test_stale_index_entries_are_dropped_not_raised():
    # Simulate the cache-invalidation edge case: an index built against a
    # previous corpus references a claim_id no longer in list_claims().
    # find_claims_semantic must skip such ids rather than raise, so a running
    # server degrades gracefully rather than crashing on a cold cache.
    embedder = _StubEmbedder()
    # A one-entry index with an id that is not in the real corpus.
    stale_matrix = np.zeros((1, embedder.dim), dtype=np.float32)
    stale_matrix[0, 0] = 1.0
    stale_index = ClaimIndex(stale_matrix, ("does-not-exist-in-corpus",))

    result = find_claims_semantic(["anything"], index=stale_index, embedder=embedder)
    assert result == []
