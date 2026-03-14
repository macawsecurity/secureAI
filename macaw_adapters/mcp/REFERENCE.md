# SecureMCP Reference

SecureMCP provides enterprise-grade security for Model Context Protocol through integration with MACAW Control Plane.

**Two main components:**
1. **SecureMCP** — For MCP servers YOU write (FastMCP-compatible decorators)
2. **SecureMCPProxy** — For external MCP servers you DON'T control (inline gateway)

---

## SecureMCP (Your MCP Servers)

FastMCP-compatible decorator API with MACAW security. All tool invocations are cryptographically signed, policy-enforced, and audit-logged.

```python
from macaw_adapters.mcp import SecureMCP, Context

mcp = SecureMCP("calculator")

@mcp.tool(description="Add two numbers")
def add(a: float, b: float) -> float:
    return a + b

if __name__ == "__main__":
    mcp.run()
```

### Constructor

```python
SecureMCP(
    name: str,                              # Server name (required)
    version: str = "1.0.0",                 # Server version
    intent_policy: dict = None,             # MAPL policy declaration
    roots: list[str] = None,                # Filesystem paths server can access
    **kwargs                                # Additional MACAWClient options
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | required | Server name for MACAW registration |
| `version` | str | `"1.0.0"` | Server version |
| `intent_policy` | dict | `None` | MAPL policy (resources, denied_resources, etc.) |
| `roots` | list | `None` | Filesystem paths this server can access (MCP roots) |

### Decorators

#### `@mcp.tool(name, description, prompts)`

Register a tool that can be invoked by clients.

```python
@mcp.tool(description="Add two numbers")
def add(a: float, b: float) -> float:
    return a + b

@mcp.tool(description="Calculate with history")
def calculate(ctx: Context, op: str, a: float, b: float) -> dict:
    # ctx parameter gives access to context vault
    history = ctx.get("calc_history") or []
    result = a + b if op == "add" else a * b
    history.append({"op": op, "result": result})
    ctx.set("calc_history", history)
    return {"result": result}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | str | Tool name (defaults to function name) |
| `description` | str | Tool description (defaults to docstring) |
| `prompts` | list | Parameter names to treat as AuthenticatedPrompts |

#### `@mcp.resource(uri_pattern, description)`

Register a read-only resource.

```python
@mcp.resource("calc://history")
def get_history(ctx: Context) -> dict:
    return {"history": ctx.get("calc_history") or []}

@mcp.resource("config://{key}")
def get_config(ctx: Context, key: str) -> dict:
    return {"key": key, "value": "..."}
```

#### `@mcp.prompt(name, description)`

Register a prompt template.

```python
@mcp.prompt(description="Generate a greeting")
def greeting(name: str) -> str:
    return f"Hello, {name}! How can I help?"
```

### Lifecycle

```python
mcp.run(transport="stdio")    # Blocking run (stdio or sse)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `mcp.name` | str | Server name |
| `mcp.version` | str | Server version |
| `mcp.agent_id` | str | MACAW agent ID (after run) |
| `mcp.roots` | list | Filesystem roots |

---

## Context

Request context passed to tool handlers. Provides access to context vault, progress reporting, sampling, and elicitation.

```python
@mcp.tool()
def my_tool(ctx: Context, param: str) -> dict:
    # Context vault (persistent storage)
    ctx.set("key", "value")
    data = ctx.get("key")

    # Logging
    ctx.info("Processing request")
    ctx.audit("data_access", target="records", outcome="success")

    return {"result": data}
```

### Methods

| Method | Description |
|--------|-------------|
| `ctx.get(key)` | Get value from context vault |
| `ctx.set(key, value)` | Set value in context vault |
| `await ctx.report_progress(progress, message)` | Report progress (0.0-1.0) |
| `await ctx.read_resource(uri)` | Read another resource |
| `await ctx.sample(prompt, ...)` | Request LLM completion from client |
| `await ctx.elicit(prompt, ...)` | Request user input from client |

### Logging Methods

| Method | Description |
|--------|-------------|
| `ctx.debug(message)` | Log debug message |
| `ctx.info(message)` | Log info message |
| `ctx.warning(message)` | Log warning message |
| `ctx.error(message)` | Log error message |
| `ctx.audit(action, target, outcome, **metadata)` | Cryptographically signed audit entry |

### Sampling (MCP Sampling)

Request LLM completion from the calling client:

```python
@mcp.tool()
async def analyze(ctx: Context, text: str) -> dict:
    summary = await ctx.sample(
        prompt=f"Summarize: {text}",
        system_prompt="You are a helpful assistant.",
        max_tokens=500,
        temperature=0.7
    )
    return {"summary": summary}
