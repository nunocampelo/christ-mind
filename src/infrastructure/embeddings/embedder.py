"""The Embedder seam: turn texts into unit-normed vectors, batched.

Following the `Complete` / `ChatStream` pattern in `src/infrastructure/llm/` --
the abstraction is a callable protocol; the real implementation is a thin adapter
over the vendor SDK; tests inject a stub at the constructor. `dim` and `model_id`
are on the protocol because both the index cache and the on-disk cache key
depend on them: a change to either invalidates a stored index.
"""

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray


class Embedder(Protocol):
    """The seam. `embed` returns L2-normalized float32 vectors, one row per
    input, so cosine similarity collapses to a dot product downstream."""

    dim: int
    model_id: str

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]: ...


class SentenceTransformersEmbedder:
    """The production adapter. Loads the model lazily on first `embed`, not at
    construction, so an app that never actually retrieves (e.g. a unit test that
    only walks the object graph) doesn't pay torch's ~40s import cost.
    `normalize_embeddings=True` unit-norms the output so callers can dot-product
    for cosine similarity."""

    def __init__(self, model_id: str = "all-MiniLM-L6-v2"):
        self.model_id = model_id
        self._model: Any = None
        # Known dim of MiniLM-L6-v2; verified at first encode to fail loud on a
        # model swap that forgot to update this.
        self.dim = 384

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        model = self._load()
        vectors = model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True
        )
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)
        if vectors.shape[1] != self.dim:
            raise RuntimeError(
                f"embedder model_id={self.model_id!r} produced dim={vectors.shape[1]}, "
                f"expected {self.dim}"
            )
        return vectors

    def _load(self) -> Any:
        if self._model is None:
            # Local import: torch/transformers weigh ~40s at import time, and
            # only this method needs them. Keeps `from ...embedder import
            # SentenceTransformersEmbedder` cheap for callers that never encode.
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_id)
        return self._model
