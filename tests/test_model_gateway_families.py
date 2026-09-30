from infrastructure.model_gateway.families.anthropic import AnthropicFamily
from infrastructure.model_gateway.families.base import ChatFamily
from infrastructure.model_gateway.families.orchestration import OrchestrationFamily


# --- Anthropic family ---


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


# --- Orchestration family ---


def test_orchestration_conforms_to_family_protocol() -> None:
    family: ChatFamily = OrchestrationFamily(model="gpt-4o")
    assert family is not None


def test_orchestration_build_request_has_envelope() -> None:
    family = OrchestrationFamily(model="gpt-4o", max_tokens=512)
    body = family.build_request("be terse", "hi", stream=True)
    assert body == {
        "orchestration_config": {
            "module_configurations": {
                "templating_module_config": {
                    "template": [
                        {"role": "system", "content": "be terse"},
                        {"role": "user", "content": "hi"},
                    ],
                },
                "llm_module_config": {
                    "model_name": "gpt-4o",
                    "model_version": "latest",
                    "model_params": {"max_tokens": 512},
                },
            },
            "stream": True,
        },
        "input_params": {},
        "messages_history": [],
    }


def test_orchestration_build_request_omits_system_when_empty() -> None:
    family = OrchestrationFamily(model="gpt-4o")
    body = family.build_request("", "hi", stream=False)
    template = body["orchestration_config"]["module_configurations"][
        "templating_module_config"
    ]["template"]
    assert template == [{"role": "user", "content": "hi"}]
    assert "stream" not in body["orchestration_config"]


def test_orchestration_parse_response_extracts_content() -> None:
    family = OrchestrationFamily(model="gpt-4o")
    response = {
        "orchestration_result": {
            "choices": [{"message": {"content": "Hello!"}}],
        }
    }
    assert family.parse_response(response) == "Hello!"


def test_orchestration_parse_response_handles_empty() -> None:
    family = OrchestrationFamily(model="gpt-4o")
    assert family.parse_response({}) == ""
    assert family.parse_response({"orchestration_result": {}}) == ""
    assert family.parse_response({"orchestration_result": {"choices": []}}) == ""


def test_orchestration_parse_stream_event_extracts_delta() -> None:
    family = OrchestrationFamily(model="gpt-4o")
    event = {
        "orchestration_result": {
            "choices": [{"delta": {"content": "Hi"}}],
        }
    }
    assert family.parse_stream_event(event) == "Hi"


def test_orchestration_parse_stream_event_ignores_non_content() -> None:
    family = OrchestrationFamily(model="gpt-4o")
    # Role-only delta
    assert family.parse_stream_event(
        {"orchestration_result": {"choices": [{"delta": {"role": "assistant"}}]}}
    ) is None
    # No delta
    assert family.parse_stream_event(
        {"orchestration_result": {"choices": [{"finish_reason": "stop"}]}}
    ) is None
    # No orchestration_result
    assert family.parse_stream_event({"request_id": "abc"}) is None
