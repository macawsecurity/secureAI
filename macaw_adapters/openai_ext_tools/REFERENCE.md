# SecureOpenAI Reference

Drop-in replacement for OpenAI client with MACAW security. Supports three usage paths for different scenarios.

## Installation

```python
from macaw_adapters.openai import SecureOpenAI
```

Install the package:
```bash
pip install -e /path/to/secureAI
```

---

## When to Use Each Path

| Scenario | Path | Example |
|----------|------|---------|
| Simple app, no user distinction | Direct on service | `client.chat.completions.create()` |
| Multi-user, per-user policies | bind_to_user | `service.bind_to_user(user_client)` |
| A2A communication, explicit control | invoke_tool | `user.invoke_tool("tool:xxx/generate", ...)` |
| CLI tool, single operator | Direct on service | `client.chat.completions.create()` |
| SaaS with user accounts | bind_to_user | Different users = different permissions |

### Why bind_to_user?

Without `bind_to_user`, everyone uses the **service's identity**. With `bind_to_user`, each user's **JWT identity flows through** for policy evaluation.

This enables scenarios like:
- Alice: GPT-3.5 only, max 500 tokens
- Bob: GPT-3.5/4, max 2000 tokens

Same service, different permissions based on WHO is calling.

---

## Path 1: Direct on Service (Simplest)

```python
from macaw_adapters.openai import SecureOpenAI

# Just like using regular OpenAI client
client = SecureOpenAI(
    app_name="my-app",
    intent_policy={"purpose": "financial analysis"}
)

# Same API as OpenAI
response = client.chat.completions.create(
    model="gpt-4",
    max_tokens=500,
    messages=[{"role": "user", "content": "What is compound interest?"}]
)

print(response.choices[0].message.content)
```

**Use when**: Single app, no user distinction, app-level policies.

---

## Path 2: bind_to_user (Multi-user)

```python
from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider

# 1. Create SINGLE service (shared across all users)
service = SecureOpenAI(app_name="financial-service")

# 2. User login -> JWT -> MACAWClient
jwt_token, _ = RemoteIdentityProvider().login("alice", "Alice123!")
user = MACAWClient(
    user_name="alice",
    iam_token=jwt_token,
    agent_type="user",
    app_name="financial-app"
)
user.register()

# 3. Bind user to service
user_openai = service.bind_to_user(user)

# 4. Same API, user's identity flows through for policy evaluation
response = user_openai.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello"}]
)

# 5. Cleanup when user session ends
user_openai.unbind()
```

**Use when**: SaaS app, different users need different permissions.

---

## Path 3: invoke_tool (A2A)

```python
from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider

# 1. Create OpenAI service
service = SecureOpenAI(app_name="openai-service")

# 2. Create user agent
jwt_token, _ = RemoteIdentityProvider().login("alice", "Alice123!")
user = MACAWClient(
    user_name="alice",
    iam_token=jwt_token,
    agent_type="user",
    app_name="my-agent"
)
user.register()

# 3. Explicit invoke_tool - you control everything
result = user.invoke_tool(
    tool_name="tool:openai-service/generate",  # MAPL tool name
    parameters={
        "model": "gpt-3.5-turbo",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": "What is compound interest?"}]
    },
    target_agent=service.server_id  # Explicit routing
)

# Result is raw dict
content = result["choices"][0]["message"]["content"]
```

**Use when**: Building agent systems, need explicit control, cross-service communication.

---

## SecureOpenAI Class

