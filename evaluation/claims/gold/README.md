# Gold claims

Hand-labelled claims, one JSON object per line, loaded by `evaluation/claims/gold.py`.

- `t1_1.jsonl`: development set, 15 miracle principles. Tune prompts against this.
- `t1_1_holdout.jsonl`: 5 principles never looked at while tuning. Score against it
  only to report a result.

Labels key on `source_id`, not the principle number. The Original Edition repeats
some numbers (two 24s and two 27s in T1.1), and commentary paragraphs sit between
principles, so principle N is not `t1-1-N` past principle 22.

## Conventions

These are also the rules an extractor has to follow, so its prompt should state them.

- **Every claim the passage makes gets a label.** Recall means nothing otherwise.
  Leave out only what repeats a claim already labelled in the same passage.
- **Subject/object** are the text's own noun phrase, with articles dropped and
  pronouns resolved ("They" → "miracles", "One" → "intellectualizing"). No
  entity resolution: "miracle" and "miracles" stay as written.
- **`evidence`** is the shortest exact span supporting the claim, and it must occur
  exactly once in the passage. Several claims may share one span.
- **`verb_phrase`** is the text's wording, including emphasis caps ("are ALWAYS").
- **Direction**: `causes` always runs cause → effect. "X comes from Y" and
  "X arises from Y" are stored as Y `causes` X. Effect verbs ("heal", "are healing",
  "bring") are `causes` with the effect as object.
- **`requires`** covers preconditions and means: "necessary first", "depend on",
  "by extending it".
- **`is`** covers identity, definition and predicate adjectives ("are natural").
- **`other`** is for anything the fixed predicates don't cover. `verb_phrase` then
  carries the meaning.
- **Negation**: set `polarity: negated`. Never paraphrase it into the object.
  "The Spirit, not the body, is the altar" gives two claims, one affirmed and one
  negated. A "NOT" inside an if/when clause doesn't negate the claim itself. That
  claim is `conditional` + `affirmed`.
- **Appearance vs. reality**: "X seems to A, but really B" gives two claims, one
  for A and one for B. `verb_phrase` keeps "seem" and "really", since that
  wording is the only thing telling the two apart.
- **`mode`**: `normative` for should/must, `conditional` for if/when/without clauses,
  `question` for questions, including rhetorical ones.
- **`attribution`**: `course` when the text asserts it. `others` when it reports a
  belief it rejects ("the fallacious belief that…", "Man believes that…"), `ego` when
  the belief is attributed to the ego, `hypothetical` for posed but unasserted cases.
