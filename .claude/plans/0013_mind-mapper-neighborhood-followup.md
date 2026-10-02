# Follow-up plan: consistent targeted retrieval via mapper neighborhood expansion

## Context

Deferred from the sources-display work. A reviewer observed that two structurally identical
questions retrieved inconsistently:

```
"mind of God"    → seed → targeted follow-up ("mind of God / God's Mind / Thoughts of God")
                 → 2 more claims → synthesis
"mind of Christ" → seed → NO targeted follow-up → synthesis on thinner evidence
```

Both should apply the same test — "does the gathered evidence actually address the entity
asked about?" — and search the conceptual neighborhood when it doesn't. Today that decision
is made **reactively by the model in the ReAct loop**, so it fires for one query and not the
other. The inconsistency is the symptom; the reactive placement is the cause.

## The architectural choice

The system deliberately concentrates LLM interpretation in `map_situation`
(`src/application/mapping/map_situation.py`) — "the one place an LLM enters the reasoning
path". A reactive "directness test → search variants" rule in the orchestrator would add a
**second** interpretation point in the loop and require a non-LLM definition of "direct hit"
(brittle: substring match on the entity is exactly what already returned nothing).

**Chosen direction: expand in the mapper, up front.** When the situation names an
entity/concept (e.g. "the mind of Christ"), `map_situation` returns not just the literal
mention but its conceptual neighborhood (`Christ's mind`, `thoughts of Christ`,
`Christ perception`, `the one mind`, ...). The existing seeded batch then searches all of
them deterministically — there is no reactive decision left to be inconsistent about, and
interpretation stays in the one designated place. This also composes with the normalized
repeat-search guard already in the orchestrator (reworded variants the mapper emits are
searched once as a set; later model retries of the same terms are skipped).

## Sketch (to be detailed when picked up)

- `map_situation` / its `SituationMapper` prompt — instruct the mapper to include near
  neighbors of a named entity/attribute, not only the literal surface form. Bound the count
  (e.g. ≤ 6 mentions) so the seed batch's `global_limit` stays meaningful and the observation
  doesn't blow past the 3000-char truncation in the orchestrator.
- No orchestrator change required if the neighborhood arrives as extra concepts — the seed
  already batches `concepts`. Confirm the batch's `global_limit` still yields a balanced
  spread across the wider concept set (may need tuning).
- Evaluation: this is a recall lever, and `map_situation`'s docstring already frames a
  mention the corpus lacks as "a measurable recall signal rather than an error." Add a small
  gold set of entity questions ("mind of Christ", "mind of God", ...) and measure whether
  neighborhood expansion lifts directly-relevant claims retrieved without inflating noise.

## Open questions

- Does neighborhood expansion belong to *every* mapped mention, or only when the situation
  is a direct "describe/what is X" entity question? Over-expanding ordinary situations could
  pull the seed off-topic. Possibly gate on question shape.
- Ontology source: are the neighbors model-generated (flexible, unbounded) or drawn from a
  curated concept map (predictable, maintainable)? The current mapper is deliberately
  corpus-agnostic; a curated map would be a new dependency.
- Interaction with the repeat-search guard's normalization: ensure mapper-emitted variants
  that normalize to the same term aren't self-colliding before they're even searched.
