"""The entity-resolution prompt, and the parser for the replies it asks for.

This is the single statement of the same/different rules: the pair gold under
`evaluation/entities/gold/` follows the same rules, so changing a rule here means
relabelling there and bumping `RESOLVER_PROMPT_VERSION`. A provider adapter only has
to supply a `Complete`, so two providers are compared on the same prompt -- the same
arrangement as claim extraction.

The model judges only the pairs it is given and echoes each pair's two surface forms
verbatim; it never proposes a new mention or a canonical name. `parse_response` keeps
each verdict's own left/right so `resolve` can reject a verdict whose forms don't
match a presented pair.
"""

import json
from collections.abc import Callable, Sequence

from application.resolution.resolve_entities import (
    CandidatePair,
    PairVerdict,
    ResolutionFailedError,
)

RESOLVER_PROMPT_VERSION = "1.0"

type Complete = Callable[[str, str], str]
"""Sends (system prompt, user prompt) to a model and returns its reply text."""


SYSTEM_PROMPT = """\
You resolve entity mentions from A Course in Miracles (Original Edition). Each mention
is a surface form -- a noun phrase -- that was extracted as the subject or object of a
claim. You are given pairs of mentions and decide, for each pair, whether the two
forms name the SAME thing in the Course's vocabulary.

Reply with only a JSON object of the form {"verdicts": [...]}, where each verdict is:

  "left": string. The pair's first mention, copied exactly as given.
  "right": string. The pair's second mention, copied exactly as given.
  "same": boolean. true if the two forms name the same thing, false otherwise.

Rules:

- Same thing, not same words. "the ego", "ego", "his ego", "the ego's wish" all name
  the ego. "self esteem in ego terms" is about the ego but names self-esteem, not the
  ego -- different.
- Capitalisation and the Course's emphasis capitals never matter: "Knowledge" and
  "knowledge", "YOU" and "you" are the same.
- Determiners and possessives never matter on their own: "the mind", "your mind",
  "his mind" are the same mind unless the possessor makes them a different thing.
- A modifier that narrows the thing makes it different: "fear" and "the fear of God"
  are different; "miracles" and "the greatest miracle" are different.
- Singular and plural of the same thing are the same: "miracle" and "miracles",
  "thought" and "thoughts".
- Judge only the pair in front of you. Do not merge across pairs, and never output a
  mention that is not one of the pair's two given forms. Copy both forms exactly.
"""


def user_prompt(pairs: Sequence[CandidatePair]) -> str:
    listed = "\n".join(
        f'{i}. "{pair.left}"  <->  "{pair.right}"' for i, pair in enumerate(pairs)
    )
    return f"Judge whether each pair names the same thing:\n\n{listed}"


def parse_response(text: str, pairs: Sequence[CandidatePair]) -> list[PairVerdict]:
    by_forms = {(p.left, p.right): p for p in pairs}
    try:
        response = json.loads(_strip_code_fence(text))
        if not isinstance(response, dict) or not isinstance(
            verdicts := response.get("verdicts"), list
        ):
            raise ValueError("response is not an object with a verdicts list")
        return [_parse_verdict(record, by_forms) for record in verdicts]
    except ValueError as e:
        raise ResolutionFailedError("model response is not valid verdicts JSON") from e


def _parse_verdict(
    record: object, by_forms: dict[tuple[str, str], CandidatePair]
) -> PairVerdict:
    if not isinstance(record, dict):
        raise ValueError("verdict must be a JSON object")
    left, right, same = record.get("left"), record.get("right"), record.get("same")
    if not isinstance(left, str) or not isinstance(right, str):
        raise ValueError("verdict left/right must be strings")
    if not isinstance(same, bool):
        raise ValueError("verdict same must be a boolean")
    # Match a presented pair in either order the model echoed it, so swapping left
    # and right isn't treated as inventing a mention. A verdict whose forms match no
    # presented pair still becomes a PairVerdict, so resolve() counts it as a
    # rejection rather than silently dropping it.
    pair = (
        by_forms.get((left, right))
        or by_forms.get((right, left))
        or CandidatePair(left, right)
    )
    return PairVerdict(pair=pair, same=same)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped.removeprefix("```").removesuffix("```")
        stripped = stripped.removeprefix("json")
    return stripped


class PromptedResolver:
    def __init__(self, complete: Complete):
        self._complete = complete

    def judge(self, pairs: Sequence[CandidatePair]) -> Sequence[PairVerdict]:
        if not pairs:
            return []
        return parse_response(self._complete(SYSTEM_PROMPT, user_prompt(pairs)), pairs)
