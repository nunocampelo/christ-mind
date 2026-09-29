"""Call one MCP tool over stdio and print its result, for terminal testing.

    python apps/mcp-server/scripts/call_tool.py find_claims '{"queries": ["mind"]}'
    python apps/mcp-server/scripts/call_tool.py list

Reuses the agent's McpClient so this drives the exact transport production runs --
no second stdio client to keep in step. Prints structured_content (the JSON object
the wire carries) plus each text block; --raw dumps the whole CallToolResult. Output
goes to stdout, so pipe it (`| less -R`, `| jq`) when a result is large; logs go to
stderr, so `2>/dev/null` keeps the pipe clean.
"""

import argparse
import asyncio
import json

from mind_of_christ_agent.infrastructure.mcp_client import connect


async def _run(tool: str, arguments: dict[str, object], raw: bool) -> int:
    async with connect() as client:
        if tool == "list":
            for descriptor in await client.list_tools():
                print(descriptor.name)
            return 0

        result = await client.call_tool(tool, arguments)
        if raw:
            print(json.dumps(result.model_dump(by_alias=True, mode="json"), indent=2))
            return 1 if result.is_error else 0

        print(f"is_error: {result.is_error}")
        if result.structured_content is not None:
            print("structured_content:")
            print(json.dumps(result.structured_content, indent=2))
        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                print(text)
        return 1 if result.is_error else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Call an MCP tool over stdio.")
    parser.add_argument("tool", help='tool name, or "list" to list tools')
    parser.add_argument(
        "arguments",
        nargs="?",
        default="{}",
        help='tool arguments as a JSON object, e.g. \'{"queries": ["mind"]}\'',
    )
    parser.add_argument(
        "--raw", action="store_true", help="dump the full CallToolResult as JSON"
    )
    args = parser.parse_args()

    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        parser.error("arguments must be a JSON object")

    raise SystemExit(asyncio.run(_run(args.tool, arguments, args.raw)))


if __name__ == "__main__":
    main()
