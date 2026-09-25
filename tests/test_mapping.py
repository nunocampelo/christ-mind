import json

import pytest

from application.mapping.map_situation import (
    MappingFailedError,
    SituationMapper,
    map_situation,
)
from application.mapping.prompt import (
    PromptedSituationMapper,
    parse_response,
)


class StubComplete:
    """A `Complete` that returns a canned reply and records how it was called, so a
    test can assert the model was (or wasn't) invoked without any network."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


def _mapper(reply: str) -> tuple[PromptedSituationMapper, StubComplete]:
    complete = StubComplete(reply)
    return PromptedSituationMapper(complete), complete


def test_maps_situation_to_concepts_exactly():
    reply = json.dumps({"concepts": ["anger", "criticism", "judgment"]})
    mapper, complete = _mapper(reply)
    assert map_situation(mapper, "I keep getting angry when criticized") == [
        "anger",
        "criticism",
        "judgment",
    ]
    assert len(complete.calls) == 1


def test_blank_situation_returns_empty_without_calling_model():
    mapper, complete = _mapper(json.dumps({"concepts": ["anger"]}))
    assert map_situation(mapper, "   ") == []
    assert complete.calls == []


def test_output_is_trimmed_and_deduped_first_seen():
    reply = json.dumps({"concepts": [" anger ", "Anger", "guilt", "", "guilt"]})
    mapper, _ = _mapper(reply)
    assert map_situation(mapper, "something") == ["anger", "guilt"]


def test_code_fenced_reply_is_parsed():
    reply = "```json\n" + json.dumps({"concepts": ["fear"]}) + "\n```"
    assert parse_response(reply) == ["fear"]


@pytest.mark.parametrize(
    "reply",
    [
        "Anger is caused by fear.",
        json.dumps(["anger", "guilt"]),
        json.dumps({"ideas": ["anger"]}),
        json.dumps({"concepts": "anger"}),
        json.dumps({"concepts": ["anger", 3]}),
        "not json at all",
    ],
)
def test_invalid_reply_raises_mapping_failed(reply: str):
    mapper, _ = _mapper(reply)
    with pytest.raises(MappingFailedError):
        map_situation(mapper, "something")


def test_prompted_mapper_is_usable_as_the_protocol():
    mapper, _ = _mapper(json.dumps({"concepts": []}))
    used: SituationMapper = mapper
    assert used.map("something") == []
