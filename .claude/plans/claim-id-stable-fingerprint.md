# Stable `claim_id` on the `Claim` model

The first roadmap step after v3 (see `claim-extraction-scoring-and-prompt-v3.md`,
"Roadmap: after v3", item 1): *"Stable `claim_id` on the `Claim` model —
prerequisite, small. Today a claim is identified by `source_id` + evidence
offsets; every layer above must reference claims by a stable id, not
reconstructed offsets."*

## Process note

The master roadmap (`semantic-layer-design-and-roadmap.md`) says to write a
detailed plan for an increment only once its predecessor is done, and increment
#4 (the v3 work) is **not** marked done — dev relaxed R is ~0.72, below the 0.8
holdout gate, and the holdout run was deliberately not taken. This plan is drafted
ahead of that gate by explicit decision, because `claim_id` is the "prerequisite,
small" step: it's low-risk, adds no LLM behavior, and its scope does not depend on
the exact extraction score. It should still land only when it won't disturb an
in-flight v3.1 evaluation. It does **not** close increment #4.

## What a `claim_id` is here

A deterministic content fingerprint. **A claim id identifies a particular
assertion extracted from a particular source span — not merely a source span.**

The id is a hash of the claim's full signature, anchored by the **evidence quote,
not offsets**:

```
ClaimSignature = (
    source_id,
    evidence,        # the exact quote, guaranteed to occur once in the passage
    subject,
    predicate,
    object,
    polarity,
    mode,
    attribution,
)
claim_id = sha256(serialize(ClaimSignature))[:16]   # 16 hex chars
```

### Why quote, not offsets

