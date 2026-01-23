# MACAW Adapter Examples

These examples demonstrate how MACAW adapters add enterprise security controls to AI applications through **drop-in replacements** for popular frameworks.

## Three Classes of Adapters

MACAW provides API-compatible replacements across the AI stack:

| Category | Frameworks | What It Secures |
|----------|------------|-----------------|
| **LLM APIs** | OpenAI, Anthropic | Direct LLM calls (chat completions, messages) |
| **Agentic Frameworks** | MCP (Model Context Protocol) | Tool servers, resources, agent-to-agent calls |
| **Orchestrators** | LangChain | Agent executors, tool chains, multi-agent workflows |

The adapters are thin wrappers that route requests through MACAW's security layer. Change one import line - your existing code continues to work unchanged, now with enterprise security built in.

## Why MACAW?

Building production AI applications requires more than just API calls. You need:

- **Policy-based access controls** - Who can use which models? What token limits apply? Which tools are allowed?
- **Identity propagation** - User identity must flow through every layer for per-user policies
- **Audit trail** - Tamper-proof logs of every AI operation for compliance
- **Observability** - Trace requests through the AI stack layers

Without MACAW, implementing these controls requires months of custom development, careful security review, and ongoing maintenance across every integration point.

**With MACAW**, you get all of this by changing an import:

```python
# Without MACAW: Alice can use any model, any tokens, no audit trail
from openai import OpenAI
client = OpenAI()

# With MACAW: Alice blocked from GPT-4 by policy, full audit trail
from macaw_adapters.openai import SecureOpenAI
client = SecureOpenAI(app_name="my-app")
```

MACAW deploys cryptographically-secured policy enforcement points at the edge using a zero-trust mesh architecture. Every tool endpoint becomes a PEP, enabling deterministic security controls even for non-deterministic AI systems.

## 30-Second Quick Start

```python
# Install
# pip install macaw-adapters[openai]

from macaw_adapters.openai import SecureOpenAI

# Same API as OpenAI - just a different import
client = SecureOpenAI(app_name="my-app")

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

That's it. Your OpenAI calls now flow through MACAW's security layer with policy enforcement and audit logging.

## Examples by Framework

### OpenAI (`openai/`)

Drop-in replacement for the OpenAI Python SDK with full API compatibility including streaming.

| Example | Description |
|---------|-------------|
| `openai_1a_dropin_simple.py` | Basic drop-in replacement with app-level policy |
| `openai_1b_multiuser_bind.py` | Per-user policies via `bind_to_user()` pattern |
| `openai_1b_multiuser_bind_streaming.py` | Same as 1b with streaming responses |
| `openai_1c_a2a_invoke.py` | Agent-to-agent calls via `invoke_tool()` |

**Progression**: Start with 1a for single-user apps. Move to 1b when you need different permissions per user (SaaS). Use 1c for agent orchestration systems.

### Anthropic (`anthropic/`)

Drop-in replacement for the Anthropic Python SDK with full API compatibility including streaming.

| Example | Description |
|---------|-------------|
| `anthropic_1a_dropin_simple.py` | Basic drop-in replacement with app-level policy |
| `anthropic_1b_multiuser_bind.py` | Per-user policies via `bind_to_user()` pattern |
| `anthropic_1b_multiuser_bind_streaming.py` | Same as 1b with streaming responses |
| `anthropic_1c_a2a_invoke.py` | Agent-to-agent calls via `invoke_tool()` |

**Progression**: Same pattern as OpenAI - the adapters provide consistent security semantics across LLM providers.

### MCP (`mcp/`)

Drop-in replacement for MCP (Model Context Protocol) servers and clients. Secures tool invocations, resource access, and agent communication.

| Example | Description |
|---------|-------------|
| `securemcp_server.py` | Basic SecureMCP server with tools and resources |
| `securemcp_calculator.py` | Calculator server with context tracking |
| `1a_simple_invocation.py` | Client invoking tools on a server |
| `1b_discovery_and_resources.py` | Discovering servers and accessing resources |
| `1c_logging_client.py` | Client with logging support |
| `1d_progress_client.py` | Progress tracking for long operations |
| `1e_sampling_*.py` | LLM sampling (client + server) |
| `1f_elicitation_*.py` | User input elicitation (client + server) |
| `1g_roots_*.py` | Filesystem roots (client + server) |

**Progression**: Start with the server example to create a SecureMCP tool server. Use 1a-1b to understand client patterns. Examples 1c-1g demonstrate advanced MCP features (logging, progress, sampling, elicitation, roots) all flowing through MACAW's security layer.

### LangChain (`langchain/`)

Drop-in replacements for LangChain agent components with MACAW security controls on tool access.

| Example | Description |
|---------|-------------|
| `langchain_1a_dropin_simple.py` | Basic agent with security policy |
| `langchain_1b_multiuser.py` | Per-user agents with different tool permissions |
| `langchain_1c_orchestration.py` | Multi-agent supervisor pattern |
| `langchain_1d_llm_openai.py` | Securing LLM calls (OpenAI) |
| `langchain_1e_llm_anthropic.py` | Securing LLM calls (Anthropic) |
| `langchain_1f_memory.py` | Memory integration with security |

**Progression**: Start with 1a to add tool access control to a single agent. Use 1b when different users need different tool permissions. Use 1c for multi-agent systems where each agent has isolated permissions.

## Running the Examples

### Prerequisites

1. **Install the adapters**:
   ```bash
   pip install macaw-adapters[all]
   # Or specific: pip install macaw-adapters[openai,anthropic,langchain,mcp]
   ```

2. **Set API keys** (for LLM examples):
   ```bash
   export OPENAI_API_KEY=sk-...
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

