"""Unit tests for the semantic claim index. Uses the stub Embedder from
test_embedder.py -- the real SentenceTransformersEmbedder is exercised only at
integration time (the black-box eval build path).
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from infrastructure.embeddings.claim_index import ClaimIndex, _save, load_or_build


class _StubEmbedder:
    """Deterministic hash-to-vector fake -- same as test_embedder.py's stub,
    duplicated here to keep the two test files independent. If the shape ever
    changes, that's a signal to promote it to a fixtures module."""

    dim = 8
    model_id = "stub-index-v1"

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


def _toy_matrix(rows: list[list[float]]) -> NDArray[np.float32]:
    """Build a normalized matrix from raw floats -- lets tests assert exact
    top-k order without depending on the stub's hash outputs."""
    arr = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return (arr / np.where(norms == 0, 1, norms)).astype(np.float32)


def test_top_k_returns_most_similar_first():
    # Three claims, hand-built vectors. The query is closest to c1 then c2 then c0.
    matrix = _toy_matrix([[1, 0, 0, 0, 0, 0, 0, 0],   # c0
                          [0, 1, 0, 0, 0, 0, 0, 0],   # c1
                          [0.5, 0.5, 0, 0, 0, 0, 0, 0]])  # c2
    index = ClaimIndex(matrix, ("c0", "c1", "c2"))
    query = matrix[1]  # exactly c1
    result = index.top_k(query, k=3)
    assert [cid for cid, _ in result] == ["c1", "c2", "c0"]


def test_top_k_caps_at_index_size():
    matrix = _toy_matrix([[1, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0, 0]])
    index = ClaimIndex(matrix, ("c0", "c1"))
    result = index.top_k(matrix[0], k=99)
    # Only 2 claims exist; a k larger than corpus caps at corpus size.
    assert len(result) == 2


def test_top_k_returns_empty_for_nonpositive_k():
    matrix = _toy_matrix([[1, 0, 0, 0, 0, 0, 0, 0]])
    index = ClaimIndex(matrix, ("c0",))
    assert index.top_k(matrix[0], k=0) == []


def test_top_k_returns_empty_on_empty_index():
    matrix = np.zeros((0, 8), dtype=np.float32)
    index = ClaimIndex(matrix, ())
    assert index.top_k(np.zeros(8, dtype=np.float32), k=5) == []


def test_top_k_scores_are_finite_floats():
    matrix = _toy_matrix([[1, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0, 0]])
    index = ClaimIndex(matrix, ("c0", "c1"))
    result = index.top_k(matrix[0], k=2)
    scores = [s for _, s in result]
    assert all(isinstance(s, float) for s in scores)
    assert all(np.isfinite(s) for s in scores)


def test_shape_mismatch_raises_at_construction():
    matrix = _toy_matrix([[1, 0, 0, 0, 0, 0, 0, 0]])
    with pytest.raises(ValueError):
        ClaimIndex(matrix, ("c0", "c1"))  # 1 row but 2 ids


def test_save_and_reload_roundtrips_matrix_and_ids(tmp_path: Path):
    # A round-trip is load-bearing: if the on-disk format silently drifts, every
    # future retrieval scores against stale vectors. Assert both matrix and ids
    # survive verbatim.
    matrix = _toy_matrix([[1, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0, 0]])
    original = ClaimIndex(matrix, ("c0", "c1"))
    path = tmp_path / "roundtrip.npz"
    _save(original, path)

    data = np.load(path)
    reloaded = ClaimIndex(
        data["matrix"].astype(np.float32, copy=False),
        tuple(str(cid) for cid in data["claim_ids"]),
    )
    assert reloaded.size == original.size
    assert reloaded.dim == original.dim
    result_original = original.top_k(matrix[0], k=2)
    result_reloaded = reloaded.top_k(matrix[0], k=2)
    assert result_original == result_reloaded


def test_load_or_build_produces_index_matching_corpus_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A real end-to-end shape check against the corpus, with a stub embedder so
    # torch never loads. Redirect the cache dir to tmp_path so the test never
    # writes a stub-model cache into the real corpus data directory.
    from infrastructure.database.claims import list_claims
    from infrastructure.embeddings import claim_index as index_module

    monkeypatch.setattr(index_module, "_CACHE_DIR", tmp_path)

    class _UniqueStubEmbedder(_StubEmbedder):
        model_id = "stub-load-or-build"

    embedder = _UniqueStubEmbedder()
    idx = load_or_build(embedder)
    assert idx.size == len(list_claims())
    assert idx.dim == embedder.dim
    # Cache landed in tmp_path, not the real corpus dir.
    assert (tmp_path / f"embeddings_{embedder.model_id}_"
            f"{index_module._corpus_run_id()}.npz").exists()
