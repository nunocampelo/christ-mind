"""Unit tests for the Embedder seam. Only exercises the protocol contract and a
stub implementation -- the real SentenceTransformersEmbedder is not touched here,
because torch's ~40s import cost has no place in a unit-test loop and the real
model's outputs are not something a test should assert against.

The production adapter is exercised at integration time when the claims index
first builds against the real corpus (see the index tests).
"""

from collections.abc import Sequence

import numpy as np
import pytest
from numpy.typing import NDArray

from infrastructure.embeddings.embedder import Embedder


class _StubEmbedder:
    """A deterministic fake embedder. Maps each input string to a fixed vector
    derived from its hash, then L2-normalizes. Two different strings almost
    always map to different vectors, but the same string always maps to the
    same vector -- exactly the two properties a real Embedder must hold and the
    ones downstream code (index, semantic retrieval, hybrid merge) depends on."""

    dim = 8
    model_id = "stub-v1"

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors: list[NDArray[np.float32]] = []
        for text in texts:
            # Deterministic hash-to-vector: 8 floats per text, seeded by the
            # string's hash so the vector is stable across process runs even
            # though Python's built-in hash() would not be.
            rng = np.random.default_rng(_stable_hash(text))
            v = rng.standard_normal(self.dim).astype(np.float32)
            v /= np.linalg.norm(v) or 1.0
            vectors.append(v)
        return np.asarray(vectors, dtype=np.float32)


def _stable_hash(s: str) -> int:
    # Python's built-in hash() is randomized per-process; the fake needs to be
    # stable across processes so the on-disk index cache round-trips in tests.
    # Small FNV-1a-style mixer, sufficient for a stub.
    h = 2166136261
    for byte in s.encode("utf-8"):
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return h


def test_stub_conforms_to_embedder_protocol():
    embedder: Embedder = _StubEmbedder()
    assert embedder.dim == 8
    assert embedder.model_id == "stub-v1"


def test_embed_returns_float32_matrix_of_shape_n_by_dim():
    embedder = _StubEmbedder()
    out = embedder.embed(["a", "b", "c"])
    assert out.shape == (3, 8)
    assert out.dtype == np.float32


def test_embed_is_deterministic_across_calls():
    # Same input -> same output. Load-bearing for the index cache: an embed
    # that drifted between builds would silently invalidate every stored score.
    embedder = _StubEmbedder()
    first = embedder.embed(["repeatable input"])
    second = embedder.embed(["repeatable input"])
    assert np.array_equal(first, second)


def test_embed_returns_unit_norm_vectors():
    # Cosine similarity via dot product depends on this. A non-normalized
    # vector would silently poison every downstream score.
    embedder = _StubEmbedder()
    out = embedder.embed(["a", "some longer text with several words"])
    norms = np.linalg.norm(out, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)


def test_embed_of_empty_batch_returns_zero_rows():
    embedder = _StubEmbedder()
    out = embedder.embed([])
    assert out.shape == (0, 8)


@pytest.mark.parametrize("text", ["", " ", "\n"])
def test_embed_handles_whitespace_texts(text: str):
    # Whitespace-only input shouldn't crash. Semantic meaning is undefined, but
    # the embed must still produce a well-shaped, finite vector -- the caller
    # decides whether to filter such queries upstream.
    embedder = _StubEmbedder()
    out = embedder.embed([text])
    assert out.shape == (1, 8)
    assert np.all(np.isfinite(out))
