"""Unit tests for `find_claims_hybrid`. Both channels get injected via DI hooks
so torch never loads; the test asserts the merge contract (interleave, dedupe,
global-cap) and the `RETRIEVAL_MODE=lexical` kill switch. Real MiniLM behavior
is validated by the live black-box eval at PR-5.
"""

from collections.abc import Sequence

import numpy as np
import pytest
from numpy.typing import NDArray

from application.retrieval.hybrid import find_claims_hybrid
from application.retrieval import hybrid as hybrid_module
from application.retrieval import find_claims_semantic as semantic_module
from infrastructure.database.claims import list_claims
from infrastructure.embeddings.claim_index import ClaimIndex


class _StubEmbedder:
    dim = 8
    model_id = "stub-hybrid-v1"

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
def stub_semantic_channel(monkeypatch: pytest.MonkeyPatch):
    """Wire the semantic channel to a real-corpus-sized ClaimIndex built with
    the stub embedder. Monkeypatches the default resolvers in
    `find_claims_semantic` so `find_claims_hybrid` (which does not accept DI
    hooks by design) never reaches the singleton."""
    embedder = _StubEmbedder()
    claims = list_claims()
    texts = [f"{c.subject} {c.verb_phrase} {c.object or ''}" for c in claims]
    matrix = embedder.embed(texts)
    index = ClaimIndex(matrix, tuple(c.claim_id for c in claims))
    monkeypatch.setattr(semantic_module, "get_claim_index", lambda: index)
    monkeypatch.setattr(
        semantic_module, "SentenceTransformersEmbedder", lambda: embedder
    )
    return index, embedder


def test_hybrid_returns_a_permutation_of_lex_and_sem_deduped(stub_semantic_channel):
    result = find_claims_hybrid(["forgiveness"], limit_per_query=5, global_limit=12)
    claim_ids = [c.claim_id for c in result]
    # Deduped by claim_id.
    assert len(claim_ids) == len(set(claim_ids))
    # Never exceeds the cap.
    assert len(result) <= 12
    # Every result is a real corpus claim.
    known = {c.claim_id for c in list_claims()}
    assert all(cid in known for cid in claim_ids)


def test_hybrid_first_slot_is_lexical_first_when_channels_disagree(
    stub_semantic_channel,
):
    # Lexical wins ties in the round-robin interleave: the first slot of the
    # merged result is whatever lexical put first (assuming lexical returned
    # anything). Preserves current behavior on A cases the lexical channel
    # already handles.
    result = find_claims_hybrid(["forgiveness"], limit_per_query=5, global_limit=8)
    # Compute lexical alone.
    from application.retrieval.find_claims import find_claims_batch

    lex = find_claims_batch(["forgiveness"], limit_per_query=5, global_limit=16)
    assert lex, "test relies on lexical returning at least one claim"
    assert result[0].claim_id == lex[0].claim_id


def test_hybrid_widens_channel_caps_beyond_global_limit(
    stub_semantic_channel, monkeypatch: pytest.MonkeyPatch
):
    # `find_claims_hybrid` asks each channel for 2*global_limit so the merge
    # has room to interleave. Prove it by capturing the arguments each channel
    # is called with.
    from application.retrieval.find_claims import find_claims_batch

    calls: dict[str, int] = {}

    def spy_batch(qs, limit_per_query, global_limit):
        calls["lex"] = global_limit
        return find_claims_batch(qs, limit_per_query, global_limit)

    monkeypatch.setattr(hybrid_module, "find_claims_batch", spy_batch)

    def spy_semantic(qs, limit_per_query=5, global_limit=12):
        calls["sem"] = global_limit
        return []

    monkeypatch.setattr(hybrid_module, "find_claims_semantic", spy_semantic)

    find_claims_hybrid(["x"], limit_per_query=5, global_limit=10)
    assert calls["lex"] == 20
    assert calls["sem"] == 20


def test_retrieval_mode_lexical_bypasses_semantic_channel(
    stub_semantic_channel, monkeypatch: pytest.MonkeyPatch
):
    # RETRIEVAL_MODE=lexical must not touch the semantic channel at all -- an
    # eval baseline reproduction has to be able to prove the hybrid code path
    # is a no-op when the env var is set.
    monkeypatch.setenv("RETRIEVAL_MODE", "lexical")
    touched = {"sem": False}

    def poisoned_semantic(*_args, **_kwargs):
        touched["sem"] = True
        return []

    monkeypatch.setattr(hybrid_module, "find_claims_semantic", poisoned_semantic)

    find_claims_hybrid(["forgiveness"], limit_per_query=5, global_limit=8)
    assert touched["sem"] is False


def test_retrieval_mode_hybrid_is_the_default(
    stub_semantic_channel, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("RETRIEVAL_MODE", raising=False)
    touched = {"sem": False}

    def counting_semantic(qs, limit_per_query=5, global_limit=12):
        touched["sem"] = True
        return []

    monkeypatch.setattr(hybrid_module, "find_claims_semantic", counting_semantic)

    find_claims_hybrid(["forgiveness"], limit_per_query=5, global_limit=8)
    assert touched["sem"] is True


def test_empty_queries_returns_empty(stub_semantic_channel):
    assert find_claims_hybrid([]) == []
