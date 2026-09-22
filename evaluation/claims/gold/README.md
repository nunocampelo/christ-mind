# Gold claims

Hand-labelled claims, one JSON object per line, loaded by `evaluation/claims/gold.py`.

- `t1_1.jsonl` + `t3_2.jsonl`: development set. It covers 15 miracle principles plus
  T3.2 ¶1, ¶2 and ¶4. The T3.2 paragraphs are there because the principles almost
  never report a belief the Course rejects, so without them the development set
  would never test `attribution` or `question`. Tune prompts against this set.
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
- **`verb_phrase`** connects subject to object, so `subject verb_phrase object`
  reads as a sentence with the claim's meaning. Use the text's own words, including
  emphasis caps ("are ALWAYS"), where they read correctly in that order. Where the
  text is built the other way round ("sickness comes from confusing the levels",
  "through prayer love is received"), use the shortest connector that reads
  correctly ("causes", "is received through"). Never repeat the object inside the
  verb phrase.
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
  negated. Negative words in the subject or object ("nothing", "no-one", "no")
  also move into polarity, so negation is never counted twice. "NOTHING of this
  kind remains" is `this kind of thinking` `remains in` + `negated`, not
  `nothing of this kind` + `negated`. A "NOT" inside an if/when clause doesn't negate the claim itself. That
  claim is `conditional` + `affirmed`.
- **Appearance vs. reality**: "X seems to A, but really B" gives two claims, one
  for A and one for B. `verb_phrase` keeps "seem" and "really", since that
  wording is the only thing telling the two apart.
- **`mode`**: `normative` for should/must, `conditional` for if/when/without clauses,
  `question` for questions, including rhetorical ones.
- **Questions** are labelled with the proposition as literally worded, with
  `mode: question`, and `polarity` is *not* flipped to the implied answer. "Is it
  likely that God would be capable of…?" is `God is capable of…`, `affirmed`,
  `question`. The implied "no" is interpretation, and it belongs downstream with
  the other non-explicit claims. The asker is `course`.
- **Reported speech and appearances** of a view the Course rejects go to `others`
  ("it DOES appear as if God permitted…", a parent's "This hurts me more than it
  hurts you"). The fact that someone holds or preaches the view is a separate
  `course` claim ("Many ministers preach this every day").
- **`attribution`**: `course` when the text asserts it. `others` when it reports a
  belief it rejects ("the fallacious belief that…", "Man believes that…"), `ego` when
  the belief is attributed to the ego, `hypothetical` for posed but unasserted cases.
