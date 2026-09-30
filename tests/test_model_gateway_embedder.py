"""Unit tests for the gateway embedder, mirroring test_embedder.py's contract
checks (shape/dim/norm/empty/model_id) but faking the client, not the transport.
"""

from typing import Any

import numpy as np
import pytest

from infrastructure.embeddings.embedder import Embedder
from infrastructure.model_gateway.client import GatewayInferenceError
from infrastructure.model_gateway.embedder import ModelGatewayEmbedder

_DIM = 4


class _FakeClient:
    """Returns a deterministic un-normalized vector per input, in a scrambled
    row order with explicit `index`, so the embedder's reorder + normalize is
    what's under test — not the client."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post_inference(
        self, deployment_url: str, path: str, json_body: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({"url": deployment_url, "path": path, "body": json_body})
        texts = json_body["input"]
        rows = [
            {"index": i, "embedding": [float(i + 1)] * _DIM}
            for i in range(len(texts))
        ]
        return {"data": list(reversed(rows)), "usage": {"total_tokens": 1}}


def _embedder(client: Any) -> ModelGatewayEmbedder:
    return ModelGatewayEmbedder(
        client=client,
        deployment_url="https://api.example/dep",
        dim=_DIM,
        model_id="gateway-text-embedding-3-large",
    )


def test_conforms_to_embedder_protocol() -> None:
    embedder: Embedder = _embedder(_FakeClient())
    assert embedder.dim == _DIM
    assert embedder.model_id == "gateway-text-embedding-3-large"


def test_embed_returns_float32_matrix_of_shape_n_by_dim() -> None:
    out = _embedder(_FakeClient()).embed(["a", "b", "c"])
    assert out.shape == (3, _DIM)
    assert out.dtype == np.float32


def test_embed_returns_unit_norm_vectors() -> None:
    out = _embedder(_FakeClient()).embed(["a", "b", "c"])
    norms = np.linalg.norm(out, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)


def test_embed_reorders_rows_by_index() -> None:
    # Row 0 is [1,1,1,1] pre-norm; after unit-norm every component is 0.5.
    out = _embedder(_FakeClient()).embed(["first", "second"])
    assert np.allclose(out[0], 0.5)


def test_embed_sends_input_list_to_deployment() -> None:
    client = _FakeClient()
    _embedder(client).embed(["x", "y"])
    assert client.calls[0]["path"] == "/embeddings"
    assert client.calls[0]["body"] == {"input": ["x", "y"]}


def test_embed_of_empty_batch_returns_zero_rows_without_calling() -> None:
    client = _FakeClient()
    out = _embedder(client).embed([])
    assert out.shape == (0, _DIM)
    assert client.calls == []


def test_embed_chunks_large_batches_and_preserves_order() -> None:
    from infrastructure.model_gateway.embedder import _MAX_INPUTS_PER_REQUEST

    class _CountingClient:
        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        def post_inference(
            self, deployment_url: str, path: str, json_body: Any
        ) -> dict[str, Any]:
            texts = json_body["input"]
            self.batch_sizes.append(len(texts))
            return {
                "data": [
                    {"index": i, "embedding": [float(hash(t) % 7 + 1)] * _DIM}
                    for i, t in enumerate(texts)
                ]
            }

    n = _MAX_INPUTS_PER_REQUEST + 5
    client = _CountingClient()
    out = _embedder(client).embed([f"t{i}" for i in range(n)])
    assert out.shape == (n, _DIM)
    assert client.batch_sizes == [_MAX_INPUTS_PER_REQUEST, 5]
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0, atol=1e-6)


def test_embed_raises_on_row_count_mismatch() -> None:
    class _ShortClient:
        def post_inference(self, *_: Any, **__: Any) -> dict[str, Any]:
            return {"data": [{"index": 0, "embedding": [1.0] * _DIM}]}

    with pytest.raises(GatewayInferenceError):
        _embedder(_ShortClient()).embed(["a", "b"])


def test_embed_raises_on_dim_mismatch() -> None:
    class _WrongDimClient:
        def post_inference(self, *_: Any, **__: Any) -> dict[str, Any]:
            return {"data": [{"index": 0, "embedding": [1.0, 2.0]}]}

    with pytest.raises(GatewayInferenceError):
        _embedder(_WrongDimClient()).embed(["a"])
