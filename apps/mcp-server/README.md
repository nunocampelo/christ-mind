# mind-of-christ-mcp

MCP server exposing the Mind of Christ knowledge system as tools for an
agent to call. First slice: one tool, `find_sources`, backed by a small
in-memory stub of public-domain source passages (not a real database yet).

## Setup

From the repo root:

```sh
python3.14 -m venv .venv   # already created; see below if starting fresh
.venv/bin/pip install -e "apps/mcp-server[dev]"
```

## Run tests

```sh
.venv/bin/python -m pytest apps/mcp-server/tests -q
```

## Run the server (stdio)

```sh
.venv/bin/python -m mind_of_christ_mcp.server
```

Point any MCP client (Claude Desktop, the MCP inspector, a custom client)
at this command over stdio to connect.

## Tools

- `find_sources(query, limit=5)` -- keyword/concept search over the stub
  source set, returns matching passages with reference and concept tags.

## Status

This is a prototype slice, not the full architecture. Not yet built:
real database-backed repositories, additional tools (`explore_situation`,
etc.), the orchestrator/agent layer, A2A interface, and the evaluation
harness.
