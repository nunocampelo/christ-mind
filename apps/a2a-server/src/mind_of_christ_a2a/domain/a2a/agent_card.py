"""The v1 agent card, rendered once and validated against the a2a-sdk proto.

Native v1 only (`enable_v0_3_compat=False` at the dispatcher, see api/controllers): the
transport is advertised in `supportedInterfaces[]` with a `1.0.0` protocol version, not the
0.3 top-level `url`/`preferredTransport`. The shared content is built from typed SDK models
so a field rename or typo fails at construction, not on the wire.

No security scheme: this is a local prototype over stdio-backed MCP with no auth. When a
real transport carries a token (roadmap), add the scheme here and validate it at boot.
"""

from typing import cast

from a2a.compat.v0_3 import types as v03
from a2a.types import AgentCard as CoreCard
from a2a.utils.constants import TransportProtocol
from google.protobuf import json_format

_AGENT_PATH = "/a2a"

_NAME = "Mind of Christ Agent"
_DESCRIPTION = (
    "Maps a person's free-text situation to A Course in Miracles concepts, then reasons "
    "over deterministic, cited claims to answer it — keeping what the Course says "
    "distinct from what follows from it."
)
_VERSION = "0.1.0"
_INPUT_MODES = ["text/plain"]
_OUTPUT_MODES = ["text/plain"]

_PROVIDER = v03.AgentProvider(organization="Mind of Christ", url="https://example.invalid")
_CAPABILITIES = v03.AgentCapabilities(streaming=True, push_notifications=False)
_SKILLS = [
    v03.AgentSkill(
        id="situation-guidance",
        name="Situation Guidance",
        description=(
            "Answers a natural-language personal situation with grounded, cited "
            "guidance from A Course in Miracles."
        ),
        tags=["acim", "guidance", "chat"],
        examples=[
            "I keep getting angry when criticized",
            "I can't forgive someone who hurt me",
        ],
        input_modes=list(_INPUT_MODES),
        output_modes=list(_OUTPUT_MODES),
    )
]


def render_agent_card_v1(agent_url: str) -> dict[str, object]:
    body = {
        "name": _NAME,
        "description": _DESCRIPTION,
        "version": _VERSION,
        "provider": _PROVIDER.model_dump(mode="json", by_alias=True, exclude_none=True),
        "capabilities": _CAPABILITIES.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "defaultInputModes": list(_INPUT_MODES),
        "defaultOutputModes": list(_OUTPUT_MODES),
        "skills": [
            s.model_dump(mode="json", by_alias=True, exclude_none=True) for s in _SKILLS
        ],
        "supportedInterfaces": [
            {
                "url": f"{agent_url}{_AGENT_PATH}",
                "protocolBinding": TransportProtocol.JSONRPC,
                "protocolVersion": "1.0.0",
            }
        ],
    }
    core = json_format.ParseDict(body, CoreCard())
    return cast(
        "dict[str, object]",
        json_format.MessageToDict(core, preserving_proto_field_name=False),
    )