The evidence quote is already required to occur **exactly once** in the passage
(the anchoring invariant in `anchor_claim`), so it is a validated-unique anchor to
the source text by construction. Offsets are worse: a harmless source-text edit
(a leading space, an OCR fix) shifts every subsequent offset, so an offset-based id
changes even though the claim did not. This is exactly the corpus caveat the
roadmap already warns about ("Passage IDs and offsets depend on the parser… Any
parser change moves them"). A quote-based id survives a re-parse as long as the
quote still appears.

### Why the full signature, not just the triple

Several claims routinely share one evidence span — this corpus is built that way
(4.8 claims/passage). "The Spirit, not the body, is the altar of truth" yields
`Spirit | is | altar of truth | affirmed` and `body | is | altar of truth |
negated` from the *same* quote. On the triple alone these nearly collide; it is
**polarity** that separates them. The `polarity`-not-`is_not` design (see Decisions
in the roadmap) exists precisely to keep such claims distinct, so hashing only the
triple would silently undo it. `mode` and `attribution` are in the signature for
the same reason — they are the fields `strict` scoring already treats as
claim-distinguishing over `loose`.

### Future split (documented, not built now)

Later, when a datastore is introduced (roadmap: "Embeddings and a database… when
#7 needs them"), identity may separate into two ids:

- `claim_id` — database identity (a UUID or serial), assigned by the store.
- `claim_fingerprint` — the deterministic content hash defined here.

At that point today's `claim_id` becomes `claim_fingerprint` and the DB id takes
the `claim_id` name. This plan builds only the deterministic hash and names it
`claim_id`; the rename is a later, mechanical increment. It is called out here so
the concept isn't re-argued.

## Serialization (exact, so it's reproducible and testable)

NUL-join with an explicit null-object sentinel, enums by `.value`:

```python
_NULL_OBJECT = "\x00NULL\x00"

def claim_signature(
    source_id, evidence, subject, predicate, object, polarity, mode, attribution
) -> str:
    parts = [
        source_id,
        evidence,
        subject,
        predicate.value,
        _NULL_OBJECT if object is None else object,
        polarity.value,
        mode.value,
        attribution.value,
    ]
    return "\x00".join(parts)

def compute_claim_id(...) -> str:
    return hashlib.sha256(claim_signature(...).encode("utf-8")).hexdigest()[:16]
```

- The `\0` separator can't appear in the source text or in a model's output for
  these fields, so it can't be confused with content; combined with the distinct
  null-object sentinel, `object=None` never hashes equal to `object=""`.
- 16 hex chars (64 bits) is ample for a prototype at this corpus scale;
  collision-free in practice and short enough to read in a run file.
- **Where it lives:** a new module `src/domain/claims/identity.py` (pure, no I/O),
  so both `anchor_claim` and any later layer compute the id the same way. Keep it
  in `domain/` because the fingerprint is a property of the entity, not of the
  extraction use case.

## Model change

`src/domain/claims/models.py` — add `claim_id: str` as the **first field** of the
frozen `Claim` dataclass (required, no default), with a one-line docstring note
that it's the deterministic fingerprint from `identity.py`, not a stored surrogate
key. First position makes it primary and impossible to forget at a construction
site.

Because `Claim` is a frozen dataclass, `__eq__`/`__hash__` now include `claim_id` —
but since the id is a pure function of the other signature fields, two claims are
equal on `claim_id` iff they were already equal on the signature. Equality
semantics are therefore unchanged for signature-equal claims; the only code that
compares whole `Claim`s is one test assertion (see Touchpoints).

## Touchpoints (from a full-repo inventory)

Exactly five sites name `Claim(`. The scorer keys on derived tuples, never on claim
identity, so **`claim_id` must stay out of `_loose_key`/`_strict_key`** — gold and
predicted claims get independently-computed ids, but identical signatures produce
identical ids, so in practice a matched gold/predicted pair *will* share a
`claim_id`. That's a nice property but must not be relied on by the scorer.

### Production

1. `src/application/extraction/extract_claims.py:138` — `anchor_claim`, the single
   production factory (live extraction *and* gold loading both flow through it).
   Compute `claim_id` here from the resolved evidence quote + signature fields and
   pass it into the `Claim(...)` constructor. This is the only place the id is
   *computed* for real claims.
2. `evaluation/claims/run.py:104-122` — the manual per-claim dict for each
   `{"type": "claim", ...}` JSONL line. Add `"claim_id": claim.claim_id` as the
   first field after `"type"`, so run files persist it. (Header/rejected lines use
   `asdict` on other dataclasses — untouched.)
3. `evaluation/claims/near_miss.py:29-41` — `_claim_from_line` reconstructs a
   `Claim` from a run line. It must supply `claim_id`. Two options, decide in
   implementation: (a) read it from the line when present, else recompute via
   `identity.py`; (b) always recompute from the signature fields it already reads.
   Prefer **(b) recompute** — it makes old run files (written before this change,
   lacking the field) work with no special-casing, and it means near_miss never
   depends on the writer having stored a correct id. Add a test that a line
   *with* a stored id and a recomputed id agree.

### Tests

4. `tests/test_claims_score.py:6` — module-level `NATURAL = Claim(...)`; add
   `claim_id` to this one literal. `PURIFICATION` and all other fixtures derive via
   `replace(NATURAL, ...)` and inherit it. **Caveat:** several tests pass `NATURAL`
   and a `replace`-derived variant together expecting them to be *distinct* claims.
   `replace()` does **not** recompute `claim_id`, so a derived fixture keeps
   `NATURAL`'s id even though its signature changed. This is fine for the scorer
   (it keys on signature tuples, not id) but means fixtures no longer satisfy the
   "id is a function of signature" invariant. Resolve by giving fixtures ids via a
   small helper that computes the id from the fields (so `replace` users call the
   helper, or the test constructs through `anchor_claim`). Keep this contained to
   the fixtures; don't let it leak into production.
5. `tests/test_claims_near_miss.py:15` — module-level `GOLD = Claim(...)`; same
   treatment as #4.
6. `tests/test_extraction.py:61` — `assert claim == Claim(...)`, the only
   whole-`Claim` equality in the suite and the highest-risk breakage. The literal
   must include the exact `claim_id` `anchor_claim` now produces. Rather than
   hand-computing a hash into the test, assert the id separately: keep the
   structural equality by comparing `replace(claim, claim_id=...)` against the
   literal, and assert `claim.claim_id == compute_claim_id(...)` on its own. This
   keeps the test meaningful without pinning a magic hex string.

`tests/test_claims_gold.py` constructs no `Claim` directly and asserts only on
individual fields — unaffected.

## New tests for the id itself

`tests/test_claims_identity.py`:

- Same signature → same id (determinism), across two independent computations.
- Two claims sharing one evidence quote but differing in one signature field each
  (subject, then predicate, then object, then polarity, then mode, then
  attribution) → six distinct ids. The polarity case is the important one (the
  Spirit/body example): same triple, opposite polarity, different id.
- `object=None` and `object=""` produce different ids (the sentinel works).
- The NUL-join is unambiguous: `subject="a", object="bc"` vs `subject="ab",
  object="c"` (with all else equal) → different ids.
- A quote-based stability check: two `Claim`s identical except for
  `evidence_start`/`evidence_end` (same quote, shifted offsets) → **same** id.
  This is the offsets-don't-matter guarantee, and it doubles as documentation.

## Backward compatibility

Committed run files under `evaluation/runs/` were written before this field
existed. Because `near_miss._claim_from_line` recomputes the id (option b above),
those files keep working unchanged — no migration, no re-run. New run files carry
`claim_id`; old ones don't, and that's fine. Note this in the run file / results
log convention if anything downstream starts to assume the field is present.

## Steps (each its own commit)

1. **`domain/claims/identity.py` + its tests.** Pure hashing, no model change yet.
   `compute_claim_id` and `claim_signature`, plus `tests/test_claims_identity.py`.
   Nothing else references it — commit measures the hash in isolation.
2. **Add `claim_id` to `Claim`, compute it in `anchor_claim`, fix the fixtures.**
   Model change + `extract_claims.py` + the three test files (#4–#6). After this,
   `pytest` + `pyright` pass and every `Claim` in the system carries a correct id.
   No serialized-output change yet, so scores can't move (the scorer ignores the
   id) — verify by re-scoring a committed run file and confirming identical
   numbers.
3. **Persist and round-trip the id in run I/O.** `run.py` writes `claim_id`;
   `near_miss._claim_from_line` recomputes and (optionally) verifies it against a
   stored value. Add the round-trip test. Optionally re-emit one run file so a
   committed example carries the field, or leave existing files as-is (they still
   work) and note new runs include it.

## Verification

- `.venv/bin/python -m pytest tests -q` green.
- `.venv/bin/pyright` clean (only the pre-existing third-party missing-import
  noise remains).
- Re-score a committed v3.1 run (`evaluation/runs/20260923T210128Z.jsonl`) after
  step 2 and confirm loose/strict/relaxed are byte-identical to the recorded log
  values — proves the id is inert to scoring.
- `near_miss` runs unchanged against an old (pre-field) run file and a new
  (with-field) one, producing the same near-miss set for the same claims.

## Not in this plan

- The `claim_id` / `claim_fingerprint` split — deferred to the datastore
  increment; only the deterministic hash is built now.
- Any use of the id (`extract_mentions`, `resolve_entities`). This step only
  *mints* the id; the next roadmap increments consume it.
- Changing the scorer to use the id. It stays signature-keyed on purpose.