```python
client = SecureOpenAI(
    api_key="sk-...",           # Optional: uses OPENAI_API_KEY env var
    app_name="my-app",          # Application name for MACAW registration
    intent_policy={...},        # Application-defined security policy (MAPL format)
    jwt_token="...",            # Optional: creates user-mode client
    user_name="alice"           # Optional: user name for user mode
)
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | str | env var | OpenAI API key |
| `app_name` | str | `"secure-openai-app"` | Application name for MACAW |
| `intent_policy` | dict | `{}` | Security policy (MAPL format) |
| `jwt_token` | str | None | JWT token for user mode |
| `user_name` | str | None | User name for user mode |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `client.server_id` | str | Agent ID after registration |
| `client.macaw_client` | MACAWClient | MACAW client instance |
| `client.openai_client` | OpenAI | Underlying OpenAI client |
| `client._mode` | str | "service" or "user" |

### Methods

#### bind_to_user(user_client) -> BoundSecureOpenAI

Bind service to a user's MACAW client for per-user identity.

```python
user_openai = service.bind_to_user(user_client)
```

Only valid in service mode. Returns `BoundSecureOpenAI` wrapper.

#### register_tool(name, handler) -> SecureOpenAI

Register a tool that OpenAI can call.

```python
client.register_tool("get_weather", get_weather_fn)
```

---

## BoundSecureOpenAI Class

Per-user wrapper created via `bind_to_user()`.

```python
user_openai = service.bind_to_user(user_client)

# Same API as SecureOpenAI
response = user_openai.chat.completions.create(...)

# Check binding status
if user_openai.is_bound:
    ...

# Cleanup
user_openai.unbind()
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_bound` | bool | Whether wrapper is still bound |
| `service` | SecureOpenAI | The bound service (raises if unbound) |
| `user_client` | MACAWClient | The bound user client (raises if unbound) |

### Methods

#### unbind()

Invalidate this binding. All future calls will raise `RuntimeError`.

---

## API Surface

SecureOpenAI mirrors the OpenAI API structure:

```python
# Chat completions
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "..."}],
    tools=[...],  # Optional: auto-discovered
    tool_choice="auto"
)

# Text completions
response = client.completions.create(
    model="gpt-3.5-turbo-instruct",
    prompt="..."
)

# Embeddings
response = client.embeddings.create(
    model="text-embedding-ada-002",
    input="..."
)
```

---

## MAPL Tool Names

SecureOpenAI uses MAPL-compliant tool names:

| Operation | Tool Name |
|-----------|-----------|
| Chat completions | `tool:{app_name}/generate` |
| Text completions | `tool:{app_name}/complete` |
| Embeddings | `tool:{app_name}/embed` |

Example: If `app_name="openai-service"`, the generate tool is `tool:openai-service/generate`.

---

## Tool Auto-Discovery

SecureOpenAI automatically discovers tool implementations from the caller's scope:

```python
# Define tools in your code
def get_weather(location: str) -> str:
    return f"Weather in {location}: Sunny, 72F"

# Define tool schemas for OpenAI
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",  # Must match function name
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    }
]

# Tools are auto-discovered and routed through MACAW PEP
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=tools
)
```

---

## Intent Policy Format (MAPL)

```python
intent_policy = {
    # Deny access to sensitive resources
    "denied_resources": ["*password*", "*credential*", "*secret*"],

    # Allow specific resources
    "resources": ["tool:get_weather", "tool:search_files"],

    # Parameter constraints
    "constraints": {
        "parameters": {
            "tool:search_files": {
                "path": ["*public*", "*reports*"]
            }
        },
        "denied_parameters": {
            "tool:*": {
                "query": ["*password*"]
            }
        }
    },

    # Application metadata
    "purpose": "weather and file search app"
}
```

---

## Authenticated Prompts

SecureOpenAI supports authenticated prompts for cryptographic proof of prompt origin:

```python
# Tools declare which parameters are prompts
self.tools = {
    f"tool:{self.app_name}/generate": {
        "handler": self._handle_generate,
        "prompts": ["messages"]  # messages param is authenticated
    }
}
```

Authenticated prompts are auto-created when `agent.authenticate_prompts` is enabled.

---

## Migration from OpenAI

```python
# Before
from openai import OpenAI
client = OpenAI()

# After (drop-in replacement)
from macaw_adapters.openai import SecureOpenAI
client = SecureOpenAI(
    app_name="my-app",
    intent_policy={"denied_resources": ["*sensitive*"]}
)

# Same API - no other code changes needed
response = client.chat.completions.create(...)
```
