import json

import pytest

from application.mapping.map_situation import (
    ConversationTurn,
    MappingFailedError,
    SituationMapper,
    map_situation,
)
from application.mapping.prompt import (
    SYSTEM_PROMPT,
    PromptedSituationMapper,
    parse_response,
    user_prompt,
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


def test_user_prompt_without_history_has_no_context_block():
    prompt = user_prompt("how does that relate to forgiveness?")
    assert "Earlier in this conversation" not in prompt
    assert "how does that relate to forgiveness?" in prompt


def test_user_prompt_renders_role_labelled_history_as_context():
    history = (
        ConversationTurn("user", "What does the Course say about salvation?"),
        ConversationTurn("agent", "Salvation is the undoing of the belief in separation."),
    )
    prompt = user_prompt("how does that relate to forgiveness?", history)
    assert "Earlier in this conversation" in prompt
    assert "user: What does the Course say about salvation?" in prompt
    assert "agent: Salvation is the undoing of the belief in separation." in prompt
    assert prompt.index("Earlier in this conversation") < prompt.index(
        "how does that relate to forgiveness?"
    )


def test_history_reaches_user_prompt_not_system_prompt():
    reply = json.dumps({"concepts": ["forgiveness", "salvation"]})
    mapper, complete = _mapper(reply)
    history = (ConversationTurn("user", "Tell me about salvation."),)
    map_situation(mapper, "how does that relate to forgiveness?", history)
    system, user = complete.calls[0]
    assert system == SYSTEM_PROMPT
    assert "Tell me about salvation." in user
