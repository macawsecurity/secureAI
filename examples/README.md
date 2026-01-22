# Examples: Getting Started with MACAW Adapters

These examples demonstrate usage paths for MACAW-protected LLM and agent adapters.

## When to Use Each Path

| Scenario | Path | OpenAI Example | Anthropic Example | LangChain Example |
|----------|------|----------------|-------------------|-------------------|
| Simple app, no user distinction | Direct/Drop-in | `openai_1a_dropin_simple.py` | `anthropic_1a_dropin_simple.py` | `langchain_1a_dropin_simple.py` |
| Multi-user, per-user policies | bind_to_user/Per-user | `openai_1b_multiuser_bind.py` | `anthropic_1b_multiuser_bind.py` | `langchain_1b_multiuser.py` |
| A2A/Orchestration | invoke_tool/Supervisor | `openai_1c_a2a_invoke.py` | `anthropic_1c_a2a_invoke.py` | `langchain_1c_orchestration.py` |
| CLI tool, single operator | Direct/Drop-in | `openai_1a_dropin_simple.py` | `anthropic_1a_dropin_simple.py` | `langchain_1a_dropin_simple.py` |
| SaaS with user accounts | bind_to_user/Per-user | `openai_1b_multiuser_bind.py` | `anthropic_1b_multiuser_bind.py` | `langchain_1b_multiuser.py` |

## Quick Start

First, install the package:
```bash
cd /path/to/secureAI
pip install -e .
```

### 1a: Drop-in Replacement (Simplest)

No setup required - just set your API key:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
python openai/openai_1a_dropin_simple.py

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python anthropic/anthropic_1a_dropin_simple.py
```

### 1b: Multi-user with bind_to_user

Requires identity provider setup:

```bash
# 1. Set up identity provider (Keycloak or Auth0)
cd setup/
./keycloak_complete_setup.sh  # or ./auth0_complete_setup.sh

# 2. Load user policies
# (policies are in policies/ directory)

# 3. Run example
export OPENAI_API_KEY=sk-...
python openai/openai_1b_multiuser_bind.py
```

### 1c: A2A with invoke_tool

Same setup as 1b:

```bash
export OPENAI_API_KEY=sk-...
python openai/openai_1c_a2a_invoke.py
```

## LangChain Examples

The LangChain adapter provides drop-in replacements for LangChain agent components with MACAW security.

### LangChain 1a: Drop-in Replacement

```bash
export OPENAI_API_KEY=sk-...
python langchain/langchain_1a_dropin_simple.py
```

```python
# BEFORE
from langchain.agents import create_react_agent, AgentExecutor

# AFTER - just change imports and add security_policy
from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor

agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=prompt,
    security_policy={
        "resources": ["tool:calculator", "tool:weather"],
        "denied_resources": ["tool:admin"],
        "constraints": {
            "denied_parameters": {"tool:*": {"query": ["*password*", "*secret*"]}}
        }
    }
)
```

### LangChain 1b: Multi-user Agents

```bash
export OPENAI_API_KEY=sk-...
python langchain/langchain_1b_multiuser.py
```

Creates separate executors per user, each with their own policy:
- alice (Analyst): calculator, file_reader (reports only)
- bob (Manager): calculator, weather, file_reader
- carol (Admin): all tools, all files

### LangChain 1c: Agent Orchestration

```bash
export OPENAI_API_KEY=sk-...
python langchain/langchain_1c_orchestration.py
```

A supervisor pattern where a coordinator routes tasks to specialized sub-agents:
- Research Agent: search, public files
- Finance Agent: calculator, financial reports
- Admin Agent: admin tools, email

Demonstrates policy isolation - each agent can only use its allowed tools.

## Directory Structure

```
examples/
├── openai/
│   ├── openai_1a_dropin_simple.py      # Path 1: Direct (OpenAI)
│   ├── openai_1b_multiuser_bind.py     # Path 2: bind_to_user (OpenAI)
│   └── openai_1c_a2a_invoke.py         # Path 3: invoke_tool (OpenAI)
├── anthropic/
│   ├── anthropic_1a_dropin_simple.py   # Path 1: Direct (Anthropic)
│   ├── anthropic_1b_multiuser_bind.py  # Path 2: bind_to_user (Anthropic)
│   └── anthropic_1c_a2a_invoke.py      # Path 3: invoke_tool (Anthropic)
├── langchain/
│   ├── langchain_1a_dropin_simple.py   # Path 1: Drop-in (LangChain)
│   ├── langchain_1b_multiuser.py       # Path 2: Per-user executors (LangChain)
│   ├── langchain_1c_orchestration.py   # Path 3: Agent orchestration (LangChain)
│   ├── langchain_1d_llm_openai.py      # LLM wrapper (OpenAI)
│   ├── langchain_1e_llm_anthropic.py   # LLM wrapper (Anthropic)
│   └── langchain_1f_memory.py          # Memory integration
├── mcp/
│   ├── securemcp_server.py             # Basic MCP server
│   ├── securemcp_calculator.py         # Calculator MCP server
│   ├── 1a_simple_invocation.py         # Basic tool invocation
│   ├── 1b_discovery_and_resources.py   # Resource discovery
│   ├── 1c_logging_client.py            # Logging support
│   ├── 1d_progress_client.py           # Progress tracking
│   ├── 1e_sampling_*.py                # Sampling (client + server)
│   ├── 1f_elicitation_*.py             # Elicitation (client + server)
│   └── 1g_roots_*.py                   # Roots (client + server)
└── README.md                           # This file
```

## Path Details

### Path 1: Direct on Service

```python
# BEFORE
from openai import OpenAI
client = OpenAI()

