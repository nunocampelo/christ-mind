# Increment #9: situation → concept mapping

## Context

The semantic layer's roadmap (`.claude/plans/semantic-layer-design-and-roadmap.md`) is at
its last unbuilt step. #7 (claims in retrieval) and #8 (deterministic claim chaining) are
done and committed; the whole retrieval+synthesis path is deterministic and cited. #9 adds
the **one** place an LLM enters the reasoning path: mapping a user's free-text situation to
candidate concept mentions. It was deliberately split out of #8 (see the "Deferred to #9"
section of `synthesis-and-interpretation.md`) precisely because its failure modes are
probabilistic and mixing them with deterministic chaining would make failures hard to
localize.

The intended outcome: `map_situation("I keep getting angry when criticized")` returns
`["anger", "criticism", "judgment", ...]` — a deliberately **dumb** list of concept
mentions, **never** an interpretation like "this is caused by…". The agent then feeds those
mentions into #7's `find_claims_for_entity` / #8's `chain_claims`, so the LLM interprets
only the *situation*; everything downstream stays deterministic and cited. This preserves
the roadmap's core invariant — "the Course says X" is never conflated with "this follows
from what it says".

Decisions confirmed with the user:
- **Free-form, unconstrained output.** The mapper emits whatever concept words fit; a
  mention absent from the corpus simply returns nothing downstream. No candidate list to
  choose from (unlike the resolver). Misses become a measurable recall signal.
- **Set precision/recall per situation** as the metric (order-independent set overlap
  vs. an expected concept set, averaged across situations).
- **Reuse the existing `anthropic_proxy`** adapter for the `Complete` function.
- **Retrieval concepts, not literal concepts.** The gold labels (and the prompt) name the
  concepts that open the *claim space* relevant to a situation — including ones the person
  never said ("I lied and feel awful" → also `forgiveness`) — not a literal-semantics
  annotation of the sentence. The pipeline is situation → retrieval concepts → relevant
  claims; the mapper labels the middle. This makes recall the metric that matters and
  explains the deliberately-low precision: casting a wide net is correct when a
  corpus-absent concept just returns nothing downstream. Holdouts therefore test **novel
  concept combinations** and **surface language far from corpus terminology** (semantic
  abstraction), not just recombinations of the dev concept clusters.

## What #9 mirrors (existing patterns to reuse, not reinvent)

