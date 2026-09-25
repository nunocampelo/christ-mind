# Plan: Evidence-bounded synthesis + relevance-ranked retrieval

## Context

A review of the christ-mind agent's first real outputs surfaced three problems, in
priority order:

1. **Synthesis outruns evidence.** On "describe God," the agent produced genre-fitting
   interpretive prose the cited claims don't support ("God does not create at a
   distance," "any description remains a pointer... known through experience"). The
   existing prompts forbid *inventing Course teachings* and *presenting synthesis as a
   single Course statement*, but they do **not** forbid a third level: unsupported
   interpretive/psychological commentary layered on top of real citations.
2. **The retrieval-failure path breaks the epistemic contract.** On a query with no
   retrieved claims, the agent switched into generic relationship advice ("your steady
   presence speaks more than words") — uncited psychological wisdom that *sounds*
   grounded. The prompts have no "insufficient evidence — say so and stop" instruction.
3. **Retrieval is lexical, not semantic.** `find_claims` etc. are unranked case-
   insensitive substring matches. "Describe God" surfaces "I stand below God" (God as
   object/incidental) with the same weight as "God offers only mercy" (God as subject of
   a characterizing relation). The review's §5 "entity characterization query" is
   achievable *deterministically* using the `Claim` structure already extracted.

The system is more built-out than the review assumed. The **cited-vs-inferred invariant
is already structural** (`AgentAnswer`, `_absorb`, the wire `"evidence"` artifact) — so
the review's §4 "three levels" is *partially* solved: levels 1 (cited) and 2 (inferred
chains) are separated in code. This plan adds the missing **level-3 suppression**
(interpretation) in the prompts, plus the failure contract and deterministic ranking.

