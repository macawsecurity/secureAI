"""
Native MCP endpoint for MACAW-registered tools.

Lets an ordinary MCP client (Claude Desktop, Cursor, mcp.ClientSession) talk to a
SecureMCP server or a SecureMCPProxy without knowing anything about MACAW.

Every JSON-RPC call is translated into the same invoke_tool() a MACAW-aware client
would make, so both entry paths land on the identical enforcement trunk:

    external client --JSON-RPC--> serve() --+
                                            +--> invoke_tool --> LocalAgent --> PEP --> tool
    MACAW client ---------------------------+

The external caller has no MACAW identity of its own, so a stub agent
("<name>-external") is registered to stand in for it. That stub is also where
server->client callbacks land: ctx.sample() / ctx.elicit() route back to it over the
bus, and it forwards them out over the live MCP session.
"""

import asyncio
import json
import logging

import anyio
from mcp.server.lowlevel import Server
import mcp.types as types

from .client import Client

logger = logging.getLogger(__name__)


def _as_text(result) -> str:
    """Render a tool result for MCP.

    MACAWClient wraps scalar returns as {"result": x}, so unwrap that one shape.
    Anything else is a real payload from the tool and must survive intact - a tool
    returning {"result": 13, "expression": "...", "history_count": 1} loses two
    fields if we reach for ["result"].
    """
    if isinstance(result, dict):
        if set(result.keys()) == {"result"}:
            return str(result["result"])
        return json.dumps(result, default=str)
    return str(result)


async def serve(
    name: str,
    version: str,
    registry,
    target_agent: str,
    prefix: str = "",
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """
    Serve MACAW-registered tools over native MCP.

    Args:
        name: Server name (also names the stub caller agent)
        version: Server version
        registry: MACAWClient that holds the tools (the server's / proxy's own client).
                  Its .tools dict is the single source of truth for tools/list.
        target_agent: Agent to invoke the tools on
        prefix: MAPL name prefix. "" for SecureMCP, "tool:<app>/" for SecureMCPProxy.
                Stripped on the way out, re-added on the way in.
        transport: "stdio" or "http"
        host: Bind host (http only)
        port: Bind port (http only)
    """
    loop = asyncio.get_running_loop()
    live = {}  # holds the current MCP session for server->client callbacks

    # Stub identity for callers that have no MACAW identity of their own.
    caller = Client(f"{name}-external")

    def _on_loop(coro):
        # Callback handlers run in macaw_client's handler_pool thread, but the MCP
        # session is bound to this event loop. Hand the coroutine back to it.
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    def _sample(prompt, system_prompt, max_tokens, temperature=None, **_kwargs):
        # Forward temperature only if the calling tool asked for one. MCP carries
        # it as an optional hint, and the client is free to ignore or reject it.
        extra = {} if temperature is None else {"temperature": temperature}
        result = _on_loop(
            live["session"].create_message(
                messages=[
                    types.SamplingMessage(
                        role="user",
                        content=types.TextContent(type="text", text=prompt),
                    )
                ],
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                **extra,
            )
        )
        return result.content.text

    def _elicit(prompt, options, input_type, default, required, **_kwargs):
        schema = {
            "type": "object",
            "required": ["value"] if required else [],
            "properties": {
                "value": {"type": "string", **({"enum": options} if options else {})}
            },
        }
        result = _on_loop(live["session"].elicit(message=prompt, requestedSchema=schema))
        if result.action != "accept" or not result.content:
            return default
        return result.content.get("value", default)

    caller.set_sampling_handler(_sample)
    caller.set_elicitation_handler(_elicit)

    server = Server(name, version)

    @server.list_tools()
    async def _list_tools():
        tools = []
        for full_name, config in registry.tools.items():
            if not full_name.startswith(prefix):
                continue
            bare = full_name[len(prefix):]
            # Resources and prompts are registered as tools with these prefixes;
            # they are not MCP tools. Internal callbacks are not either.
            if bare.startswith(("resource:", "prompt:", "_mcp_")):
                continue
            tools.append(
                types.Tool(
                    name=bare,
                    description=config.get("description", ""),
                    inputSchema=config.get("metadata", {}).get("schema")
                    or {"type": "object"},
                )
            )
        return tools

    @server.call_tool()
    async def _call_tool(tool_name: str, arguments: dict):
        ctx = server.request_context
        live["session"] = ctx.session

        peer = getattr(ctx.session.client_params, "clientInfo", None)
        logger.info(
            "tools/call %s from %s",
            tool_name,
            f"{peer.name}/{peer.version}" if peer else "unknown",
        )

        # Same call a MACAW client makes: policy, signing, and audit happen downstream.
        #
        # invoke_tool() is synchronous and blocks until the result comes back, so it
        # MUST run off the event loop. If it blocks the loop, any tool that calls
        # ctx.sample() / ctx.elicit() deadlocks: the handler routes the callback to
        # our stub, whose handler needs this loop to send sampling/createMessage back
        # over the session - and the loop is still blocked here waiting for the very
        # invocation that callback belongs to. Both sides then time out.
        result = await anyio.to_thread.run_sync(
            lambda: caller.macaw_client.invoke_tool(
                prefix + tool_name, arguments, target_agent=target_agent
            )
        )
        return [types.TextContent(type="text", text=_as_text(result))]

    init_options = server.create_initialization_options()

    if transport == "stdio":
        from mcp.server.stdio import stdio_server

        logger.info("Serving MCP over stdio: %s", name)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, init_options)

    elif transport == "http":
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.routing import Mount
        import uvicorn

        manager = StreamableHTTPSessionManager(app=server)
        app = Starlette(routes=[Mount("/mcp", app=manager.handle_request)])

        logger.info("Serving MCP over http: %s at http://%s:%s/mcp", name, host, port)
        async with manager.run():
            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            await uvicorn.Server(config).serve()

    else:
        raise ValueError(f"transport must be 'stdio' or 'http', got {transport!r}")
