"""Live smoke + measurement: does the gateway embedder reach `mind-of-god-004b`'s
required claims that MiniLM cannot? (Step 3 of the model-gateway increment.)

Out of the pytest suite by design — it makes live gateway calls. Gated on
`MODEL_GATEWAY_*`; skips cleanly when unset. Builds a gateway-backed claim index
(cached under its own model_id, so MiniLM's cache is untouched), then for each
required claim of `mind-of-god-004b` compares semantic reachability: is the claim
in the top-k for any plausible query term, under MiniLM vs. under the gateway model?

Run: `.venv/bin/python -m evaluation.blackbox.gateway_smoke`
"""

import json
from pathlib import Path

from application.retrieval.find_claims_semantic import find_claims_semantic
from evaluation.blackbox.reachability import plausible_query_terms
from infrastructure.config.env import load_env
from infrastructure.embeddings.claim_index import ClaimIndex, load_or_build
from infrastructure.embeddings.embedder import Embedder, SentenceTransformersEmbedder
from infrastructure.model_gateway.client import ModelGatewayClient
from infrastructure.model_gateway.config import GatewayConfig
from infrastructure.model_gateway.embedder import ModelGatewayEmbedder

_CASE_ID = "mind-of-god-004b"
_GOLD = (
    Path(__file__).resolve().parent / "gold" / "cases.jsonl"
)
_GATEWAY_DIM = 3072  # text-embedding-3-large
_GATEWAY_MODEL_ID = "gateway-text-embedding-3-large"


def _load_case() -> dict:
    for raw in _GOLD.read_text().splitlines():
        if not raw.strip():
            continue
        rec = json.loads(raw)
        if rec.get("id") == _CASE_ID:
            return rec
    raise SystemExit(f"gold case {_CASE_ID} not found")


def _semantic_reaches(
    claim_id: str,
    terms: list[str],
    index: ClaimIndex,
    embedder: Embedder,
    limit: int = 12,
) -> bool:
    for term in terms:
        hits = find_claims_semantic(
            [term], limit_per_query=limit, global_limit=limit,
            index=index, embedder=embedder,
        )
        if any(c.claim_id == claim_id for c in hits):
            return True
    return False


def main() -> None:
    load_env()
    if not GatewayConfig.is_configured():
        print("MODEL_GATEWAY_* not set — skipping live smoke.")
        return
    config = GatewayConfig.from_env()
    if not config.embedding_deployment_url:
        print("MODEL_GATEWAY_EMBEDDING_DEPLOYMENT_URL not set — skipping.")
        return

    case = _load_case()
    required = case["must_include_any_claim_ids"]
    terms = plausible_query_terms(case["question"])
    print(f"case {_CASE_ID}: {len(required)} required claims, {len(terms)} query terms\n")

    minilm = SentenceTransformersEmbedder()
    minilm_index = load_or_build(minilm)

    with ModelGatewayClient(config) as client:
        gateway = ModelGatewayEmbedder(
            client, config.embedding_deployment_url, _GATEWAY_DIM, _GATEWAY_MODEL_ID
        )
        gateway_index = load_or_build(gateway)

        print(f"{'claim_id':<20} {'MiniLM':<8} {'gateway':<8}")
        minilm_hits = gateway_hits = 0
        for cid in required:
            m = _semantic_reaches(cid, terms, minilm_index, minilm)
            g = _semantic_reaches(cid, terms, gateway_index, gateway)
            minilm_hits += m
            gateway_hits += g
            print(f"{cid:<20} {'YES' if m else 'no':<8} {'YES' if g else 'no':<8}")

    print(
        f"\nreached: MiniLM {minilm_hits}/{len(required)}, "
        f"gateway {gateway_hits}/{len(required)}"
    )


if __name__ == "__main__":
    main()