3. **MACAW client configured** (`~/.macaw/config.json`)

### Running

```bash
# OpenAI drop-in example
python openai/openai_1a_dropin_simple.py

# Anthropic with streaming
python anthropic/anthropic_1b_multiuser_bind_streaming.py

# MCP server (run first)
python mcp/securemcp_server.py
# Then in another terminal:
python mcp/1a_simple_invocation.py

# LangChain multi-agent
python langchain/langchain_1c_orchestration.py
```

## Tutorial

For a complete end-to-end tutorial with policy setup, identity provider configuration, and a realistic multi-user scenario, see:

**[demos/tutorial-1/](../demos/tutorial-1/)** - Role-Based AI Access Control

This tutorial demonstrates a FinTech Corp scenario with hierarchical policies:
- **alice** (Analyst): GPT-3.5 only, 500 token limit
- **bob** (Manager): GPT-3.5/4, 2000 token limit
- **carol** (Admin): All models, 4000 token limit

Includes setup scripts for Keycloak and Auth0 identity providers, complete MAPL policy files, and three demo applications showing different integration patterns.

## Console Dev Hub

Everything in this repository is also available in the MACAW Console's Dev Hub with interactive features:

```
Console > Dev Hub
├── Quick Start
│   └── Download Client SDK (macOS/Linux/Windows, Python 3.9-3.12) and Adapters
├── Tutorials
│   └── Role-Based Access Control
│       ├── Multi-User SaaS Patterns
│       ├── Agent Orchestration
│       └── Policy Hierarchies
├── Examples
│   ├── OpenAI (drop-in, multi-user, streaming, A2A)
│   ├── Anthropic (drop-in, multi-user, streaming, A2A)
│   ├── MCP
│   │   ├── Simple Invocation
│   │   ├── Discovery & Resources
│   │   ├── Logging
│   │   ├── Progress Tracking
│   │   ├── Sampling
│   │   ├── Elicitation
│   │   └── Roots
│   └── LangChain
│       ├── Drop-in Agents
│       ├── Multi-user Permissions
│       ├── Agent Orchestration
│       ├── LLM Wrappers (OpenAI, Anthropic)
│       └── Memory Integration
└── Reference
    ├── MACAW Client SDK
    ├── Adapter APIs
    ├── MAPL Policy Language
    └── Claims Mapping
```

Access at [console.macawsecurity.ai](https://console.macawsecurity.ai) → Dev Hub tab.

## Learn More

- **Documentation**: [docs.macawsecurity.ai](https://docs.macawsecurity.ai)
- **Console**: [console.macawsecurity.ai](https://console.macawsecurity.ai)
- **GitHub**: [github.com/macawsecurity/secureAI](https://github.com/macawsecurity/secureAI)