#9 is a third narrow, gold-scored LLM pass alongside extraction (#2–#5) and resolution
(#6). It copies their shape exactly:

- **Adapter + prompt module**, mirroring `src/application/resolution/prompt.py`: a
  `type Complete = Callable[[str, str], str]`, a `SYSTEM_PROMPT` that is the single
  statement of the mapping rules, a `MAP_VERSION` (relabel the gold + bump on any rule
  change), a `parse_response`, and a `PromptedSituationMapper` wrapping a `Complete`.
- **Use-case module + protocol/error**, mirroring `src/application/extraction/extract_claims.py`:
  a `SituationMapper` `Protocol`, a `MappingFailedError(Exception)` raised when a reply
  can't be parsed, and the top-level `map_situation` entry point.
- **Provider adapter** already exists: `src/infrastructure/llm/anthropic_proxy.py` supplies
  a `Complete` (used by extraction/resolution). Add a `make_mapper` factory there, matching
  the existing `make_extractor`/`make_resolver` factories.
- **Evaluation package**, mirroring `evaluation/entities/` (gold.py, score.py, run.py,
  run_format.py, gold/, runs/): a small gold set, a set-P/R scorer, and a runner that
  writes a versioned run record with the same header/provenance shape.
- **Downstream contract**: output is `list[str]` of surface-form mentions. `find_claims_for_entity`
  (`src/application/retrieval/find_claims_for_entity.py:16`) and `chain_claims`
  (`src/application/synthesis/chain_claims.py:41`) both already take a plain string
  `mention` — there is **no separate `concept` type** to build, and none should be added.

## Steps

Each step its own commit, core → wire boundary, same as #7/#8.

### 1. `map_situation` use case + prompt (transport-free, LLM behind an adapter)

`src/application/mapping/map_situation.py` and `src/application/mapping/prompt.py`
(new `application/mapping/` package with an empty `__init__.py`, per the repo's
empty-`__init__` rule).

- `prompt.py`:
  - `MAP_VERSION = "1.0"`; `type Complete = Callable[[str, str], str]`.
  - `SYSTEM_PROMPT`: the single statement of the mapping rules. Must instruct the model to
    return **only** a JSON object `{"concepts": ["...", ...]}` of short concept mentions
    (noun phrases in the Course's register — "anger", "guilt", "criticism", "judgment"),
    and to **never** return sentences, causal claims, advice, or "the Course says…" —
    deliberately dumb, situation → concept words only. State that it may return concepts
    the corpus might not contain (free-form, unconstrained).
  - `parse_response(text) -> list[str]`: strip code fence (reuse the resolver's
    `_strip_code_fence` shape), `json.loads`, validate it is `{"concepts": [str, ...]}`,
    reject invented structure (non-list, non-string members) by raising `ValueError`
    → wrapped as `MappingFailedError`. Normalize trivially (strip whitespace; drop empties;
    dedupe preserving first-seen order) so the output is clean mentions.
  - `PromptedSituationMapper(complete: Complete)` with `map(free_text) -> list[str]`;
    blank input → `[]` without calling the model.
- `map_situation.py`:
  - `class SituationMapper(Protocol)` with `map(self, free_text: str) -> list[str]`.
  - `class MappingFailedError(Exception)` — static message, chained `from e`, never
    interpolating the model text (per CLAUDE.md error handling).
  - `def map_situation(mapper: SituationMapper, free_text: str) -> list[str]` — the entry
    point (thin; blank input → `[]`).
- Tests (`tests/test_mapping.py`, root): drive a **stub `Complete`** returning canned JSON
  (no network). Assert exact concept lists by equality; assert blank input → `[]` without
  calling the stub; assert a reply that is a sentence / bare list / missing key raises
  `MappingFailedError`; assert whitespace/dedupe normalization. Mock the provider boundary
  (the `Complete`), never the application layer — matches the extraction/resolution test
  discipline.

### 2. `make_mapper` provider factory

`src/infrastructure/llm/anthropic_proxy.py`

- Add `make_mapper() -> SituationMapper` returning `PromptedSituationMapper(<the existing
  Complete>)`, mirroring the file's existing `make_extractor`/`make_resolver` factories so
  the eval runner can load it by `module:factory` spec. No new dependency (`anthropic` is
  already declared and imported here).

### 3. Situation → concept gold set + scorer + runner

`evaluation/mapping/` (new package: `__init__.py`, `gold.py`, `score.py`, `run.py`,
`run_format.py`, `gold/`, `runs/`), mirroring `evaluation/entities/`.

- `gold/situations.jsonl`: a handful (≈8–12) of representative situations, each
  `{"situation": "...", "concepts": ["...", ...]}`. Hand-authored; the expected concepts
  are the surface forms a good mapper should surface. Keep a `holdout` split analogous to
  the entities gold (`t1_1_holdout.jsonl`) so a reported number isn't tuned on.
- `gold.py`: a `GoldSituation` frozen dataclass and `load_gold_situations(path)` (loud
  failure on a malformed record, mirroring `evaluation/entities/gold.py`).
- `score.py`: **set precision/recall per situation.** For each situation compute
  `predicted ∩ expected` over the concept sets; aggregate to macro P/R/F1 (mean across
  situations). Concept-set comparison is case-insensitive / whitespace-normalized to match
  the mapper's own normalization, so casing alone isn't a miss. A `MappingScore` /
  `MappingReport` frozen-dataclass pair with `precision`/`recall`/`f1` properties, mirroring
  `PairScore`/`PairReport`.
- `run.py`: CLI `python -m evaluation.mapping.run --mapper infrastructure.llm.anthropic_proxy:make_mapper`
  (`--record` to write, `--holdout` only to report — never while tuning), mirroring
  `evaluation/entities/run.py`. Loads the factory by spec, runs each gold situation through
  the mapper, scores, and (`--record`) writes `runs/<run_id>.jsonl` with a header carrying
  `MAP_VERSION`, the run id/timestamp, and the gold file hash (reuse the entities runner's
  header/provenance shape). Commit the run record.
- `run_format.py`: the run-record header dataclass, mirroring `evaluation/entities/run_format.py`.
- Tests (`tests/test_mapping_gold.py`): `load_gold_situations` loads the committed gold and
  fails loudly on a malformed record; `score.py` returns the expected P/R/F1 on a tiny
  hand-built `(predicted, gold)` example asserted by exact value (construct real
  `GoldSituation`s, not dict literals — per the no-`dict` test policy).

### 4. Roadmap + plan updates (docs, no code)

- Mark #9 **done** in `.claude/plans/semantic-layer-design-and-roadmap.md`'s roadmap table
  and intro once steps 1–3 land and a scored run exists.
- Write `.claude/plans/situation-concept-mapping.md` (the detailed #9 plan promoted from
  this scratch file) with a Results log recording `MAP_VERSION`, the dev-set P/R/F1, and the
  committed run id — matching how #4/#6 recorded their scored results.

## Scope guards (what #9 is NOT)

- **No ranking / relevance scoring** of concepts. Output is an unordered set; the scorer is
  set-based. Ranking is later work if a real query needs it.
- **No interpretation.** The mapper never emits claims, causes, advice, or "the Course
  says…". If a rule tempts it toward interpretation, that rule belongs downstream (#8
  chaining), not here.
- **No new MCP tool in #9.** #9 delivers the mapper + its eval; the agent composes
  `map_situation` → `find_claims_for_entity` / `chain_claims`. (Whether to expose
  `map_situation` as its own MCP tool is a separate, later decision — the extractor and
  resolver aren't MCP tools either.)
- **No `concept` domain type, no candidate-vocabulary index, no embeddings/datastore.**
  Output is plain `list[str]`; corpus misses are a signal, not a bug.

## Verification

From the repo root, after each step:

```bash
.venv/bin/python -m pytest tests -q          # step 1 & 3 unit tests, all pass
.venv/bin/pyright                            # clean (now resolves against .venv)
```

End-to-end (step 3, real provider — needs the anthropic proxy credentials the existing
extraction/resolution runs use):

```bash
# Dev-set score while iterating (never --holdout while tuning)
.venv/bin/python -m evaluation.mapping.run --mapper infrastructure.llm.anthropic_proxy:make_mapper

# Record a run to commit
.venv/bin/python -m evaluation.mapping.run --mapper infrastructure.llm.anthropic_proxy:make_mapper --record
```

Manual composition sanity check (no MCP needed — the point is the deterministic hand-off):

```bash
.venv/bin/python -c "
from infrastructure.llm.anthropic_proxy import make_mapper
from application.mapping.map_situation import map_situation
from application.retrieval.find_claims_for_entity import find_claims_for_entity
concepts = map_situation(make_mapper(), 'I keep getting angry when criticized')
print('concepts:', concepts)
for c in concepts:
    print(c, '->', len(find_claims_for_entity(c)), 'claims')
"
```

Expect a short, sentence-free concept list, with corpus-present concepts returning claims
and absent ones returning `[]` (the recall signal). Git commits are left to the user
(no self-commit).

## Status: implemented

Steps 1–3 built; step 4 (this file + the roadmap tables) done. All new code lands under
`src/application/mapping/`, `src/infrastructure/llm/anthropic_proxy.py` (`make_mapper`),
`evaluation/mapping/`, and `tests/test_mapping.py` + `tests/test_mapping_gold.py`. Full
suite 182 passing; pyright clean. No MCP tool added (by design). Changes are staged, not
committed.

### Results log

| Run | `MAP_VERSION` | Set P | Set R | Set F1 | Notes |
| --- | ------------- | ----- | ----- | ------ | ----- |
| `runs/20260925T202235Z.jsonl` (dev) | 1.0 | 0.294 | 0.889 | 0.442 | Real `anthropic_proxy` mapper over the 9-situation dev gold. Recall is the metric that matters (see the retrieval-concept decision); low precision is the deliberate wide net — extra concepts absent from the corpus return `[]` downstream, so they cost nothing. Holdout deliberately not scored yet (reserved as unseen data; only `--holdout` at report time, never while tuning). |

The two revised holdout situations were spot-checked (not scored) to confirm semantic
abstraction over keyword matching: "manager is out to get me / read every email as a
threat" → `projection, perception, misperception, …`; "everybody clicked, I don't belong"
→ `separation, specialness, the ego, …` — neither relies on lexical overlap with its gold
concepts.
