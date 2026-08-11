"""
Native MCP endpoint for MACAW-registered tools - MCP 2026-07-28 binding.

Same contract and behaviour as _endpoint.py, written against the mcp>=2 SDK.
_serve.py picks between the two from the installed SDK version; nothing imports
this module directly.

What moved in the SDK (everything below the JSON-RPC boundary is unchanged):

    _endpoint.py  (mcp<2)                 _endpoint2.py  (mcp>=2)
    ------------------------------------  ------------------------------------
    Server(name, version)                 version is keyword-only
    @server.list_tools() -> list          on_list_tools -> ListToolsResult
    @server.call_tool()  -> list          on_call_tool  -> CallToolResult
    handler(tool_name, arguments)         handler(ctx, params)
    ctx = server.request_context          ctx is a handler argument
    Starlette + Mount + SessionManager    server.streamable_http_app()

The MACAW half - tool filtering, invoke_tool, the stub caller, the sampling and
elicitation bridge - is the same logic as _endpoint.py.
"""

import asyncio
import logging

import anyio
from mcp.server.caching import CacheHint
from mcp.server.lowlevel import Server
import mcp.types as types

from ._endpoint import _as_text
from .client import Client

logger = logging.getLogger(__name__)


def _peer(ctx) -> str:
    """Best-effort client identity for the log line.

    2026-07-28 is stateless: clients identify themselves per-request in _meta.
    Legacy peers still arrive over a session with client_params, so check both.
    """
    meta = ctx.meta or {}
    info = meta.get(types.CLIENT_INFO_META_KEY) if hasattr(meta, "get") else None
    if info:
        return f"{info.get('name', '?')}/{info.get('version', '?')}"

    # A peer that negotiated down to an older revision identified itself in the
    # initialize handshake instead, so it arrives on the session. mcp>=2 renamed
    # that field clientInfo -> client_info.
    params = getattr(getattr(ctx, "session", None), "client_params", None)
    legacy = getattr(params, "client_info", None) or getattr(params, "clientInfo", None)
    return f"{legacy.name}/{legacy.version}" if legacy else "unknown"


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
    Serve MACAW-registered tools over native MCP. See _endpoint.serve().

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
        #
        # Sampling is deprecated as of 2026-07-28 (SEP-2577) and the SDK warns on
        # this call. It still works for clients that support it; MACAW-native
        # ctx.sample() over the mesh is unaffected either way.
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
        # 2026-07-28 renamed this parameter from requestedSchema.
        result = _on_loop(
            live["session"].elicit(message=prompt, requested_schema=schema)
        )
        if result.action != "accept" or not result.content:
            return default
        return result.content.get("value", default)

    caller.set_sampling_handler(_sample)
    caller.set_elicitation_handler(_elicit)

    async def _list_tools(ctx, params) -> types.ListToolsResult:
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
        return types.ListToolsResult(tools=tools)

    async def _call_tool(ctx, params) -> types.CallToolResult:
        live["session"] = ctx.session

        tool_name = params.name
        arguments = params.arguments or {}
        logger.info("tools/call %s from %s", tool_name, _peer(ctx))

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
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=_as_text(result))]
        )

    # Tool availability is an authorization statement, so a cached one is a stale
    # one: ttl_ms=0 tells clients to re-ask, scope="private" forbids shared
    # intermediaries from reusing an answer across principals. These are also the
    # SDK's current defaults - stated here so a future default is our decision to
    # change rather than something we inherit silently.
    no_caching = {
        "tools/list": CacheHint(ttl_ms=0, scope="private"),
        "server/discover": CacheHint(ttl_ms=0, scope="private"),
    }

    server = Server(
        name,
        version=version,
        cache_hints=no_caching,
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )

    if transport == "stdio":
        from mcp.server.stdio import stdio_server

        logger.info("Serving MCP over stdio: %s", name)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    elif transport == "http":
        import uvicorn

        # streamable_http_app() builds the Starlette app and wires the session
        # manager as its lifespan, so there is nothing to start by hand.
        #
        # stateless_http=True is the 2026-07-28 transport: no Mcp-Session-Id, every
        # request self-describing. The SDK still defaults it to False for backward
        # compatibility, but sessions are the thing MACAW never needed - identity,
        # policy, and the signature travel with each invocation, not with a
        # connection - so there is no cross-call state here to keep.
        app = server.streamable_http_app(
            streamable_http_path="/mcp", host=host, stateless_http=True
        )

        logger.info("Serving MCP over http: %s at http://%s:%s/mcp", name, host, port)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        await uvicorn.Server(config).serve()

    else:
        raise ValueError(f"transport must be 'stdio' or 'http', got {transport!r}")