# AFTER
from macaw_adapters.openai import SecureOpenAI
client = SecureOpenAI(app_name="my-app")

# Same API - no other changes
response = client.chat.completions.create(...)
```

**Identity**: Service's own MACAW agent identity.
**Policies**: App-level policies apply to all calls.
**Use when**: Simple apps, CLI tools, no per-user permissions needed.

### Path 2: bind_to_user

```python
from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider

# 1. Create service (once)
service = SecureOpenAI(app_name="my-service")

# 2. User login -> JWT -> MACAWClient
jwt, _ = RemoteIdentityProvider().login("alice", "password")
user = MACAWClient(user_name="alice", iam_token=jwt, agent_type="user")
user.register()

# 3. Bind user to service
user_client = service.bind_to_user(user)

# 4. Same API, user's identity flows through
response = user_client.chat.completions.create(...)

# 5. Cleanup
user_client.unbind()
```

**Identity**: User's JWT identity flows through for policy evaluation.
**Policies**: User-specific policies (alice vs bob can have different permissions).
**Use when**: SaaS apps, multi-tenant systems, per-user permissions.

### Path 3: invoke_tool

```python
from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient

# 1. Create service
service = SecureOpenAI(app_name="my-service")

# 2. Create user agent (jwt obtained via RemoteIdentityProvider().login())
user = MACAWClient(user_name="alice", iam_token=jwt, agent_type="user")
user.register()

# 3. Explicit invoke_tool
result = user.invoke_tool(
    tool_name="tool:my-service/generate",  # MAPL tool name
    parameters={"model": "gpt-4", "messages": [...]},
    target_agent=service.server_id
)

# Result is raw dict
content = result["choices"][0]["message"]["content"]
```

**Identity**: User's MACAW agent identity.
**Control**: Full control over routing and tool names.
**Use when**: Agent systems, cross-service calls, custom routing.

## LangChain Adapter Details

The LangChain adapter wraps LangChain agents with MACAW security controls without requiring code rewrites.

### SOSP Policy Format

Policies use MACAW's SOSP (Simple Open Security Policy) format directly:

```python
security_policy = {
    "resources": ["tool:calculator", "tool:weather"],  # Allowed tools
    "denied_resources": ["tool:admin"],                 # Blocked tools
    "constraints": {
        "parameters": {
            "tool:file_reader": {"input": ["*report*", "*public*"]}  # Allowed file patterns
        },
        "denied_parameters": {
            "tool:*": {"input": ["*password*", "*secret*"]}  # Block sensitive queries
        }
    }
}
```

### What Gets Enforced

- **Tool Access**: Tools not in `resources` (or in `denied_resources`) raise policy violations
- **Query Filtering**: Parameters matching `denied_parameters` patterns are rejected
- **File Restrictions**: File path arguments are validated against `parameters` patterns

### Orchestration Pattern

For multi-agent systems, create separate executors with different policies:

```python
from macaw_adapters.langchain.agents import AgentExecutor

# Research agent - limited tools
research_executor = AgentExecutor(
    agent=agent,
    tools=ALL_TOOLS,
    security_policy={"resources": ["tool:search", "tool:file_reader"]}
)

# Admin agent - privileged tools
admin_executor = AgentExecutor(
    agent=agent,
    tools=ALL_TOOLS,
    security_policy={"resources": ["tool:admin", "tool:email"]}
)

# Supervisor routes to appropriate executor
class Supervisor:
    def route(self, query):
        if "admin" in query: return admin_executor
        return research_executor
```

## User Policies

The examples use two test users with different policies:

| User | Password | Policy |
|------|----------|--------|
| alice | Alice123! | GPT-3.5/Haiku only, max 500 tokens |
| bob | Bob@123! | GPT-3.5/4 + all Claude models, max 2000 tokens |

See `policies/user_policies.json` for details.

## Why bind_to_user?

Without `bind_to_user`, everyone uses the **service's identity**. With `bind_to_user`, each user's **JWT identity flows through** for policy evaluation.

This enables:
- Alice can only use GPT-3.5-turbo, max 500 tokens
- Bob can use GPT-4, max 2000 tokens
- Same service, different permissions based on WHO is calling

## Troubleshooting

### "No MACAW LocalAgent running"
Start the MACAW agent service:
```bash
macaw-agent service start
```

### "Authentication failed"
Check identity provider is running and configured:
```bash
# Keycloak
curl http://localhost:8080/realms/macaw/.well-known/openid_configuration

# Or check config
cat ~/.macaw/config.json
```

### "Policy violation"
This is expected for blocked operations! Check that:
1. Policies are loaded in MACAW
2. User has correct policy assigned
3. Parameters are within policy constraints