```

### Elicitation (MCP Elicitation)

Request user input during tool execution:

```python
@mcp.tool()
async def delete_file(ctx: Context, path: str) -> dict:
    confirmed = await ctx.elicit(
        prompt=f"Delete {path}?",
        input_type="confirm",
        default="no"
    )
    if confirmed:
        # perform deletion
        return {"deleted": path}
    return {"cancelled": True}
```

---

## SecureMCPProxy (External MCP Servers)

Inline gateway that wraps external MCP servers (Snowflake, Salesforce, Databricks, etc.) with MACAW security.

```python
from macaw_adapters.mcp import SecureMCPProxy

# HTTP transport (remote MCP servers)
proxy = SecureMCPProxy(
    app_name="snowflake-mcp",
    upstream_url="http://localhost:9000/mcp"
)

# stdio transport (local MCP servers via subprocess)
proxy = SecureMCPProxy(
    app_name="salesforce-dx",
    command=["npx", "@salesforce/mcp", "--orgs", "DEFAULT"],
    env={"HOME": os.environ["HOME"]}
)

# Use tools
tools = proxy.list_tools()
result = proxy.call_tool("run_snowflake_query", {"statement": "SELECT 1"})
```

### Constructor

```python
SecureMCPProxy(
    app_name: str,                          # Application name (required)
    # HTTP transport
    upstream_url: str = None,               # URL of upstream MCP server
    upstream_auth: dict = None,             # Auth config (see below)
    # stdio transport
    command: list[str] = None,              # Command to start MCP server
    env: dict = None,                       # Environment variables
    # Identity
    iam_token: str = None,                  # IAM token for user identity
    user_name: str = None,                  # User name
    intent_policy: dict = None              # MAPL intent policy
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `app_name` | str | Application name for MACAW registration |
| `upstream_url` | str | URL for HTTP transport |
| `upstream_auth` | dict | Auth: `{"type": "bearer", "token": "..."}` or `{"type": "api_key", "api_key": "...", "header_name": "X-API-Key"}` |
| `command` | list | Command for stdio transport |
| `env` | dict | Environment variables for stdio subprocess |
| `iam_token` | str | IAM token for authenticated identity |
| `user_name` | str | User name (used with local identity) |
| `intent_policy` | dict | MAPL policy for this proxy |

**Note:** Provide either `upstream_url` (HTTP) or `command` (stdio), not both.

### Methods

#### `call_tool(tool_name, params) -> Any`

Call a tool through MACAW security.

```python
result = proxy.call_tool("run_snowflake_query", {
    "statement": "SELECT * FROM customers LIMIT 10"
})
```

Flow:
1. MACAWClient.invoke_tool() checks MAPL policy
2. Signs the invocation cryptographically
3. Logs to audit trail
4. Proxy handler forwards to upstream MCP server

#### `list_tools() -> list[dict]`

List available tools discovered from upstream.

```python
tools = proxy.list_tools()
# Returns: [{"name": "run_query", "description": "...", "schema": {...}}]
```

#### `get_tool_schema(tool_name) -> dict`

Get schema for a specific tool.

```python
schema = proxy.get_tool_schema("run_snowflake_query")
```

#### `bind_to_user(user_client) -> BoundMCPProxy`

Bind proxy to a specific user's identity for multi-tenant applications.

```python
from macaw_client import MACAWClient, RemoteIdentityProvider

# Authenticate user via Keycloak/Okta
jwt, _ = RemoteIdentityProvider().login("alice", "Alice123!")
alice = MACAWClient(user_name="alice", iam_token=jwt, app_name="my-app")
alice.register()

# Bind proxy to Alice's identity
alice_proxy = proxy.bind_to_user(alice)

# Calls now use Alice's identity and policy
result = alice_proxy.call_tool("run_snowflake_query", {...})
```

#### `refresh_tools()`

Re-discover tools from upstream (if tools may have changed).

```python
proxy.refresh_tools()
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `proxy.app_name` | str | Application name |
| `proxy.upstream_url` | str | Upstream URL |
| `proxy.agent_id` | str | MACAW agent ID |
| `proxy.server_id` | str | Alias for agent_id |
| `proxy.tool_schemas` | dict | Discovered tool schemas |
| `proxy.is_connected` | bool | Connection status |

---

## BoundMCPProxy

MCP Proxy bound to a specific user's identity. All calls use the user's policy and audit trail.

```python
bound_proxy = proxy.bind_to_user(user_client)

# Methods (same as SecureMCPProxy)
result = bound_proxy.call_tool("tool_name", params)
tools = bound_proxy.list_tools()
schema = bound_proxy.get_tool_schema("tool_name")
```

---

## Examples

### SecureMCP Calculator Server

```python
from macaw_adapters.mcp import SecureMCP, Context

mcp = SecureMCP("calculator")

@mcp.tool(description="Add two numbers")
def add(a: float, b: float) -> float:
    return a + b

@mcp.tool(description="Multiply two numbers")
def multiply(a: float, b: float) -> float:
    return a * b

@mcp.tool(description="Calculate with history")
def calculate(ctx: Context, op: str, a: float, b: float) -> dict:
    history = ctx.get("calc_history") or []
    result = a + b if op == "add" else a * b
    history.append({"op": op, "a": a, "b": b, "result": result})
    ctx.set("calc_history", history)
    return {"result": result, "history_count": len(history)}

@mcp.resource("calc://history")
def get_history(ctx: Context) -> dict:
    return {"history": ctx.get("calc_history") or []}

if __name__ == "__main__":
    mcp.run()
```

### SecureMCPProxy with Snowflake

```python
from macaw_adapters.mcp import SecureMCPProxy

proxy = SecureMCPProxy(
    app_name="snowflake-data",
    upstream_url="http://localhost:9000/mcp"
)

# List available tools
for tool in proxy.list_tools():
    print(f"  {tool['name']}: {tool['description']}")

# Query data
result = proxy.call_tool("run_snowflake_query", {
    "statement": "SELECT CURRENT_USER(), CURRENT_ROLE()"
})
print(result)
```

### Multi-User SecureMCPProxy

```python
from macaw_adapters.mcp import SecureMCPProxy
from macaw_client import MACAWClient, RemoteIdentityProvider

# Service creates shared proxy
proxy = SecureMCPProxy(
    app_name="data-platform",
    upstream_url="http://localhost:9000/mcp"
)

# Authenticate users via Keycloak
alice_jwt, _ = RemoteIdentityProvider().login("alice", "Alice123!")
alice = MACAWClient(user_name="alice", iam_token=alice_jwt, app_name="data-platform")
alice.register()

bob_jwt, _ = RemoteIdentityProvider().login("bob", "Bob@123!")
bob = MACAWClient(user_name="bob", iam_token=bob_jwt, app_name="data-platform")
bob.register()

# Per-user proxies
alice_proxy = proxy.bind_to_user(alice)
bob_proxy = proxy.bind_to_user(bob)

# Each user's calls use their identity and policy
alice_result = alice_proxy.call_tool("list_objects", {"object_type": "database"})
bob_result = bob_proxy.call_tool("run_snowflake_query", {"statement": "SELECT 1"})
```

---

## Security Model

All security is delegated to MACAW Control Plane:

1. **Registration**: Server/proxy registers with LocalAgent on startup
2. **Tool Invocation**: Requests routed through ToolAgent PEP
3. **Policy Enforcement**: MAPL policies enforced on every request
4. **Cryptographic Signing**: All invocations are signed per-request
5. **Audit Logging**: Security events logged with cryptographic proof
6. **Identity Propagation**: User identity flows through bind_to_user()

**Per-invocation security**: Even with persistent connections (stdio), MACAW creates fresh AuthenticatedContext for each call. This solves the "shared context" problem in standard MCP.

---

## Legacy API

The `Server` and `Client` classes are available for backwards compatibility:

```python
from macaw_adapters.mcp import Server, Client
```

For new projects, use `SecureMCP` (your servers) or `SecureMCPProxy` (external servers).

---

## Installation

```bash
pip install macaw-adapters[mcp-proxy]
```

For more information: https://macawsecurity.ai
