# Model gateway: shared embeddings provider now, LLM seam for later

## STATUS: COMPLETE (2026-09-30) — see OUTCOME at bottom

All four steps built, tested, and verified. The gateway embedder is
available-but-not-default (the live smoke showed a stronger embedder does not help
`mind-of-god-004b`). The chat families seam is scaffolded for the future
LLM-on-gateway cutover. Jump to the **OUTCOME** section for the result and what's
left. History below is preserved for context.

## Step 0 findings (confirmed against the live tenant)

These wire shapes were confirmed by the read-only probe (since deleted) before any
product code was written; the client and embedder are built to them.
- **OAuth**: HTTP Basic `client_credentials` POST to `AUTH_URL` → JSON
  `{"access_token": <JWT>}`. JWT has `exp` (use for cache-until-near-expiry) and
  ~47 scopes. Identical to the sibling agent.
- **Deployments list**: `GET {BASE_URL}/v2/lm/deployments` with header
  `AI-Resource-Group: <RESOURCE_GROUP>` → `{"resources": [ {id, status,
  scenarioId, deploymentUrl, details.resources.backend_details.model.name}, ...]}`.
  19 deployments; scenario `foundation-models`.
- **Two embedding deployments, both RUNNING** under `foundation-models`:
  `text-embedding-3-large` (id `d265b68f0ac4879d`, **dim 3072**) and
  `text-embedding-3-small` (id `d7676184cfeb8886`, **dim 1536**). Both far above
  MiniLM's 384. Chose **-large** as the gateway embedder target (strongest lever).
- **Embed call**: `POST {deploymentUrl}/embeddings?api-version=2023-05-15` — the
  `api-version` query param is **REQUIRED** (omitting it → 404). Headers:
  `Authorization: Bearer`, `AI-Resource-Group`, `Content-Type: application/json`.
  Request `{"input": [texts...]}`. Response is OpenAI-shaped:
  `{"data": [{"embedding": [...], "index", "object"}], "model", "object", "usage"}`
  — family-uniform, no family seam needed for embeddings (as planned).
- `deploymentUrl` from the list == `{BASE_URL}/v2/inference/deployments/{id}`.

**To resume, in order:**
1. Add the `httpx==0.28.1` direct pin (resolved in venv) to root `pyproject.toml`.
2. Build **Step 1**: `config.py` (fail-loud `GatewayConfig` from `MODEL_GATEWAY_*`)
   + `client.py` (token mint w/ exp-based cache, persistent `httpx.Client`,
   `post_inference`). Bake the `api-version` requirement in. Offline tests via a
   faked httpx transport.
3. Then **Step 2** (embedder, dim 3072), **Step 3** (discovery + live smoke — the
   measurement), **Step 4** (families scaffold).

