# SecureMCP Reference

SecureMCP provides enterprise-grade security for Model Context Protocol servers and clients through integration with MACAW Control Plane.

## Server

```python
from securemcp import Server

server = Server(
    name="my-server",
    version="1.0.0",
    port=8080,              # Optional: port to listen on
    host="localhost",       # Optional: host to bind to
    service_account="name"  # Optional: run as service account
)
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | required | Server name for identification |
| `version` | str | `"1.0.0"` | Server version |
| `port` | int | `8080` | Port to listen on |
| `host` | str | `"localhost"` | Host to bind to |
| `service_account` | str | `None` | Run as service account instead of user identity |

### Decorators

#### `@server.tool(name, description, **kwargs)`

Register a tool that can be invoked by clients.

```python
@server.tool("add", description="Add two numbers")
def add(a: float, b: float) -> dict:
    return {"result": a + b}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | str | Tool name (uses function name if not provided) |
| `description` | str | Tool description |
| `**kwargs` | dict | Additional metadata |

#### `@server.resource(pattern, description, **kwargs)`

Register a read-only resource.

```python
@server.resource("config/{name}", description="Configuration resource")
class ConfigResource:
    def read(self, name: str) -> dict:
        return {"config": name, "value": "..."}
```

#### `@server.prompt(name, description, **kwargs)`

Register a prompt template for AuthenticatedPrompt creation.

```python
@server.prompt("summarize", description="Summarize text")
def summarize(text: str) -> str:
    return f"Please summarize: {text}"
```

### Lifecycle Methods

```python
# Start server (async)
await server.start()

# Stop server (async)
await server.stop()

# Run server (blocking)
server.run()
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `server.tools` | dict | Registered tools |
| `server.resources` | dict | Registered resources |
| `server.prompts` | dict | Registered prompts |
| `server.macaw_client` | MACAWClient | MACAW client instance |
| `server.server_id` | str | Agent ID after registration |

---

## Client

```python
from securemcp import Client

client = Client(
    name="my-client",
    version="1.0.0",
    server_url="http://localhost:8080"  # Optional
)
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | required | Client name |
| `version` | str | `"1.0.0"` | Client version |
| `server_url` | str | `None` | Default server URL |

### Methods

#### `connect(server_url, transport)`

```python
await client.connect(
    server_url="http://localhost:8080",
    transport="sse"  # or "stdio"
)
```

#### `call_tool(tool_name, arguments, target_server)`

```python
result = await client.call_tool(
    tool_name="add",
    arguments={"a": 1, "b": 2},
    target_server="app/my-server"  # Required per MCP spec
)
```

#### `get_resource(resource_uri, target_server)`

```python
config = await client.get_resource(
    resource_uri="config/database",
    target_server="app/my-server"
)
```

#### `get_prompt(prompt_name, arguments, target_server)`

```python
prompt = await client.get_prompt(
    prompt_name="summarize",
    arguments={"text": "Hello world"},
    target_server="app/my-server"
)
```

#### `list_servers()`

```python
servers = await client.list_servers()
# Returns: [{"name": "...", "instance_id": "...", "tools": [...]}]
```

#### `list_tools(server_name)`

```python
tools = await client.list_tools("app/my-server")
# Returns: [{"name": "add", "server": "...", "description": "..."}]
```

#### `set_default_server(server_name)`

```python
client.set_default_server("app/my-server")
# Now call_tool can omit target_server
```

#### `disconnect()`

```python
await client.disconnect()
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `client.client_id` | str | Client's unique ID |
| `client.is_secure` | bool | True if MACAW is enabled |
| `client.connected` | bool | Connection status |

---

## Example: Calculator Server

```python
from securemcp import Server

server = Server(name="calculator", version="1.0.0")

@server.tool("add", description="Add two numbers")
def add(a: float, b: float) -> dict:
    return {"result": a + b}

@server.tool("multiply", description="Multiply two numbers")
def multiply(a: float, b: float) -> dict:
    return {"result": a * b}

if __name__ == "__main__":
    server.run()
```

## Example: Calculator Client

```python
import asyncio
from securemcp import Client

async def main():
    client = Client(name="calc-client")
    await client.connect()

    # Discover servers
    servers = await client.list_servers()
    print(f"Found servers: {servers}")

    # Set default and call tools
    client.set_default_server("app/calculator")
    result = await client.call_tool("add", {"a": 5, "b": 3})
    print(f"5 + 3 = {result}")

    await client.disconnect()

asyncio.run(main())
```

## Security Model

All security is delegated to MACAW Control Plane:

1. **Registration**: Server/client registers with LocalAgent on startup
2. **Tool Invocation**: Requests routed through ToolAgent PEP
3. **Policy Enforcement**: MACAW enforces policies on every request
4. **Cryptographic Signing**: All invocations are signed
5. **Audit Logging**: Security events logged to audit trail

No security logic in application code - MACAW handles everything.
