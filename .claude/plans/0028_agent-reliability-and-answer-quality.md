# Agent reliability & answer-quality hardening

## Context

Frontend tests, the production build, and Pyright all pass; the system is substantial and
well-layered (source evidence / inferred connections / generated prose kept distinct end to
end). The next work is **reliability and answer quality**, not more architecture. A review
surfaced seven concrete defects plus stale docs.

This revision incorporates seven corrections from review that change *how* several items are
built — most importantly: the failed answers are **not** in the run file (item 2 must
recover/rerun), history must be bounded by **size and** turn count and excluded by
**sequence** (item 3), the mapper must consume context or "that" never resolves (item 4),
`FinalEvent.text` is currently **ignored** so sanitization never reaches the wire (item 1),
and ownership must cover **writes + history loading**, not just REST reads (item 7).

All findings below were verified against current code (file:line cited). No source changed yet.

## Execution sequence (revised per review)

1. Citation diagnostics **+ authoritative final text** (item 1)
2. Capture/review the failed answers (item 2)
3. Contextual retrieval + bounded history (item 3 + 4)
4. Cancellation + dedup (item 5 + 6)
5. Markdown (item 7-md)
6. Operational: ownership, logging (item 8)
7. CI + docs (item 9) — pull earlier wherever convenient

---

### 1. Citation audit on original text + authoritative final answer  ✅ DONE

**Two coupled bugs.**

**(a) Audit after strip.** `orchestrator.py:267` strips fabricated markers, then `:273`
diagnoses the already-stripped text, so `unknown_ids` is always `[]`.
**Fix:** in `_final_event`, diagnose the original text first, then strip for display:
```python
diagnostics = _diagnose_citations(text, cited_claims)           # original
text = _strip_fabricated_markers(text, {c.claim_id for c in cited_claims})
self.last_answer = AgentAnswer(..., citation_diagnostics=diagnostics)
return FinalEvent(text=text)
```
Both call sites (:238, :253) route through `_final_event`. Update the two docstrings that
assert strip and audit share a set "so a stripped marker is exactly one reported as unknown"
— that coupling is what we're breaking.

**(b) `FinalEvent.text` is ignored; the wire carries raw tokens.** Fabricated markers already
streamed via `TokenEvent`s before `_final_event` sanitizes. In `executor.py`, the terminal
`complete()` uses `"".join(buffer)` (the raw token buffer, :176-178), the answer artifact is
built from streamed `TokenEvent` deltas (:131-136), and `FinalEvent` only closes the artifact
with an empty part (:138-143) — **the sanitized text is never emitted.** The evidence artifact
(`AgentAnswer`, :149) *is* sanitized, but the prose a reader sees is not.

**Fix:** make the sanitized `FinalEvent.text` authoritative across all four outputs:
- **Answer artifact:** on `FinalEvent`, replace the streamed artifact content with
  `event.text` (emit `last_chunk` with the full sanitized text under `_ANSWER_ARTIFACT_ID`,
  `append=False`), rather than closing with an empty part. Confirm the a2a-sdk artifact
  semantics allow a final replace; if append-only, emit a correcting final chunk and document
  why.
- **Terminal message:** `complete()` carries `event.text`, not the raw `buffer`.
- **Evidence artifact + persisted turn:** already use `answer.text` (sanitized) — keep.
- **Recovery path:** `recoverAssistant` must return the sanitized final text, not a replay of
  raw deltas, so a reconnect doesn't resurrect fabricated markers.

