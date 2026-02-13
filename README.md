# MACAW Secure AI Adapters

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![Version](https://img.shields.io/badge/version-0.5.25-green.svg)](https://github.com/macawsecurity/secureAI)

**Drop-in replacements for OpenAI, Anthropic, LangChain, and MCP for deterministic policy-based security controls for enterprise apps.**

## What This Is

Open source interfaces that add MACAW transparently to popular LLM and Agentic frameworks.

MACAW creates a **distributed zero-trust mesh** where tool endpoints serve as **policy enforcement points**, enabling preventative, deterministic security controls - even for non-deterministic LLMs and Agentic applications.

These adapters are thin wrappers that route requests through the MACAW security layer. Change one import line and get:

- **Deterministic policy enforcement** - Control models, tokens, operations, data access, and actions performed
- **Identity propagation** - User identity flows through every LLM call for per-user policies
- **Cryptographic audit trail** - Complete record of all AI operations with signatures
- **Zero code changes** - Your existing code works unchanged

Learn more about our research: [Authenticated Workflows](https://arxiv.org/abs/2602.10465) | [Protecting Context and Prompts](https://arxiv.org/abs/2602.10481)

## Installation

**From PyPI:**
```bash
pip install macaw-adapters[all]

# Or install specific adapters only
pip install macaw-adapters[openai]
pip install macaw-adapters[anthropic]
pip install macaw-adapters[langchain]
pip install macaw-adapters[mcp]
```

**From source:**
```bash
git clone https://github.com/macawsecurity/secureAI.git
pip install "./secureAI[all]"
```

## Quick Start

### SecureOpenAI

```python
# Before
from openai import OpenAI
client = OpenAI()

# After - just change the import
from macaw_adapters.openai import SecureOpenAI
client = SecureOpenAI(app_name="my-app")

# Same API, now with MACAW security
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### SecureAnthropic

```python
# Before
from anthropic import Anthropic
client = Anthropic()

# After
from macaw_adapters.anthropic import SecureAnthropic
client = SecureAnthropic(app_name="my-app")

# Same API
response = client.messages.create(
    model="claude-3-haiku-20240307",
    max_tokens=100,
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### SecureMCP

```python
from macaw_adapters.mcp import SecureMCP

mcp = SecureMCP("calculator")

@mcp.tool(description="Add two numbers")
def add(a: float, b: float) -> float:
    return a + b

mcp.run()
```

### LangChain

```python
# Before
from langchain_openai import ChatOpenAI

# After
from macaw_adapters.langchain import ChatOpenAI

# Same API
llm = ChatOpenAI(model="gpt-4")
response = llm.invoke("Hello!")
```

## Multi-User Support

For SaaS applications with per-user policies:

```python
from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider

# Create shared service
service = SecureOpenAI(app_name="my-saas")

# Authenticate user
jwt_token, _ = RemoteIdentityProvider().login("alice", "password")
user = MACAWClient(user_name="alice", iam_token=jwt_token, agent_type="user")
user.register()

# Bind user to service - their identity flows through
user_openai = service.bind_to_user(user)

# Policies evaluated against alice's permissions
response = user_openai.chat.completions.create(...)
```

## How It Works

```
┌─────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Your App  │────▶│  Secure Adapter     │────▶│   LLM API           │
│             │     │  (SecureOpenAI,etc) │     │   (OpenAI, Claude)  │
└─────────────┘     └──────────┬──────────┘     └─────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  MACAW Client       │
                    │  Endpoint           │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Trust Layer        │
                    │  Control Plane      │
                    │  ─────────────────  │
                    │  • Policy Engine    │
                    │  • Identity/Claims  │
                    │  • Audit Trail      │
                    └─────────────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Drop-in Replacement** | Change one import, keep all your code |
| **Per-User Policies** | Different users get different permissions |
| **Model Restrictions** | Control which models each user can access |
| **Token Limits** | Enforce max_tokens per user/role |
| **Streaming Support** | Full support for streaming responses |
| **Audit Logging** | Cryptographically signed audit trail |

## Requirements

- **Python 3.9+**
- **macaw_client v0.5.25+** - The MACAW client library (download from console)

### Getting Started

1. Sign up at [console.macawsecurity.ai](https://console.macawsecurity.ai)
2. Download and install macaw_client
3. Configure your workspace and policies
4. Install macaw-adapters and start building

## Adapters

| Adapter | Package | Wraps |
|---------|---------|-------|
| SecureOpenAI | `macaw_adapters.openai` | OpenAI Python SDK |
| SecureAnthropic | `macaw_adapters.anthropic` | Anthropic Python SDK |
| SecureMCP | `macaw_adapters.mcp` | Model Context Protocol |
| LangChain | `macaw_adapters.langchain` | LangChain (OpenAI, Anthropic, Agents) |

## Examples

See the [examples/](examples/) directory for complete working examples:

- `examples/openai/` - OpenAI adapter examples
- `examples/anthropic/` - Anthropic adapter examples
- `examples/langchain/` - LangChain integration examples
- `examples/mcp/` - MCP server and client examples

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

## Research

Learn more about the technical foundations of MACAW:

- **[Authenticated Workflows: A Systems Approach to Protecting Agentic AI](https://arxiv.org/abs/2602.10465)**
- **[Protecting Context and Prompts: Deterministic Security for Non-Deterministic AI](https://arxiv.org/abs/2602.10481)**

## Links

- **GitHub**: [github.com/macawsecurity/secureAI](https://github.com/macawsecurity/secureAI)
- **Documentation**: [www.macawsecurity.ai/docs](https://www.macawsecurity.ai/docs)
- **Console**: [console.macawsecurity.ai](https://console.macawsecurity.ai)
- **Support**: help@macawsecurity.com

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