Scope decided with the user: **both, synthesis first; deterministic ranking only** (no
embeddings — that's a later, larger change behind these same signatures).

---

## Part A — Synthesis contract (do first; cheap, high-impact, no infra)

**File:** `apps/agent/src/mind_of_christ_agent/domain/prompt.py`

Both `DECISION_SYSTEM_PROMPT` and `ANSWER_SYSTEM_PROMPT` produce final prose and must
stay consistent (a change to one must be mirrored in the other). Add the following rules
to **both**, preserving the existing cited-vs-inferred language (do not remove it):

1. **Suppress interpretation (level 3).** Every substantive statement about what the
   Course teaches must be traceable to a specific cited claim or a marked inferred chain.
   Do **not** add interpretive framing, spiritual commentary, therapeutic guidance, or
   common-sense psychological observations that the cited claims don't support — even
   when they sound fitting. Ban the specific genre tells the review flagged: no "the
   picture that emerges," "the Course would remind us," "known more fully through
   experience than definition," or similar.
2. **Narrowest formulation.** Prefer the narrowest wording the evidence justifies. Do not
   strengthen "God gave them His peace" into "God's nature is peace" unless a cited claim
   says the stronger thing. Preserve the semantic roles (subject/verb/object) of the
   claim being paraphrased — do not introduce a subject, object, or relation the claim
   doesn't carry (this is the `God created your own will` vs *"which He created in the
   likeness of His Own"* mismatch).
3. **Insufficient-evidence contract.** When the cited claims don't sufficiently address
   the situation, say so plainly and do **not** fill the gap with uncited knowledge or
   plausible interpretation. Offer to look further given more situational detail, or
   stop — but never substitute generic advice for missing citations. (This is the
   loved-one failure mode.)
4. **No framing transfer** (added after a second review round). Do **not** carry a
   property or relationship from the *person's question* onto the cited claims just
   because the concepts are related. Observed leak: asked how to love an *enemy* with
   claims that only speak of extending *forgiveness to others*, the model concluded "the
   Course points toward loving enemies through forgiveness" and that the "others" are
   enemies — neither is in the evidence. Answer with what the claims establish, then name
   the part of the framing (enemy, love-of-enemy) the claims don't reach. This is the
   residual level-3 drift: not invented commentary, but binding the user's wording to
   evidence that doesn't support the binding.

Keep the additions tight and imperative — match the existing terse prose style, no
bullet-doc bloat in the prompt itself.

**Note on the fallback path:** `ANSWER_SYSTEM_PROMPT` only fires when `max_steps` is
exhausted. The normal path is `DECISION_SYSTEM_PROMPT` emitting `{"final": ...}`. Both
must carry the identical contract or behavior differs by path.

### Tests (Part A)

`apps/agent/tests/` (mock the MCP transport / LLM, per CLAUDE.md — never mock the
application layer). Existing `test_orchestrator.py` shows the mocking pattern.

- Given a stubbed decision stream that yields a `{"final": ...}` with an empty
  `cited_claims`/`inferred_chains` accumulator, assert the orchestrator still produces a
  `FinalEvent` (behavior unchanged) — the *content* contract is prompt-enforced and not
  unit-assertable, so this test guards the plumbing, not the prose.
- If practical, add a prompt-content regression test in `tests/test_prompt.py` asserting
  both prompts contain the insufficient-evidence and no-interpretation clauses (a cheap
  guard that a future edit doesn't silently drop one of the two).

---

## Part A.1 — Polarity preservation (hard grounding invariant; added after review round 3)

**Root cause (confirmed by inspecting the data, not guessed):** the stored corpus is
correct — `t1-1-86` "God is partial", `t3-4-8` "God is stranger to His Sons", and
`t4-1-12` "God is author of fear" are all stored `Polarity.NEGATED`. The MCP wire schema
(`ClaimResult`) carries `polarity`. But the agent's `CitedClaim` DTO **dropped it**, and
`answer_user_prompt` rendered each claim as bare `subject verb_phrase object` — so the
model literally saw "God is partial" with the negation surviving only in the (unrendered)
evidence span. The model faithfully reported the affirmative it was shown. This is a
data-flow bug, not a prompt bug: no synthesis rule can recover a field that isn't in the
prompt.

**Fix (implemented):**
- `apps/agent/.../application/answer.py` — add `polarity: str` to `CitedClaim`.
- `apps/agent/.../domain/orchestrator.py::_to_cited_claim` — populate it from the tool
  result (`item.get("polarity")`).
- `apps/agent/.../domain/prompt.py::answer_user_prompt` — render each claim with a
  `[NEGATED]` marker and its **exact evidence span** attached, so negation is visible and
  the evidence (authoritative) travels with the proposition.
- Both prompts — new rule: *preserve polarity exactly; evidence span > structured fields >
  label when they conflict; never convert explicit negation to affirmation.*
- Web parity: `apps/web/.../api/agentApi.ts` (`CitedClaim` type + validator) and
  `CitedAnswer.tsx::claimGloss` had the **same** bug — the gloss read "God is partial"
  above a "God is NOT partial" blockquote. Gloss now prefixes negated claims with "Not:".

**Tests (implemented):**
- Claim-extraction layer — `tests/test_claims_repository.py`: assert the three known
  negated claims are stored `NEGATED` (locks the data a re-extraction could flip).
- Agent layer — `apps/agent/tests/test_orchestrator.py`: polarity survives tool result →
  `CitedClaim`. `apps/agent/tests/test_prompt.py`: negated claim renders with `[NEGATED]`
  + evidence; affirmed claim has no marker; both prompts carry the polarity rule.
- Web layer — `CitedAnswer.test.tsx`: negated gloss reads "Not: God is partial", not
  "God is partial".

**Still open (frontend, not confirmed):** the empty `1. 2. … 14.` ordered-list artifact
seen before the prose. The reasoning-timeline `<ol>` and the hook both correctly skip
empty step text (`useA2AChat.ts` gates on `if (event.text)`), so the source is not there.
It needs a live DOM repro to pin down (likely a markdown quirk in the streamed answer or
`CitedAnswer`'s inferred-chain `<ol>`). Deferred — a regression test asserting the final
render has no empty ordered-list items should land once the source is identified.

## Part B — Deterministic *characterization* ranking (do second)

Goal, scoped tightly to the problem "describe God" revealed: rank claims where the query
**entity is the subject of a characterizing relation** ahead of claims where it appears
incidentally — **only on the characterization path** (`find_claims_for_entity`). Do NOT
make this the universal ranking for `find_claims`: the same weights are wrong for other
intents ("what causes fear?" wants `fear` in *object* position; "what causes God?" wants
object position too). Ranking is an intent-specific strategy, not a universal relevance
function. No new backend, no embeddings — stays in `application/`, unit-testable.

**New file:** `src/application/retrieval/ranking.py` — a *strategy-specific* function,
named for its intent so it can sit beside future strategies:

```
def rank_characterization_claims(claims: list[Claim], entity: str) -> list[Claim]:
    # stable sort by descending score; ties keep corpus/extraction order
```

**Predicate roles, not a flat predicate set.** Introduce a small classification so the
ranking table is explicit about *why* a predicate is preferred, rather than lumping
unlike predicates together. Roles (mapping the closed `Predicate` enum):

```
PredicateRole.ATTRIBUTE     # IS                — a property of the subject
PredicateRole.CREATIVE      # CREATES, MAKES    — the subject brings X into being
PredicateRole.GIVING        # (giving/having, where the corpus expresses it)
PredicateRole.CAUSAL        # CAUSES            — an effect involving the subject
PredicateRole.RELATIONAL    # REQUIRES, EXPRESSES, UNDOES
PredicateRole.CONTRASTIVE   # CONTRASTS_WITH
PredicateRole.OTHER         # OTHER
```

For *characterization*, prefer `ATTRIBUTE` > `CREATIVE` > `GIVING` > `RELATIONAL`/`CAUSAL`
> `CONTRASTIVE` > `OTHER`. (`CAUSES`/`REQUIRES`/`MAKES` describe relations/effects, not
attributes — do not label them all "attributive.")

Scoring signals (deterministic, from fields already on `Claim`; small weighted sum with a
documented, stable tie-break — not ML):
- **Primary — position:** the entity in *subject* position outranks object position,
  which outranks a verb_phrase-only match. A subject-position claim characterizes the
  entity; an object/incidental one usually doesn't.
- **Secondary — predicate role**, per the ordering above.
- **Tie-breakers only — polarity and attribution.** `AFFIRMED` edges out negated as a
  *tie-break*, not a strong signal: a negated claim can be highly characterizing ("God is
  NOT partial"), so it must not be treated as low-quality evidence — only ranked just
  below an equally-scored affirmed claim. Likewise `COURSE` vs `OTHERS`/`EGO` is a weak
  tie-break at most; do **not** encode "COURSE = intrinsically relevant" unless that
  becomes an established corpus-wide retrieval rule.

**Wire it in** (ranking reorders; `limit` slice applies *after* ranking):
- `src/application/retrieval/find_claims_for_entity.py` — apply
  `rank_characterization_claims` before slicing. This is the entity-characterization path
  (surface-form join already exists) and the one the "tell me about X" tool uses.
- `src/application/retrieval/find_claims.py` — **leave ordering unchanged.** No explicit
  retrieval intent lives here yet; applying characterization weights would silently
  change generic-search semantics. Revisit only when a query-intent signal exists.
- `src/application/retrieval/find_sources.py` — **fix the latent case bug** here (the
  concepts branch does `needle in concept` without lowercasing the concept side,
  `find_sources.py:24`); lowercase it to match `find_claims`. No ranking change.

**Update the MCP tool docstring** in
`apps/mcp-server/src/mind_of_christ_mcp/server.py`: `find_claims_for_entity`'s docstring
should note it now returns claims characterization-ranked (subject-position first). Leave
`find_claims`'s "extraction order, not ranked by relevance" docstring as-is (still true).

Do **not** change any tool return shapes, the `find_*` signatures, or the
cited-vs-inferred split. **Ranking is ordering-only — never filtering.**

### Tests (Part B)

`tests/` (root; plain `@dataclass` fixtures, construct real `Claim`s — no `dict`
literals, no truthiness-only asserts, per CLAUDE.md).

- **New** `tests/test_ranking.py`: build a small set of real `Claim`s mirroring the "God"
  case — a subject-position `ATTRIBUTE`/`CREATIVE` claim, an object-position `OTHER`
  claim, and a subject-position *negated* claim ("God is NOT partial"). Assert:
  subject-position characterizing claim ranks first; the object-position/incidental one
  ranks below it; the negated subject claim ranks *between* them (below an equal affirmed
  claim, but not dumped to the bottom — polarity is a tie-break, not a filter). Assert
  stable tie-break (equal scores keep input order). Assert every input claim is present
  in the output (ordering-only, never filtering).
- Extend `tests/test_find_claims_for_entity.py`: existing match/limit/empty/no-match tests
  must still pass unchanged (ranking must not drop or add matches, only reorder), plus one
  assertion that a subject-position characterizing claim precedes an incidental match for
  the same entity.
- `tests/test_find_claims.py` — no ranking assertions added (ordering intentionally
  unchanged there); existing tests must still pass.
- Add a `find_sources` case-bug regression to `tests/test_retrieval.py`: a source tagged
  with a mixed-case concept matches a lowercased query.

---

## Verification (end to end)

From the repo root, in order:

```bash
.venv/bin/python -m pytest tests -q                 # root: ranking + retrieval
.venv/bin/python -m pytest apps/agent/tests -q       # agent: orchestrator plumbing
.venv/bin/pyright                                    # root src/ + apps/*/src
```

Manual smoke of the two review scenarios via the CLI (drives the real orchestrator +
MCP subprocess):

```bash
.venv/bin/python -m mind_of_christ_agent "Can you describe God?"
# Expect: characterizing claims (giver of life, mercy, created Souls, gave peace) appear
# AHEAD of incidental matches ("I stand below God", "God WOULD be mocked") within the
# returned limit -- ordering only, not filtering (limit governs absence, not ranking); no
# invented "picture that emerges" / "known through experience" interpretive prose.

.venv/bin/python -m mind_of_christ_agent "My loved one says she doesn't believe she is loved"
# Expect: if retrieval is thin, a plain "the cited claims don't sufficiently address
# this" — NOT generic relationship advice presented as grounded.
```

## Out of scope (explicitly)

- Semantic/embedding retrieval (later change behind the same `find_*` signatures).
- Collapsing the user-facing "The Course says" evidence list into grouped snippets — the
  repetition is the traceability surface for this eval phase; revisit at the frontend
  rendering layer, keeping all claim IDs in the `"evidence"` artifact.
- Any change to the cited-vs-inferred structural invariant.
