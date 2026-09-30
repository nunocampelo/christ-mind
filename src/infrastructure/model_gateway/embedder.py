"""An `Embedder` backed by the model gateway's `/embeddings` endpoint.

Drop-in behind the `Embedder` protocol from the hybrid increment: same
`embed -> L2-normalized float32 matrix` contract as the local MiniLM adapter, so
`claim_index` and the retrieval use cases don't change. `model_id` encodes the
deployment so a gateway index caches under a different key than the MiniLM one and
the two coexist on disk.

The gateway returns raw (un-normalized) vectors, so this normalizes — the protocol
promises unit-norm rows so cosine collapses to a dot product downstream.
"""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from infrastructure.model_gateway.client import (
    GatewayInferenceError,
    ModelGatewayClient,
)

# The endpoint rejects a POST with more inputs than this (confirmed: 2048 OK,
# 3000 -> 400). A full-corpus embed (~4k claims) therefore batches.
_MAX_INPUTS_PER_REQUEST = 2048


class ModelGatewayEmbedder:
    def __init__(
        self,
        client: ModelGatewayClient,
        deployment_url: str,
        dim: int,
        model_id: str,
    ) -> None:
        self._client = client
        self._deployment_url = deployment_url
        self.dim = dim
        self.model_id = model_id

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        texts = list(texts)
        chunks = [
            self._embed_chunk(texts[i : i + _MAX_INPUTS_PER_REQUEST])
            for i in range(0, len(texts), _MAX_INPUTS_PER_REQUEST)
        ]
        vectors = np.vstack(chunks)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return vectors / norms

    def _embed_chunk(self, texts: list[str]) -> NDArray[np.float32]:
        response = self._client.post_inference(
            self._deployment_url, "/embeddings", {"input": texts}
        )
        rows = response.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise GatewayInferenceError(
                "model gateway embeddings response missing one row per input"
            )
        # Rows may arrive out of order; each carries its own index.
        ordered = sorted(rows, key=lambda r: r.get("index", 0))
        vectors = np.asarray([r["embedding"] for r in ordered], dtype=np.float32)
        if vectors.shape != (len(texts), self.dim):
            raise GatewayInferenceError(
                f"model gateway embeddings dim mismatch: got {vectors.shape}, "
                f"expected {(len(texts), self.dim)}"
            )
        return vectors