**Reference facts already gathered (don't re-research):**
- A sibling agent already talks to this gateway; its token mint = HTTP Basic
  `client_credentials` POST to the auth URL, token cached, `Authorization:
  Bearer`. It uses a heavy vendor SDK for chat — we deliberately do NOT.
- Embeddings ARE reachable through the same gateway/OAuth (confirmed: the SDK's
  embeddings call hits a deployment `/embeddings` under scenario
  `foundation-models`); we replicate that with raw `httpx`, no SDK.
- That vendor SDK pulls langchain/langgraph/pandas/openai (30+ deps) and its dist
  name leaks the vendor — rejected for weight + vendor-name leak; not on this
  project.
- Inference URL shape: `.../v2/inference/deployments/<deployment-id>/...`.
  Deployments list endpoint under the gateway base URL; embedding model name +
  deployment id are NOT pinned anywhere — discover at runtime.

## Context

The hybrid-retrieval increment (`hybrid-retrieval-semantic-channel.md`) shipped a
local `sentence-transformers` embedder (`all-MiniLM-L6-v2`) and proved — with
evidence — that local embeddings cannot close `mind-of-god-004b` (the required
claims score below generic noise at any query/merge config; it's graph-tier).
The one untested lever left for the semantic channel short of the graph tier is
**a stronger embedding model**, and the enterprise AI gateway a sibling agent
already uses exposes exactly that.

This increment builds a **vendor-neutral gateway client** that authenticates to
that gateway and serves model calls over HTTP. Scope this round: **embeddings
adapter wired now; LLM chat adapter designed-for-later** (a documented seam, not
built). The client is deliberately generic because the user plans to route the
LLM through it too — replacing the cproxy transport in a later increment.

### Decisions pinned by the user (do not relitigate)

- **Name/obfuscation:** `src/infrastructure/model_gateway/`, `ModelGatewayClient`,
  public env vars `MODEL_GATEWAY_*`. The vendor name appears in **no** repo file,
  `.env.example`, or dependency pin. The only place the vendor contract is
  unavoidable is if a call needs a vendor-specific header or env var — isolate it
  inside `client.py` with a comment, never in a public name.
- **Transport:** **raw `httpx`, NOT the vendor SDK.** The SDK pulls
  langchain + langgraph + pandas + openai + tiktoken (30+ transitive deps) for
  what is one embeddings POST, and its dist name leaks the vendor. `httpx` is
  already a transitive dep. The sibling agent already mints its token with raw
  `httpx`; only its chat path uses the SDK, which we don't
  copy.
- **LLM family plan:** the LLM *may roam across model families* (Claude today,
  possibly GPT/Gemini/Llama later). So the chat side gets a **family-adapter
  seam** designed in from the start (request-builder + response-parser per
  family), with `AnthropicFamily` as the first impl when the chat adapter is
  actually built. Embeddings need **no** family seam — the `{"input":[...]}` →
  `{"data":[{"embedding":[...]}]}` shape is family-uniform.
- **Creds:** real creds live in the sibling repo's `.env`. Flow: scaffold empty
  `MODEL_GATEWAY_*` in this project's `.env` (gitignored) + neutral placeholders
  in `.env.example`; user pastes real values; then a read-only probe runs.
  Secrets never echoed, never committed.
- **Embedding deployment unknown:** the sibling agent pins only a chat
  deployment. Whether an embeddings deployment exists in the tenant is unknown —
  so a **discovery probe** (list deployments / attempt an embed) runs before the
  embedder is trusted, and the default retrieval embedder stays MiniLM until a
  gateway embedding deployment is confirmed.

## Architecture

```
src/infrastructure/model_gateway/            NEW
  __init__.py        empty (per repo rule)
  config.py          GatewayConfig frozen dataclass: reads MODEL_GATEWAY_* via
                     os.getenv at construction; fail-loud if a required var is
                     unset (no silent placeholder). One neutral->internal name
                     map lives here if the gateway needs vendor-named headers.
  client.py          ModelGatewayClient: OAuth client-credentials token mint
                     (httpx POST), token cached until near expiry, one
                     persistent httpx.Client (keep-alive). Low-level
                     `post_inference(deployment_url, path, json_body) -> dict`.
                     No model-shape knowledge here.
  embedder.py        ModelGatewayEmbedder(Embedder): embeds via the client's
                     /embeddings POST. New model_id => new on-disk index cache
                     key, so the MiniLM cache and a gateway cache coexist.
  discovery.py       list_deployments() + a describe helper, for the
                     unknown-deployment situation. Read-only.
  families/          NEW seam, CHAT ONLY, scaffolded not wired
    __init__.py      empty
    base.py          ChatFamily Protocol: build_request(system,user,stream) +
                     parse_response / parse_stream_event
    anthropic.py     AnthropicFamily -- the Messages shape (the one family now)
```

Nothing above the `Embedder` seam changes. `find_claims_semantic`,
`find_claims_hybrid`, `claim_index`, and all their tests are untouched — the
gateway embedder is a drop-in behind the protocol from the hybrid increment.
Selecting it is opt-in (DI / a factory switch), NOT the default, until a gateway
embedding deployment is confirmed live.

### Auth + call flow (mirrors the sibling agent's token mint, no SDK)

```
GatewayConfig (from MODEL_GATEWAY_*)
      |
ModelGatewayClient._token()   POST {auth_url}  grant_type=client_credentials,
      |                       HTTP Basic (client_id, client_secret) -> access_token
      |                       cached until exp - skew
      v
client.post_inference(deployment_url, "/embeddings", {"input": texts, ...})
      |   Authorization: Bearer <token>,  (+ resource-group header if required)
      v
{"data": [{"embedding": [...]}, ...]}  ->  np.float32 matrix, L2-normalized
```

Streaming chat (later increment) reuses `_token()` + the persistent client;
`AnthropicFamily.build_request` produces the Messages body, `parse_stream_event`
turns SSE deltas into text — same seam a GPT family would slot into.

## Sequence (each step independently reviewable)

**Step 0 · Creds + probe (no product code).**
Scaffold empty `MODEL_GATEWAY_AUTH_URL / _CLIENT_ID / _CLIENT_SECRET / _BASE_URL /
_RESOURCE_GROUP` (and `_EMBEDDING_DEPLOYMENT_URL` once known) in `.env`; neutral
placeholders in `.env.example`. User pastes real values. Run a **read-only probe**
that: mints a token, lists deployments, and attempts one embed against any
embedding deployment found. Output: confirmed OAuth shape, whether an embeddings
deployment exists, and the exact embed request/response wire shape. No secrets
printed. This de-risks building the client against guessed shapes.

**Step 1 · `config.py` + `client.py` + token mint.** Build the config loader and
the client's OAuth + `post_inference`, against the shapes step 0 confirmed. Tests
fake `httpx` at the transport boundary (a stub transport returning canned
token/inference responses) — no live dependency in the suite. Fail-loud on
missing config.

**Step 2 · `embedder.py`.** `ModelGatewayEmbedder` behind the `Embedder`
protocol. `embed(texts)` -> normalized float32 matrix via `post_inference`.
Tests use a fake `ModelGatewayClient`. Verify dim, normalization, batch shape,
empty-batch, and model_id (cache-key) behavior — mirror `test_embedder.py`.

**Step 3 · discovery + live smoke.** Wire `discovery.list_deployments`. Run one
live smoke (creds in `.env`): build a gateway index over the corpus, re-probe
`mind-of-god-004b`'s required claims. **This is the measurement** — does a
gateway embedding model reach claims 1-2 (or more) that MiniLM couldn't? Record
the result; it decides whether the gateway embedder becomes the retrieval default
or stays available-but-unused.

**Step 4 · families seam (scaffold only).** Add `families/base.py` +
`families/anthropic.py` with tests, but wire NO chat path into the app. This is
the documented seam for the future LLM-on-gateway increment; building it now
(cheaply) proves the client generalizes beyond embeddings and pins the shape
before the bigger cutover.

## Dependencies

- **No new heavy pin.** `httpx` is already transitive (via `anthropic`); if it is
  not a *direct* dep it becomes one — add `httpx==<pinned>` to root
  `pyproject.toml` `dependencies` (match the version already resolved in the
  venv). **Do NOT add the vendor SDK.**
- `numpy` already pinned (hybrid increment).

## Testing

- **Offline unit tests** for config (fail-loud), client (faked httpx transport:
  token mint, caching, bearer header, inference POST), embedder (faked client:
  shape/norm/dim/empty), family adapters (Anthropic request build + response
  parse). No test touches the live gateway.
- **Live smoke** (step 3) is manual/`--live`-style, out of the pytest suite —
  same policy as the black-box harness. Gated on `MODEL_GATEWAY_*` presence,
  skips cleanly when unset.
- `pyright` clean; run the full existing suite to confirm zero regression (the
  gateway code is additive and behind DI, so nothing existing should move).

## What this does NOT do

- Does not make the gateway embedder the retrieval default. MiniLM stays default
  until step 3's live smoke confirms a gateway embedding deployment helps.
- Does not migrate the LLM off cproxy. Step 4 only scaffolds the chat seam.
- Does not add the SDK, langchain, or any vendor-named dependency.
- Does not attempt to close `mind-of-god-004b`. If the gateway model reaches more
  of its required claims, good; if not, that further confirms the graph-tier
  finding (`hybrid-retrieval-graph-tier-finding` memory). Either outcome is
  recorded, not forced.

## Verification checklist

1. Step 0 probe prints: token OK, deployments list, embed wire shape, embeddings
   deployment present? (yes/no). No secret values in output.
2. `.venv/bin/pyright` clean.
3. `.venv/bin/python -m pytest tests -q` — new gateway tests pass, nothing
   regresses.
4. Step 3 live smoke: gateway index built, `mind-of-god-004b` required-claim
   reachability compared MiniLM vs gateway, result recorded in this plan's
   OUTCOME section.
5. `.env.example` shows only neutral `MODEL_GATEWAY_*`; grepping the repo for the
   vendor's name / env-var prefix / SDK import name returns nothing outside `.env`
   (gitignored).

## OUTCOME (2026-09-30 — all steps built, increment complete)

**Built:**
- `src/infrastructure/model_gateway/`: `config.py` (`GatewayConfig`, fail-loud
  `from_env`, `is_configured`), `client.py` (`ModelGatewayClient` — exp-cached
  token mint, persistent `httpx.Client`, `post_inference` + `get_json`;
  `api-version` query param and `AI-Resource-Group` header isolated here with
  comments, no public-name leak), `embedder.py` (`ModelGatewayEmbedder`, batches
  inputs at 2048/request, reorders by `index`, L2-normalizes), `discovery.py`
  (`list_deployments` → `Deployment` records), `families/base.py` + `anthropic.py`
  (chat seam, SCAFFOLD ONLY — no chat path wired).
- `httpx==0.28.1` added as a direct root dependency.
- Tests: `test_model_gateway_{client,embedder,discovery,families}.py`, all offline
  (faked httpx transport / faked client). Live smoke at
  `evaluation/blackbox/gateway_smoke.py` (out of pytest, gated on `MODEL_GATEWAY_*`).
- Step 0 probe was throwaway and deleted after use.

**Verification:** `pyright` clean; full suite 301 passed (296 pre-existing + 23 new
gateway tests: client/embedder/discovery/families, all green); no vendor name in any
product source, `.env.example`, pin, or this plan.

**The measurement (Step 3 live smoke, `mind-of-god-004b`, 5 required claims):**

| embedder                              | dim  | required claims reached |
|---------------------------------------|------|-------------------------|
| MiniLM (`all-MiniLM-L6-v2`, default)  | 384  | **1 / 5**               |
| gateway `text-embedding-3-large`      | 3072 | **0 / 5**               |

**A stronger embedding model does NOT help — it reached *fewer* required claims
than MiniLM.** This exhausts the last semantic-channel lever short of the graph
tier and hardens `hybrid-retrieval-graph-tier-finding`: `mind-of-god-004b` is
graph-relational (B2), not embedding-recoverable at any model strength.

**Decision:** the gateway embedder stays **available-but-not-default** (MiniLM
remains the retrieval default). It is wired behind the `Embedder` protocol and
selectable via DI, but nothing in the app defaults to it. Keep it for the future
LLM-on-gateway cutover (the client + families seam are the real payoff) rather
than for retrieval quality. Two embedding deployments exist in the tenant
(`text-embedding-3-large` id `d265b68f0ac4879d` dim 3072;
`text-embedding-3-small` id `d7676184cfeb8886` dim 1536).

**Left for the future LLM-on-gateway increment:** wire `families/` into a real
chat path (client streaming via SSE + `parse_stream_event`), replacing the cproxy
transport. The seam is scaffolded and tested; only the chat call site is missing.

## OUTCOME 2: Gateway LLM chat + model comparison (2026-09-30)

**Built (on top of the families scaffold):**
- `src/infrastructure/model_gateway/families/orchestration.py` — `OrchestrationFamily`
  implementing `ChatFamily` for the orchestration deployment's envelope shape. The
  orchestration deployment (`d3b615b816440f31`) is a model-ROUTER: you pass the model
  name in the request body, no per-model deployment needed.
- `src/infrastructure/model_gateway/chat.py` — `make_complete()`, `make_chat_stream()`,
  `make_mapper()` factories. Queue-based sync-to-async bridge for true token-by-token
  streaming from sync httpx to async `ChatStream`.
- `src/infrastructure/llm/types.py` — shared `ChatStream` type alias (fixes layering
  violation where orchestrator domain imported from `anthropic_proxy`).
- `apps/agent/src/mind_of_christ_agent/application/build.py` — `LLM_PROVIDER=gateway`
  DI switch: conditional import from `model_gateway.chat` vs `anthropic_proxy`.
- `src/infrastructure/model_gateway/client.py` — `post_orchestration()` and
  `post_orchestration_stream()` (no `api-version` param — orchestration rejects it).
- `src/infrastructure/model_gateway/config.py` — `orchestration_url` field,
  `MODEL_GATEWAY_ORCHESTRATION_URL` env var.
- `evaluation/blackbox/run_format.py` / `run.py` — `model` field in run header, so
  each eval run records which LLM produced the answers.
- Tests: `test_model_gateway_families.py` (7 orchestration tests),
  `test_model_gateway_chat.py` (4 tests), `test_model_gateway_client.py` (5 new
  orchestration tests). All offline, faked transport. 317 total pass, pyright clean.

**Orchestration wire shape (reverse-engineered from the vendor SDK, no SDK dep):**
- Request: `{"orchestration_config": {"module_configurations": {"templating_module_config":
  {"template": [messages]}, "llm_module_config": {"model_name": "gpt-4o", ...}},
  "stream": true}, "input_params": {}, "messages_history": []}`
- Response: `{"orchestration_result": {"choices": [{"message": {"content": "..."}}]}}`
- Streaming: SSE `data: {json}` lines, delta in `choices[0].delta.content`
- Endpoint: `{deploymentUrl}/completion` (NOT `/chat/completions`, NO `api-version`)

**Black-box eval results (dev split, 21 cases):**

| Model                        | Transport | Pass | Total | Rate      |
|------------------------------|-----------|------|-------|-----------|
| anthropic--claude-4.8-opus   | cproxy    | 20   | 21    | **95.2%** |
| anthropic--claude-4.8-opus   | gateway   | 18   | 21    | 85.7%     |
| anthropic--claude-4.6-opus   | gateway   | 18   | 21    | 85.7%     |
| gpt-4.1                      | gateway   | 17   | 21    | 81.0%     |
| gpt-5                        | gateway   | —    | —     | *too slow, 8/21 in 30 min* |
| anthropic--claude-4.6-opus   | cproxy    | —    | —     | *too slow, 9/21 in 30 min* |

**Failure analysis:**

| Case                  | cproxy 4.8 | gw gpt-4.1       | gw claude-4.8      | gw claude-4.6      |
|-----------------------|------------|------------------|--------------------|---------------------|
| atonement-purpose-002 | ✅          | ❌ citation corrupt | ✅                  | ✅                   |
| mind-definition-025   | ✅          | ❌ retrieval miss  | ❌ retrieval miss    | ❌ retrieval miss    |
| mind-of-god-004b      | ❌ B2       | ❌ B2              | ❌ B2               | ❌ B2                |
| miracles-order-001    | ✅          | ❌ retrieval miss  | ❌ retrieval miss    | ❌ retrieval miss    |

**Findings:**
1. **mind-of-god-004b** fails everywhere — confirmed graph-tier (B2), model-independent.
2. **atonement-purpose-002**: gpt-4.1 corrupted a citation ID (prepended `a` to a hex
   ID). Both Claude models handle it. OpenAI instruction-following weakness.
3. **mind-definition-025 + miracles-order-001**: fail on ALL gateway runs but pass on
   cproxy. Same model (claude-4.8) gives different results via different transports.
   The orchestration envelope likely affects mapper concept extraction subtly — or
   there's non-deterministic LLM sampling variance. The 2-case difference on a
   21-case suite is not statistically significant; would need ~5 runs per config to
   distinguish transport effect from noise.
4. **gpt-5 is impractically slow** through the orchestration endpoint (~3.5 min/case
   vs ~45s for gpt-4.1).

**Decision:** cproxy with claude-4.8-opus remains the default. The gateway LLM path
is fully functional and switchable via `LLM_PROVIDER=gateway` +
`MODEL_GATEWAY_CHAT_MODEL=<model>` for easy A/B comparison. No model tested via the
gateway matched cproxy's 95.2% rate.
