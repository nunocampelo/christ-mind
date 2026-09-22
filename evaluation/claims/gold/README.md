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

The labelling rules live in exactly one place: `SYSTEM_PROMPT` in
`src/application/extraction/prompt.py`. The extractor is told the same rules the
gold labels follow, so they can't drift apart. Changing a rule means relabelling
these files and bumping `PROMPT_VERSION`.

Gold lines have the fields a prompted model returns, plus `source_id`. They're
ordered `subject`, `verb_phrase`, `object` first so each line reads as a sentence.
