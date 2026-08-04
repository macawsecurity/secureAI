# Pydantic AI Examples

`SecureAgent` is a drop-in replacement for `pydantic_ai.Agent`. Model calls
become `tool:<app>/generate` and tool calls become `tool:<app>/<tool_name>`, so
both are governed by the MAPL policies you already write.

```python
# BEFORE
from pydantic_ai import Agent
agent = Agent(OpenAIChatModel("gpt-4o-mini"), tools=[query_catalog])

# AFTER
from macaw_adapters.pydantic_ai import SecureAgent
agent = SecureAgent(OpenAIChatModel("gpt-4o-mini"), app_name="pydantic-agent",
                    tools=[query_catalog])
```

## Setup

```bash
pip install "macaw-adapters[pydantic-ai]"
export OPENAI_API_KEY=sk-...
```

You also need the MACAW LocalAgent running, and the examples' resources allowed
in your workspace. MAPL is restrict-only: an `intent_policy` can narrow what an
application may do but never widen it, so the workspace has to grant the
superset first.

Import `policies/app_pydantic-agent.json` via Console > Policies, or add:

```
tool:pydantic-agent/*
```

Each example then narrows from there, which is what it is demonstrating.

`1d` additionally needs an identity provider with the demo users - see
`demos/tutorial-1/setup/`.

## Examples

| Example | Demonstrates |
|---------|--------------|
| `pydanticai_1a_dropin_simple.py` | The import swap. One tool allowed, one denied, model and token ceiling pinned. |
| `pydanticai_1b_model_routing.py` | `FallbackModel` with policy-driven degradation - a denial on the preferred model falls through to a permitted one. |
| `pydanticai_1c_native_tools.py` | Provider-side tools (web search) refused by `denied_parameters` before the provider is called. |
| `pydanticai_1d_multiuser_bind.py` | `bind_to_user()` - one agent, per-user policy for alice and bob. |
| `pydanticai_1e_mcp_compose.py` | Local tools alongside an MCP server, each governed at its own boundary. |

## What is governed

Every way Pydantic AI accepts tools:

| | |
|---|---|
| `tools=[fn]` | registered with MACAW, dispatched by it |
| `@agent.tool` / `@agent.tool_plain` | registered with MACAW |
| `toolsets=[FunctionToolset(...)]` | functions registered with MACAW |
| `toolsets=[MCPToolset(...)]` | authorized here under the caller's identity; executed by the server, which `SecureMCP` or `SecureMCPProxy` governs |

`run()`, `run_sync()`, `run_stream()` and `override()` wrap any per-call model or
toolsets, so an override cannot route around the adapter. A router such as
`FallbackModel` has its candidates secured rather than the router itself, so
policy always sees the model that actually calls a provider.

## Policy

Nothing here needs new MAPL. The examples use constraint shapes that already
ship:

```json
{
  "resources": ["tool:pydantic-agent/generate", "tool:pydantic-agent/query_catalog"],
  "denied_resources": ["tool:pydantic-agent/export_dataset"],
  "constraints": {
    "parameters": {
      "tool:pydantic-agent/generate": {
        "model": ["gpt-4o-mini"],
        "max_tokens": {"max": 500}
      }
    },
    "denied_parameters": {
      "tool:pydantic-agent/generate": {"native_tools": ["*web_search*"]}
    }
  }
}
```
