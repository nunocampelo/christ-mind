from infrastructure.model_gateway.families.anthropic import AnthropicFamily
from infrastructure.model_gateway.families.base import ChatFamily


def test_anthropic_conforms_to_family_protocol() -> None:
    family: ChatFamily = AnthropicFamily(model="anthropic--claude-4.8-opus")
    assert family is not None


def test_build_request_is_messages_shaped() -> None:
    family = AnthropicFamily(model="anthropic--claude-4.8-opus", max_tokens=512)
    body = family.build_request("be terse", "hi", stream=True)
    assert body == {
        "model": "anthropic--claude-4.8-opus",
        "max_tokens": 512,
        "system": "be terse",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }


def test_parse_response_concatenates_text_blocks_only() -> None:
    family = AnthropicFamily(model="m")
    response = {
        "content": [
            {"type": "text", "text": "Hello "},
            {"type": "tool_use", "id": "x"},
            {"type": "text", "text": "world"},
        ]
    }
    assert family.parse_response(response) == "Hello world"


def test_parse_stream_event_extracts_text_delta() -> None:
    family = AnthropicFamily(model="m")
    delta = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}
    assert family.parse_stream_event(delta) == "hi"


def test_parse_stream_event_ignores_non_text_events() -> None:
    family = AnthropicFamily(model="m")
    assert family.parse_stream_event({"type": "message_start"}) is None
    assert family.parse_stream_event({"type": "ping"}) is None
    assert (
        family.parse_stream_event(
            {"type": "content_block_delta", "delta": {"type": "input_json_delta"}}
        )
        is None
    )
