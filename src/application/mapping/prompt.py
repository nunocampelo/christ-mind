"""The situation-mapping prompt, and the parser for the replies it asks for.

This is the single statement of the mapping rules: the gold under
`evaluation/mapping/gold/` follows the same rules, so changing a rule here means
relabelling there and bumping `MAP_VERSION`. A provider adapter only has to supply a
`Complete`, so two providers are compared on the same prompt -- the same arrangement
as claim extraction and entity resolution.

The model returns concept mentions only: short noun phrases, never sentences, causes,
or advice. `parse_response` normalises them (trim, drop empties, dedupe keeping first
appearance) and rejects anything that isn't `{"concepts": [str, ...]}`.
"""

import json
from collections.abc import Callable

from application.mapping.map_situation import MappingFailedError

MAP_VERSION = "1.0"

type Complete = Callable[[str, str], str]
"""Sends (system prompt, user prompt) to a model and returns its reply text."""


SYSTEM_PROMPT = """\
You map a person's real-life situation to concepts from A Course in Miracles (Original
Edition). A concept is a short surface form -- a noun phrase in the Course's register,
such as "anger", "guilt", "fear", "criticism", "judgment", "forgiveness", "the ego".

Given a free-text situation, list the concepts that open the space of Course teaching
relevant to it. That is the whole job. These are RETRIEVAL concepts: they include both
what the person is experiencing AND the concepts the Course would bring to bear on it,
even ones the person never named. "I lied and feel awful" -> guilt, shame, fear, and
also forgiveness -- because forgiveness is the relevant teaching, not because the word
appears in the sentence.

Reply with only a JSON object of the form {"concepts": [...]}, where each entry is a
string naming one concept.

Rules:

- Name concepts, nothing else. Never return sentences, explanations, causes ("anger is
  caused by fear"), advice ("you should forgive"), or anything phrased as what the
  Course says. Just the concept words.
- Each entry is a short noun phrase, lower-case unless the Course capitalises it as a
  proper term ("Atonement", "Holy Spirit"). Prefer the Course's own vocabulary.
- Surface the feelings named in the situation, the concepts it plainly implies, and the
  Course concepts that would be brought to bear on it: "I keep getting angry when
  criticized" -> anger, criticism, judgment, attack. Reach past the surface wording to
  the underlying dynamic ("everyone at the party clicked and I felt I don't belong" ->
  separation, specialness, loneliness), but don't invent a concept the situation gives
  no basis for.
- You may name a concept even if you are unsure the Course discusses it under that
  exact word. Do not invent structure to justify a concept; if it fits, list it.
- Return between one and roughly a dozen concepts. An empty situation gets an empty
  list.
"""


def user_prompt(free_text: str) -> str:
    return f"List the concepts this situation touches:\n\n{free_text}"


def parse_response(text: str) -> list[str]:
    try:
        response = json.loads(_strip_code_fence(text))
        if not isinstance(response, dict) or not isinstance(
            concepts := response.get("concepts"), list
        ):
            raise ValueError("response is not an object with a concepts list")
        if not all(isinstance(concept, str) for concept in concepts):
            raise ValueError("every concept must be a string")
        return _normalise(concepts)
    except ValueError as e:
        raise MappingFailedError("model response is not valid concepts JSON") from e


def _normalise(concepts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for concept in concepts:
        stripped = concept.strip()
        key = stripped.casefold()
        if stripped and key not in seen:
            seen.add(key)
            out.append(stripped)
    return out


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped.removeprefix("```").removesuffix("```")
        stripped = stripped.removeprefix("json")
    return stripped


class PromptedSituationMapper:
    def __init__(self, complete: Complete):
        self._complete = complete

    def map(self, free_text: str) -> list[str]:
        if not free_text.strip():
            return []
        return parse_response(self._complete(SYSTEM_PROMPT, user_prompt(free_text)))