Carry the `FinalEvent` text out of `execute()` (don't rely on the buffer). Frontend stays as
is only if the artifact/message it renders is now the sanitized text.

**Tests:** `apps/agent/tests/` — fabricated-id run yields `unknown_ids == ["<bogus>"]` and a
`FinalEvent.text` with the marker removed. `apps/a2a-server/tests/` — the terminal message,
answer artifact, and recovery output all equal the sanitized text, not the raw token stream.

---

### 2. Capture & review the 5 flagged answers (don't assume cause)  ✅ DONE

The run file holds scores/criteria only — no answer text or cited claims. Built
`evaluation/blackbox/capture_flagged.py` (one-off, like `probe_004b.py`): brings up
`live_stack`, re-asks the 5 cases, and writes `review/flagged-<run_id>.jsonl` with answer +
cited claims + diagnostics + judge scores + a **rationale pass** (the suite judge returns only
numbers). Verdicts written to `review/FINDINGS-flagged-grounding.md`.

**Method corrected after review** (first attempt regenerated answers AND re-judged — confounded
answer change with judge variance — and judged only the short claim clause, omitting
`evidence_context`): now ask each case ONCE, FREEZE answer+evidence, re-judge the frozen answer
5×; save full `evidence_context` + offsets + provenance; a scope-audit pass that SEES THE PASSAGE
sorts each assertion into clause_supported / passage_supported_outside_claim / no_source_support.
Data: `review/flagged-20261001T204223Z.jsonl` (the flawed first file was deleted).

**Findings (revised):**
- **Judge is STABLE on a frozen answer** (stdev ≤ 0.05 every criterion). The earlier 0.2→0.85
  swing was the *answer* changing between runs — retracted. BUT borderline means sit on the 0.6
  cutoff (god-004=0.60; atonement-022=0.62, range crossing 0.60) so a straight ≥0.6 scalar gate
  would flap. Three of the five scored >0.6 this run — the "5 flagged" set is not a stable 5.
- **No fabrication found.** Buckets across 5 cases: clause_supported 25,
  passage_supported_outside_claim 18, no_source_support 2 (both an audit artifact — a two-marker
  sentence cross-checked against the wrong marker; content is in the sources). The statements
  earlier called "invented" are all present in the source paragraphs the agent received. The
  prior "four synthesis defects" verdict rested on a clause-only view the agent never had — WRONG.
- **The real open question:** the answer prompt (`domain/prompt.py:205-213`) shows the whole
  passage but states the cited CLAIM, not the passage, is the licence. The 18
  passage-outside-claim assertions are the system drawing on the shown passage via a narrower
  claim's marker. **Undecided policy — does a citation authorize the claim span or its containing
  passage? Decide before any gate.**

**Carried into items 3 & 4:**
- Item 3 — do NOT gate the raw ≥0.6 scalar (borderline flap); calibrate against frozen pass AND
  fail examples; if anything gates, tie it to the *decided* scope policy, not the scalar; consider
  folding a reasoning field into the judge (it returns only numbers today).
- Item 4 / answer prompt — **blocked on the scope decision.** Do not reflexively loosen the licence
  (would mask real fabrication) nor tighten to forbid passage use until we decide it's wrong.
- Open: required-evidence-pass + unused-claims does NOT prove a suitable claim existed per
  assertion; passage-outside-claim may also be a claim-granularity/retrieval gap. Not concluded.

---

### 3. Calibrate the judge, then gate — against pass AND fail examples  ✅ DONE (validated, NOT gated)

- Calibrate the LLM judge (`llm_judge.py`, `_PASS_THRESHOLD = 0.6`) against **both** the five
  failing cases **and** a sample of passing cases — tune so it tracks human judgment on both,
  not just the failures (avoid over-fitting the threshold to make 5 reds go green).
- Only once it tracks human judgment, promote a validated criterion (e.g. `semantic_grounding`
  for `corpus_reality == "sufficient"`) to **gating** in `evaluator.py:63`, keeping the
  gating/advisory split intact.
- If item 2 found real defects, fix them at their actual layer (retrieval, ranking, or prompt
  — whichever the evidence showed).

**Outcome (see `evaluation/blackbox/calibration/FINDINGS.md`, §Rubric 1.3):** built the
calibration harness and reworked `semantic_grounding` from the model's faulty averaging to a
**code-side deterministic floor** over per-assertion verdicts (rubric 1.2 → 1.3, hash
`275a9cc5683db397`; result `results/20261002T062115Z.jsonl`). The floor now runs — grounding
`parse_failure` 50 → 0 — and the wrong-marker / unsupported-attribute controls FAIL as designed,
targeted at the mis-cited clause. The judge-call path was also parallelized (~6.3× wall-clock:
410s → 65s for 60 tune calls; see `0029_parallelize-calibration-judge-calls.md`).

**No criterion was promoted to gating.** The judge still does **not** track human judgment on
grounding: FP fell 20 → 3 (a real gain, no longer confounded by failed calls), but FN rose 0 →
16, and the real positive `real-god-description-004` fails 4/5. The FN come from (a) the judge
inconsistently extracting meta/abstention sentences as substantive assertions, and (b) the
floor's "any uncited substantive assertion ⇒ fail" being stricter than the human label. Both are
rubric/label questions — fixing them must **not** loosen the floor (that reopens the
citation-integrity hole). All criteria stay **advisory**; graduation is deferred to a later,
separately validated step on a fresh holdout. The 7 holdout fixtures remain unjudged (joined-row
SHA `c158cba0…` unchanged).

---

### 4. Contextual retrieval + bounded history (size + turn count, excluded by sequence)

`executor.py:120` builds `AgentRequest(situation=situation)` from the latest message only;
follow-ups ("how does that relate to forgiveness?") have no prior turns, **and** retrieval
can't resolve "that".

**Correctness constraints from review:**
- The executor has **no `self._conversations`** — it holds `self._sessions` and constructs
  `ConversationRepository(session)` inside `self._sessions.unit_of_work()` per op (see
  `_append_message`, :84-89). History loading must follow the same pattern.
- Exclude the current message **by its returned `sequence`**, not by position:
  `_append_message` already returns a `ConversationMessage` with `.sequence` (repo :136-143) —
  fetch messages with `sequence < current.sequence`. Position-based "drop the last" is unsafe
  under concurrent appends.
- Bound by **both** turn count **and** a char/token budget — six turns could be enormous.
  Fetch only the needed tail from storage (new repo method with `ORDER BY sequence DESC LIMIT`),
  not `get()`-then-slice.

**Layers:**
- New repo method `history_before(conversation_id, before_sequence, max_turns, max_chars)` →
  returns the bounded tail (newest-first query, re-ordered oldest-first for prompting), both
  `max_turns=6` and `max_chars` applied (truncate/drop oldest past budget). Add to
  `ConversationRepository`.
- `ConversationTurn` — a frozen `role`+`text` dataclass — is defined in the **shared**
  application layer, alongside the symbol that consumes it: `src/application/mapping/map_situation.py`
  (plain stdlib dataclass, no pydantic — `src/application/` must not grow a pydantic dependency).
  It is **not** defined in the agent app's `AgentRequest` module: `AgentRequest` lives in
  `apps/agent/src/mind_of_christ_agent/application/answer.py` (a pydantic `BaseModel`), and defining
  the type there and importing it into the shared mapper would reverse the package dependency (shared
  importing from an app).
- `AgentRequest` (`apps/agent/.../application/answer.py:60`): `from application.mapping.map_situation
  import ConversationTurn`, add `history: tuple[ConversationTurn, ...] = ()`. No extra pydantic config
  needed — pydantic 2.13.5 accepts a frozen stdlib dataclass as a `BaseModel` field and validates its
  fields (`role: Literal["user", "agent"]`, `text: str`) from raw input; verified. Constants
  `HISTORY_TURNS = 6` and `HISTORY_MAX_CHARS` in `answer.py`.
- Executor: after persisting the user turn, open a unit of work, load
  `history_before(context_id, current.sequence, HISTORY_TURNS, HISTORY_MAX_CHARS)`, pass as
  `history=`.
- **Retrieval must use context (item 4 core): `map_situation` consumes bounded history.**
  Decided in design against the query-resolution alternative. A separate query-resolution
  LLM step would rewrite the follow-up into a standalone query, but that **is** interpretation
  and would add a **second** LLM entry point to the reasoning path — exactly what plan 0013
  (`0013:21-25`) rejects to keep "the one place an LLM enters the reasoning path". Resolving
  "that" from history is the same operation the mapper already performs (underspecified
  situation → retrievable concepts, cf. the "mind of Christ" → neighborhood case in
  `0013:27-32`), so it belongs in the mapper, not beside it.
  - Widen `SituationMapper.map` additively to `map(self, free_text, history=()) -> list[str]`. Complete wiring — every impl and call site:
    - `SituationMapper` Protocol (`map_situation.py:27`) and the `map_situation(mapper, free_text, history=())` free function (`:30`).
    - `PromptedSituationMapper.map` (`prompt.py:102`) — threads `history` into `user_prompt(free_text, history)`.
    - Orchestrator (`apps/agent/.../domain/orchestrator.py:97-98`): `asyncio.to_thread(map_situation, self._mapper, request.situation, request.history)`.
    - Test mapper impls: `_StubMapper.map` (`apps/agent/tests/test_orchestrator.py:38`) and any other test double gain the `history=()` param (so they satisfy the widened Protocol and can assert what history they saw).
    Default `history=()` keeps the no-history callers (eval, direct `map_situation` tests) compatible, but impls declaring only `map(free_text)` **must** be updated to match the Protocol.
  - History renders in the mapper's **`user_prompt`** (`prompt.py:60`), never `SYSTEM_PROMPT`: system instructions stay static, and role-labelled prior turns go into the user turn as a delimited block explicitly framed as context, not instructions. `user_prompt(free_text, history=())` gains the param; `PromptedSituationMapper.map` passes it through. The mapper must stay "deliberately dumb" (`map_situation.py:3`): it resolves pronouns/ellipsis into concept words, it does **not** start reasoning, causing, or advising.
  - The **original** question is still retained verbatim for the answer prompt (below) — history reaches retrieval through the mapper, not by rewriting what the user asked.
  Leaving the mapper on the bare current situation is **not** acceptable — it's the defect; feeding history only to the answer prompt is also insufficient, since retrieval (not the answer prompt) is what fails to resolve "that".
- Prompts (`prompt.py:174`, `:222`): render a delimited "Earlier in this conversation" block;
  prior turns are context, not instructions and not citable evidence (say so).

**Tests:**
- Repo: tail bounded by turns AND chars, excludes the current sequence.
- Executor: loads via a unit of work (no `self._conversations`).
- Mapper unit: `user_prompt` renders role-labelled history as a context block (and nothing when empty); `map_situation` with history resolves a follow-up's "that" into the prior turn's concepts, and with empty history is unchanged.
- **Orchestrator integration (required):** drive `run_stream` with an `AgentRequest` carrying `history`, using a stub mapper that records the `history` it received — assert it reaches the mapper, AND that the answer prompt still contains the original (un-rewritten) question. A mapper-only test can pass while production drops `request.history` at the `to_thread` call; only an end-to-end orchestrator test catches that.

---

### 5. Cancellation: obsolete-run guards + signal through network + real server cancel

**Frontend (`useA2AChat.ts`):**
- **Unmount cleanup** (no `useEffect` exists): `useEffect(() => () => abortRef.current?.abort(), [])`.
- **Guard ALL event consumption against obsolete runs**, not just token writes. `contextId`
  (:147) and `taskId` (:157) events mutate shared refs regardless of which run is live; a late
  event from a superseded run can clobber the current one. Tag each run (e.g. the run's
  `AbortController` or a run id) and in `consumeStream` ignore events whose run is no longer
  `abortRef.current` — covering context/task id updates too.
- **Recovery signal into the network layer:** thread `controller.signal` through `RecoverFn`
  (:40), `recoverAssistant` (`agentApi.ts:405`), and into the `RECOVER_MAX_POLLS` loop and its
  polling **waits** (abort the sleep, not just skip the next request). Update tests asserting
  the two-arg recover signature (`useA2AChat.test.tsx:373,426`).
- **Reset stale task id on send:** clear `lastTaskId.current` (and `lastAgentTurnId`) at the
  top of `send` (:177) so `canReconnect` (:299) can't reflect the previous run.

**Server (`executor.py:180`):** `cancel()` only emits a canceled status — it does **not** stop
the running `execute()` (the `async for` over `run_stream` keeps consuming, MCP subprocess
keeps working). Wire real cancellation: share cancel state per task (e.g. an `asyncio.Event`
or task registry keyed by `task_id`) that `execute()`'s loop checks and that tears down the
`async with connect()` block. Verify a cancel actually halts tool calls, not just the status.

**Tests:** unmount aborts the live controller; a late event from a superseded run is ignored;
recovery abort stops polling; server cancel stops the orchestrator loop (mock MCP, assert no
further tool calls after cancel).

---

### 7-md. One Markdown implementation: parse once, transform markers in the AST

`CitedAnswer.tsx:138` renders full Markdown (`MarkdownMessage`) only with no citations; once a
citation resolves, `CitedProse` (:143) splits the string and renders each run as a plain
`<span>`, so markdown renders literally — **and** parsing each segment independently (the naive
fix) breaks any construct spanning a citation (a bulleted list, a bold run) around the marker.

**Fix (explicit choice): parse the complete answer once, transform citation markers inside the
markdown syntax tree.** `react-markdown` + `remark-gfm` are already deps. Add a small remark/
rehype step (or a custom text-node renderer) that recognizes `[claim_id]` markers in text
nodes and replaces them with the citation `<sup>`/`<a>` element, so markdown is parsed on the
whole answer and citations are injected at marker positions. Do **not** split the string before
markdown. Keep `.cited-prose`/`agent-markdown` class parity (:141).

**Tests (`CitedAnswer.test.tsx`):** a cited answer with `**bold**`, a `- list`, and a citation
that falls mid-list renders real `<strong>`/`<li>` AND the inline superscript, with no literal
`[c1]` text and no broken list.

---

### 8. Operational: ownership (reads + writes + history) and executor logging

**Ownership — one trusted identity across every path.** Reads, A2A appends, and contextual
history loading are all currently unscoped; filtering REST reads alone leaves writes and
history exposed. Use **one** owner value, sourced from the same resolver the task store already
uses (`main.py:60`, `""` today) — never a client-supplied field.
- Schema: add `owner` to `ConversationRow` (Alembic migration after `0002_...`), **backfill
  existing rows** to the same default (`""`) consistently.
- Thread owner through **every** repo method: `list_conversations`, `get`, the new
  `history_before`, `append_message`, `rename`, `delete` — each filters/sets by owner; cross-
  owner access → `ConversationNotFoundError`/404.
- REST dependency (`get_conversations`) and the executor (user-turn append, history load, agent-
  turn append) all pass the resolved owner.
- `""` remains a shared anonymous scope today — document that; it becomes real the moment the
  resolver returns a user. (Decided: add the seam now.)
- **Tests:** cross-owner read, write (append), rename, delete, and continuation (loading another
  owner's history) all denied; same-owner all allowed.

**Executor logging (`executor.py:162`):** bare `except Exception:` returns static "Agent request
failed" with no logging; `task_id`/`context_id` are in scope but lost. Logging is already
configured (`main.py:38`). Add a module logger and
`logger.exception("agent run failed", extra={"task_id": ..., "context_id": ...})` inside the
catch (static message, structured fields) before the user-facing reply. Keep the blanket catch
(it must emit a terminal event) but log the cause.

---

### 9. CI + docs

**CI** (no `.github/`, no pre-commit): GitHub Actions running the existing checks —
`pip install -e ".[dev]"` + app extras, `pytest`, `pyright`, and `apps/web` `npm ci && npm run
test && npm run build`, with a Postgres service for a2a-server tests (compose already defines
one). Land this early.

**Docs** — README.md, CLAUDE.md, and `apps/mcp-server/README.md` describe `apps/agent`,
`apps/a2a-server`, `apps/web`, conversation history, the entity_relation channel, and the eval
harness as unbuilt/roadmap — all built with tests. Also stale: CLAUDE.md:100 "logging not used"
(it is), CLAUDE.md:158 "no `.env`" (exists, loaded in `main.py`). Update to current reality.

---

## Verification

- Python: `.venv/bin/python -m pytest tests apps/agent/tests apps/a2a-server/tests
  apps/mcp-server/tests -q` and `.venv/bin/pyright` (both clean). **Run the Python suite to
  completion** — the reviewer saw it stall after 453 passing tests; isolate any hang before
  claiming green rather than masking it.
- Frontend: `cd apps/web && npm run test && npm run build`.
- Eval: after item 1, rerun the blackbox harness with the judge
  (`--evaluators deterministic,classify,llm_judge`) and confirm `unknown_ids` populates on a
  fabrication; after item 2–3, confirm the intended cases move and the judge tracks the
  pass-sample too.
- Manual e2e: ask a question then a context-dependent follow-up and confirm "that" resolves and
  the answer uses prior turns; navigate away mid-stream and confirm the request aborts; cancel
  mid-run and confirm tool calls stop server-side; verify a cited answer renders markdown
  (list/bold intact) with inline citations.

## Decisions (confirmed)

- **Ownership (8):** add the owner column + filter now across reads, writes, and history,
  wired to the existing `""` resolver.
- **History bound (4):** last 6 turns **and** a char budget, fetched as a bounded tail and
  excluded by sequence.
- **Markdown (7-md):** parse the whole answer once; inject citations in the AST.
