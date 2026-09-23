# Gold claims

Hand-labelled claims, one JSON object per line, loaded by `evaluation/claims/gold.py`.

- `t1_1.jsonl` + `t3_2.jsonl` + `t4_ego.jsonl`: development set. `t1_1` covers 15
  miracle principles; `t3_2` adds T3.2 ¶1, ¶2 and ¶4 because the principles almost
  never report a belief the Course rejects, so without them the set would never test
  `attribution` or `question`. `t4_ego` adds 5 chapter-4 ego passages (t4-2-8, t4-2-10,
  t4-3-8, t4-4-12, t4-6-2) so the set finally exercises `ego` attribution, which the
  first two files never did. Its claims were seeded from the v3.1 corpus run's own
  output and then reviewed, so the `ego` numbers it produces are less independent than
  a from-scratch gold would be. Tune prompts against this whole set.
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
