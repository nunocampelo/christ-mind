"""The claim-extraction prompt, and the parser for the replies it asks for.

This is the single statement of the labelling rules: the gold labels under
`evaluation/claims/gold/` follow the same rules, so changing a rule here means
relabelling there, and bumping `PROMPT_VERSION` so runs made under the old rules
aren't compared with runs under the new ones.

A provider adapter only has to supply a `Complete` function. Everything about
what to ask and how to read the answer stays here, so two providers are
compared on the same prompt.
"""

import json
from collections.abc import Callable, Sequence

from application.extraction.extract_claims import (
    CandidateClaim,
    ExtractionFailedError,
    parse_candidate,
)
from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.sources.models import Source

PROMPT_VERSION = "3.2"

type Complete = Callable[[str, str], str]
"""Sends (system prompt, user prompt) to a model and returns its reply text."""


def _values(enum: type[Predicate | Polarity | Mode | Attribution]) -> str:
    return ", ".join(f'"{member.value}"' for member in enum)


SYSTEM_PROMPT = f"""\
You extract claims from a passage of A Course in Miracles (Original Edition). A
claim is one thing the passage asserts, questions, or reports: a subject, a
verb phrase and usually an object, anchored to a quoted span of the passage.
Extract what the text says, not what it implies or what it means.

Reply with only a JSON object of the form {{"claims": [...]}}, where each claim is:

  "subject": string. The text's own noun phrase.
  "verb_phrase": string. Connects subject to object; see the rules below.
  "object": string or null. The text's own noun phrase, adjective or clause.
  "predicate": one of {_values(Predicate)}.
  "polarity": one of {_values(Polarity)}.
  "mode": one of {_values(Mode)}.
  "attribution": one of {_values(Attribution)}.
  "evidence": string. The shortest span of the passage supporting the claim,
    copied exactly: same case, punctuation and quote marks. It must occur exactly
    once in the passage. Several claims may share one span.

Rules:

- Extract every claim the passage makes. Leave out only a claim that repeats one
  already extracted from the same passage.
- Subject and object: drop articles, and resolve pronouns to what they refer to
  ("They" -> "miracles", "One" -> "intellectualizing"). Otherwise keep the
  text's words; don't normalise "miracle" vs "miracles".
- A relative clause states its own claim, with the clause's own subject as the
  subject: "a point which many very sincere Christians have misunderstood" is
  subject "many very sincere Christians", verb_phrase "have misunderstood",
  object "this point" -- not subject "point".
- Put the claim's own noun phrase, with its quantifiers and modifiers, in
  "object" -- "There is no order of difficulty among miracles" is object "order of
  difficulty"; "Miracles are all the same" is object "all the same", not "are all"
  / "the same". Use a null object only when the claim has none.
- verb_phrase: "subject verb_phrase object" must read as a sentence with the
  claim's meaning. Use the text's own words, including emphasis capitals ("are
  ALWAYS"), where they read correctly in that order. Where the text is built the
  other way round ("sickness comes from confusing the levels", "through prayer
  love is received"), use the shortest connector that reads correctly
  ("confusing the levels" "causes" "sickness"; "love" "is received through"
  "prayer"). Never repeat the object inside the verb phrase.
- "is": identity, definition, and predicate adjectives ("Miracles are natural",
  "Miracles are healing"). Also for a plain property or state of the subject
  worded as "feels X", "has been X", "seems X" ("this error has been
  particularly difficult to overcome" is "is", object "particularly difficult to
  overcome"). For a copula ("is", "are"), verb_phrase is just the copula and the
  whole noun phrase is the object: "Prayer is the medium of miracles" is subject
  "prayer", verb_phrase "is", object "medium of miracles", not verb_phrase "is
  the medium of".
- "causes": always cause -> effect. "X comes from Y", "X arises from Y", "X arose
  out of Y", "X because Y" and "X is the result of Y" all become Y causes X --
  the subject is the cause. "interpretation arose out of misprojections" is
  subject "misprojections", object "interpretation". Effect verbs ("heal",
  "bring") are "causes" with the effect as object, but a plain predicate
  adjective is "is", not "causes" ("Miracles are healing" is "is").
- "requires": preconditions and means ("necessary first", "depend on", "by
  extending it").
- "expresses": the subject is an expression, manifestation, or showing-forth of
  the object. "X is an expression of Y", "X is expressions of Y", "X are natural
  expressions of Y" are all "X expresses Y": "Miracles are expressions of love"
  is subject "miracles", predicate "expresses", object "love", verb_phrase "are
  expressions of" -- not "is" with object "expressions of love".
- "contrasts_with": the text sets two things against each other as a distinction.
  "the distinction between A and B", "A as opposed to B", "A rather than B" is "A
  contrasts_with B": "the basic distinction between intellectualizing and
  thinking" is subject "intellectualizing", predicate "contrasts_with", object
  "thinking" -- not "this is the distinction". (This is a distinction between two
  things; it is not the "A, not B, is C" negation pattern below.)
- "makes" and "creates" are distinct, and both are limited to the Course's
  sense: "makes" is making by the ego or in perception (making an illusion, a
  false world), "creates" is creating by spirit. An ordinary English "make" is
  "other", never "makes": "make a mistake", "make this mistake", "make an error"
  are all "other" -- "one who is free of the scarcity-error could POSSIBLY make
  this mistake" is subject "one who is free of the scarcity-error", predicate
  "other", object "this mistake", polarity "negated".
- "other": anything the other predicates don't cover; verb_phrase then carries
  the meaning.
- Negation: set polarity "negated"; never rephrase it into the subject or object.
  Negative words in the subject or object ("nothing", "no-one", "no") move into
  polarity: "NOTHING of this kind remains in your mind" is subject "this kind of
  thinking", verb_phrase "remains in", object "your mind", polarity "negated".
  "The Spirit, not the body, is the altar" is two claims, one affirmed and one
  negated. A "NOT" or "no" on the verb negates the claim, whatever the predicate:
  "I was NOT punished because YOU were bad" is subject "your being bad",
  verb_phrase "did NOT cause", object "my punishment", predicate "causes",
  polarity "negated" (the cause is negated, and the subject is still the cause).
  A double negative negates once, not twice: "No-one who is free of the
  scarcity-error could POSSIBLY make this mistake" is subject "one who is free of
  the scarcity-error", verb_phrase "could POSSIBLY make", object "this mistake",
  polarity "negated" -- the "No-one" is the only negation. A "NOT" inside an
  if/when clause doesn't negate the claim: "When they do NOT occur something has
  gone wrong" is subject "absence of miracles", verb_phrase "means", object
  "something has gone wrong", mode "conditional", polarity "affirmed".
- Appearance vs. reality: "X seems to A, but really B" is two claims, and
  verb_phrase keeps "seem" and "really".
- mode: "normative" for should/must, "conditional" for if/when/without clauses,
  "question" for questions, including rhetorical ones. "assertion" otherwise.
  "predicate" and "mode" are different fields with different value lists: a mode
  value ("normative", "conditional", "question", "assertion") is NEVER a
  predicate. A should/must claim still takes a predicate from the predicate list
  (usually "is" or "other") with mode "normative" -- never predicate "normative".
- Questions: extract the proposition as literally worded, with mode "question".
  Don't flip polarity to the implied answer: "Is it likely that God would be
  capable of X?" is "God" "would be capable of" "X", polarity "affirmed".
- attribution: "course" when the text itself asserts or asks it. "others" when it
  reports or describes a view it rejects ("the fallacious belief that...", "Man
  believes that...", "it DOES appear as if...", a quoted speaker's words). "ego"
  when the view is attributed to the ego. "hypothetical" for a case posed but not
  asserted. That someone holds a view is itself a "course" claim ("Many ministers
  preach this every day"), separate from the view's content.
- Embedded propositions: a "that X" clause after awareness, belief, recognition,
  or idea is its own claim (or claims), in addition to the claim about the frame.
  "reawaken the awareness that the Spirit, not the body, is the altar of truth"
  gives "miracles" "reawaken" "awareness" and, from the "that" clause, "Spirit"
  "is" "altar of truth" (affirmed) and "body" "is not" "altar of truth"
  (negated). The clause's attribution comes from its frame: a plain awareness or
  recognition is "course", but a "fallacious belief that X" or "the idea that X"
  it rejects makes X "others".
"""


def user_prompt(source: Source) -> str:
    return f"Passage {source.id}:\n\n{source.text}"


def parse_response(text: str) -> list[CandidateClaim]:
    try:
        response = json.loads(_strip_code_fence(text))
        if not isinstance(response, dict) or not isinstance(
            claims := response.get("claims"), list
        ):
            raise ValueError("response is not an object with a claims list")
        return [parse_candidate(record) for record in claims]
    except ValueError as e:
        raise ExtractionFailedError("model response is not valid claims JSON") from e


def _strip_code_fence(text: str) -> str:
    # Models often wrap JSON in a ``` fence despite being told not to. That's a
    # formatting habit, not an extraction error, so it shouldn't fail the source.
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped.removeprefix("```").removesuffix("```")
        stripped = stripped.removeprefix("json")
    return stripped


class PromptedClaimExtractor:
    def __init__(self, complete: Complete):
        self._complete = complete

    def extract(self, source: Source) -> Sequence[CandidateClaim]:
        return parse_response(self._complete(SYSTEM_PROMPT, user_prompt(source)))
