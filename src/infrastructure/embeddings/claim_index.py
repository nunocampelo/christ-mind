"""Import-time semantic index over the claim corpus: a numpy matrix + parallel
id tuple, top-k via matmul. Deliberately not FAISS -- 4k claims × 384 dim is
6MB, and a matmul + argpartition runs in microseconds. If the corpus grows past
~100k this becomes the wrong shape and we swap in FAISS behind the same
`top_k` signature; that day is not today.

The on-disk cache is keyed by `<model_id>_<corpus_run_id>.npz`. Either changing
invalidates: a new model produces incomparable vectors, a new corpus has claims
the old vectors don't cover. Cache files live alongside the corpus jsonl and are
committed for review-ability -- a reviewer can see exactly what vectors are
scored against, and the diff of a rebuilt cache is a legible metadata change.

The index is built once per process at first access, not at import, so an app
that never retrieves semantically doesn't pay the encode cost. Callers that DO
retrieve semantically pay it once, on the first query of the process's life.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from domain.claims.models import Claim
from infrastructure.database.claims import list_claims
from infrastructure.database.sources import list_sources
from infrastructure.embeddings.embedder import (
    Embedder,
    SentenceTransformersEmbedder,
)

_CORPUS_FILE = Path(__file__).resolve().parents[1] / "database" / "data" / "claims" / "corpus.jsonl"
_CACHE_DIR = _CORPUS_FILE.parent


def _corpus_run_id() -> str:
    """Read the corpus jsonl's header record's `run_id` -- the same value the
    black-box run artifact already captures, so an index built against corpus
    run X can never be misread as belonging to corpus run Y."""
    for raw in _CORPUS_FILE.read_text().splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        if record.get("type") == "header":
            return str(record.get("run_id", "unknown"))
    return "unknown"


def _cache_path(model_id: str) -> Path:
    # `/` is not a legal path component; sanitize just in case a model_id like
    # "sentence-transformers/all-MiniLM-L6-v2" ever slips in.
    safe_model_id = model_id.replace("/", "_")
    return _CACHE_DIR / f"embeddings_{safe_model_id}_{_corpus_run_id()}.npz"


def _embedding_text(claim: Claim, sources_by_id: dict[str, Any]) -> str:
    """The string fed to the embedder for one claim. Structure (subject verb object)
    gives the triple; the evidence sentence gives context. The `::` separator is
    a soft cue that keeps the two halves distinguishable to the model without
    imposing a hard token that pollutes short-form claims."""
    source = sources_by_id.get(claim.source_id)
    evidence = ""
    if source is not None:
        evidence = source.text[claim.evidence_start : claim.evidence_end]
    obj = claim.object or ""
    return f"{claim.subject} {claim.verb_phrase} {obj} :: {evidence}".strip()


class ClaimIndex:
    """A matrix of unit-normed claim vectors, aligned to a parallel tuple of
    claim_ids. Encapsulates load/rebuild/save so a caller only sees `top_k`."""

    def __init__(self, matrix: NDArray[np.float32], claim_ids: tuple[str, ...]):
        if matrix.ndim != 2 or matrix.shape[0] != len(claim_ids):
            raise ValueError(
                f"index shape mismatch: matrix.shape={matrix.shape}, "
                f"|claim_ids|={len(claim_ids)}"
            )
        self._matrix = matrix
        self._claim_ids = claim_ids

    @property
    def dim(self) -> int:
        return int(self._matrix.shape[1])

    @property
    def size(self) -> int:
        return int(self._matrix.shape[0])

    def top_k(
        self, query_vec: NDArray[np.float32], k: int
    ) -> list[tuple[str, float]]:
        """Return the `k` claim_ids with the highest cosine similarity to
        `query_vec`, most-similar first. `query_vec` must be unit-normed (the
        Embedder contract guarantees this)."""
        if k <= 0 or self.size == 0:
            return []
        k = min(k, self.size)
        scores = self._matrix @ query_vec
        # argpartition gets top-k unsorted (O(N)); a second sort orders just those k.
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(self._claim_ids[int(i)], float(scores[int(i)])) for i in top]


def _build(claims: Sequence[Claim], embedder: Embedder) -> ClaimIndex:
    sources_by_id = {s.id: s for s in list_sources()}
    texts = [_embedding_text(c, sources_by_id) for c in claims]
    matrix = embedder.embed(texts) if texts else np.zeros((0, embedder.dim), dtype=np.float32)
    return ClaimIndex(matrix, tuple(c.claim_id for c in claims))


def load_or_build(embedder: Embedder) -> ClaimIndex:
    """Return the corpus-wide claim index, from disk if the cache is warm and
    keyed to the current corpus + model, else building and caching it.

    Called at first semantic retrieval, not at import: a warm cache round-trip
    is milliseconds, but a cold build encodes all 4k claims and takes a few
    seconds. Neither cost belongs in an unrelated import path.
    """
    path = _cache_path(embedder.model_id)
    claims = list_claims()
    if path.exists():
        try:
            data = np.load(path)
            matrix = data["matrix"].astype(np.float32, copy=False)
            claim_ids = tuple(str(cid) for cid in data["claim_ids"])
        except (OSError, KeyError, ValueError):
            # A corrupt or old-format cache should not be fatal -- rebuild it.
            pass
        else:
            if len(claim_ids) == len(claims) and matrix.shape[1] == embedder.dim:
                return ClaimIndex(matrix, claim_ids)
    index = _build(claims, embedder)
    _save(index, path)
    return index


def _save(index: ClaimIndex, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Store ids as a fixed-width unicode array (not an object array), so
    # np.load doesn't need allow_pickle=True -- object arrays would trigger a
    # security refusal on load, and using pickled objects for what is
    # structurally a list of short strings is the wrong shape.
    np.savez_compressed(
        path,
        matrix=index._matrix,
        claim_ids=np.asarray(index._claim_ids, dtype=np.str_),
    )


# Module-level singleton, lazily materialized: `get_claim_index()` returns the
# same index for every caller in a process. First call builds (or loads) it;
# subsequent calls are O(1). Tests inject their own via `set_claim_index_for_test`
# rather than touching this global.
_INDEX: ClaimIndex | None = None
_INDEX_EMBEDDER: Embedder | None = None


def get_claim_index() -> ClaimIndex:
    """The process-wide claim index. Materialized on first call from the
    default `SentenceTransformersEmbedder`; subsequent calls reuse. Tests use
    `set_claim_index_for_test` at the seam instead of touching this."""
    global _INDEX, _INDEX_EMBEDDER
    if _INDEX is None:
        _INDEX_EMBEDDER = SentenceTransformersEmbedder()
        _INDEX = load_or_build(_INDEX_EMBEDDER)
    return _INDEX


def set_claim_index_for_test(index: ClaimIndex | None) -> None:
    """Swap the process-wide index for a test-owned one, or clear back to lazy
    default with `None`. The only intended caller is a test fixture."""
    global _INDEX
    _INDEX = index
