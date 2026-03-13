#!/usr/bin/env python3
"""
SecureMCPProxy - Inline Gateway for External MCP Servers.

Wraps any third-party MCP server (Salesforce, Google, Slack, etc.)
with MACAW security: policy enforcement, cryptographic signing, audit.

This is an "inline gateway" - it runs in your process and proxies calls
to external MCP servers through MACAW's security layer.

Supports two transport modes:
- HTTP: Connect to remote MCP servers via HTTP/SSE
- stdio: Connect to local MCP servers via subprocess stdin/stdout

Usage (HTTP):
    from macaw_adapters.mcp import SecureMCPProxy

    proxy = SecureMCPProxy(
        app_name="salesforce-mcp",
        upstream_url="https://mcp.salesforce.com",
        upstream_auth={"type": "bearer", "token": SF_TOKEN}
    )

Usage (stdio):
    proxy = SecureMCPProxy(
        app_name="salesforce-dx",
        command=["npx", "@salesforce/mcp", "--orgs", "DEFAULT"],
        env={"HOME": os.environ["HOME"]}
    )

Common API (transport-agnostic):
    tools = proxy.list_tools()
    result = proxy.call_tool("query_accounts", {"limit": 10})
    user_proxy = proxy.bind_to_user(user_client)

Security Model:
- MACAW creates AuthenticatedContext for EACH invocation
- Even with persistent stdio, each call has fresh identity/policy/signature
- This solves the "shared context" problem in standard MCP

Install: pip install macaw-adapters[mcp-proxy]
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class UpstreamAuth:
    """Authentication configuration for upstream MCP server."""
    type: str = "none"  # "none", "bearer", "api_key", "oauth"
    token: Optional[str] = None
    api_key: Optional[str] = None
    header_name: str = "Authorization"  # For custom header names


class SecureMCPProxy:
    """
    Inline gateway that wraps external MCP servers with MACAW security.

    Connects to any MCP server (Salesforce, Google, Slack, etc.) and:
    - Auto-discovers available tools via MCP protocol
    - Re-exposes tools through MACAWClient (policy, signing, audit)
    - Supports multi-user identity via bind_to_user()

    Transports:
    - HTTP: For remote MCP servers (Snowflake, Databricks, Google Cloud)
    - stdio: For local MCP servers run as subprocesses (Salesforce DX CLI)

    Security Model:
    - MACAW creates AuthenticatedContext for EACH invocation
    - Even with persistent stdio subprocess, each call gets fresh context
    - Policy enforcement, signing, and audit happen per-invocation
    """

    def __init__(
        self,
        app_name: str,
        # HTTP transport options
        upstream_url: Optional[str] = None,
        upstream_auth: Optional[Dict[str, Any]] = None,
        # stdio transport options
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        # Identity (for single-user or service mode)
        iam_token: Optional[str] = None,
        user_name: Optional[str] = None,
        # Optional intent policy
        intent_policy: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize SecureMCPProxy.

        Provide either upstream_url (HTTP) or command (stdio), not both.

        Args:
            app_name: Application name for MACAW registration (e.g., "salesforce-mcp")

            HTTP transport:
                upstream_url: URL of the upstream MCP server
                upstream_auth: Authentication config:
                              {"type": "bearer", "token": "..."} or
                              {"type": "api_key", "api_key": "...", "header_name": "X-API-Key"}

            stdio transport:
                command: Command to start MCP server (e.g., ["npx", "@salesforce/mcp"])
                env: Environment variables for subprocess

            Common:
                iam_token: Optional IAM token for user identity
                user_name: Optional user name
                intent_policy: Optional MACAW intent policy
        """
        self.app_name = app_name
        self.intent_policy = intent_policy or {}

        # Determine transport
        if command and upstream_url:
            raise ValueError("Provide either upstream_url (HTTP) or command (stdio), not both")
        elif command:
            self._transport = "stdio"
            self._stdio_command = command
            self._stdio_env = env or {}
            self.upstream_url = f"stdio://{command[0]}"  # For display
            logger.info(f"Using stdio transport: {' '.join(command)}")
        elif upstream_url:
            self._transport = "http"
            self.upstream_url = upstream_url
            self.upstream_auth = UpstreamAuth(**(upstream_auth or {}))
            logger.info(f"Using HTTP transport: {upstream_url}")
        else:
            raise ValueError("Must provide either upstream_url (HTTP) or command (stdio)")

        # State
        self.tool_schemas: Dict[str, Dict[str, Any]] = {}
        self._connected = False

        # Connect to upstream and discover tools
        self._connect_and_discover()

        # Setup MACAWClient with discovered tools
        self._setup_macaw_client(iam_token, user_name)

    def _connect_and_discover(self):
        """Connect to upstream MCP server and discover tools."""
        try:
            if self._transport == "stdio":
                asyncio.run(self._async_discover_tools_stdio())
            else:
                asyncio.run(self._async_discover_tools_http())
        except Exception as e:
            logger.error(f"Failed to connect to upstream: {e}")
            raise ConnectionError(f"Cannot connect to upstream MCP server: {e}")

    async def _async_discover_tools_http(self):
        """Discover tools from upstream MCP server via HTTP."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:
            raise ImportError(
                "MCP client not installed. Install with: pip install macaw-adapters[mcp-proxy]"
            )

        # Build HTTP client with auth
        http_client = self._create_http_client()

        try:
            async with streamable_http_client(
                self.upstream_url,
                http_client=http_client
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    # Discover tools
                    response = await session.list_tools()

                    for tool in response.tools:
                        self.tool_schemas[tool.name] = {
                            "name": tool.name,
                            "description": tool.description or f"Tool: {tool.name}",
                            "schema": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                        }

            self._connected = True
            logger.info(f"Discovered {len(self.tool_schemas)} tools from {self.upstream_url}")

        finally:
            if http_client:
                await http_client.aclose()

    async def _async_discover_tools_stdio(self):
        """Discover tools from upstream MCP server via stdio subprocess."""
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters
        except ImportError:
            raise ImportError(
                "MCP client not installed. Install with: pip install macaw-adapters[mcp-proxy]"
            )

        params = StdioServerParameters(
            command=self._stdio_command[0],
            args=self._stdio_command[1:] if len(self._stdio_command) > 1 else [],
            env=self._stdio_env or None
        )

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Discover tools
                response = await session.list_tools()

                for tool in response.tools:
                    self.tool_schemas[tool.name] = {
                        "name": tool.name,
                        "description": tool.description or f"Tool: {tool.name}",
                        "schema": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                    }

        self._connected = True
        logger.info(f"Discovered {len(self.tool_schemas)} tools via stdio")

    def _create_http_client(self):
        """Create httpx client with authentication headers."""
        try:
            import httpx
        except ImportError:
            raise ImportError(
                "httpx not installed. Install with: pip install macaw-adapters[mcp-proxy]"
            )

        headers = {}

        if self.upstream_auth.type == "bearer" and self.upstream_auth.token:
            headers["Authorization"] = f"Bearer {self.upstream_auth.token}"
        elif self.upstream_auth.type == "api_key" and self.upstream_auth.api_key:
            header_name = self.upstream_auth.header_name or "X-API-Key"
            headers[header_name] = self.upstream_auth.api_key

        return httpx.AsyncClient(headers=headers) if headers else None

    def _setup_macaw_client(self, iam_token: Optional[str], user_name: Optional[str]):
        """
        Create MACAWClient with discovered tools as proxy handlers.

        Key security property: MACAWClient creates AuthenticatedContext for
        EACH invocation, providing per-call identity, policy, and signing.
        This solves the "shared context" problem even with persistent stdio.
        """
        try:
            from macaw_client import MACAWClient
        except ImportError:
            raise ImportError(
                "MACAWClient not installed. Download from https://console.macawsecurity.ai"
            )

        # Build tool config with proxy handlers
        # Use MAPL-compliant names: tool:{app_name}/{tool_name}
        tools_config = {}
        tool_names = []

        for name, schema in self.tool_schemas.items():
            mapl_name = f"tool:{self.app_name}/{name}"
            tool_names.append(mapl_name)
            tools_config[mapl_name] = {
                "handler": self._make_proxy_handler(name),
                "description": schema.get("description", ""),
                "metadata": {
                    "schema": schema.get("schema", {}),
                    "upstream": self.upstream_url,
                    "transport": self._transport,
                    "proxy": True
                }
            }

        # Build intent policy
        full_intent_policy = {
            "provided_capabilities": [{
                "type": "tools",
                "tools": tool_names,
                "description": f"Proxied tools from {self.upstream_url} via {self._transport}"
            }],
            "description": f"SecureMCPProxy: {self.app_name} [{self._transport}] -> {self.upstream_url}",
            **self.intent_policy
        }

        # Create MACAWClient
        self.macaw_client = MACAWClient(
            app_name=self.app_name,
            app_version="1.0.0",
            iam_token=iam_token,
            user_name=user_name,
            intent_policy=full_intent_policy,
            tools=tools_config
        )

        # Register with LocalAgent
        if not self.macaw_client.register():
            raise RuntimeError("Failed to register with MACAW LocalAgent")

        self.agent_id = self.macaw_client.agent_id
        self.server_id = self.agent_id  # Alias for consistency with other adapters

        logger.info(f"SecureMCPProxy registered: {self.agent_id}")
        logger.info(f"  Tools: {list(self.tool_schemas.keys())}")

    def _make_proxy_handler(self, tool_name: str):
        """Create a handler that proxies calls to upstream MCP server."""
        def handler(params: Dict[str, Any]) -> Any:
            # This executes AFTER MACAWClient enforces policy
            # MACAW has already created AuthenticatedContext for this call
            if self._transport == "stdio":
                result = asyncio.run(self._call_upstream_stdio(tool_name, params))
            else:
                result = asyncio.run(self._call_upstream_http(tool_name, params))

            # Wrap result in dict format expected by MACAWClient
            if not isinstance(result, dict):
                result = {"result": result}
            return result
        return handler

    async def _call_upstream_http(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Call a tool on the upstream MCP server via HTTP."""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:
            raise ImportError("MCP client not available")

        http_client = self._create_http_client()

        try:
            async with streamable_http_client(
                self.upstream_url,
                http_client=http_client
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, params)
                    return self._extract_result(result)

        finally:
            if http_client:
                await http_client.aclose()

    async def _call_upstream_stdio(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Call a tool on the upstream MCP server via stdio subprocess."""
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client, StdioServerParameters
        except ImportError:
            raise ImportError("MCP client not available")

        params_obj = StdioServerParameters(
            command=self._stdio_command[0],
            args=self._stdio_command[1:] if len(self._stdio_command) > 1 else [],
            env=self._stdio_env or None
        )

        async with stdio_client(params_obj) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, params)
                return self._extract_result(result)

    def _extract_result(self, result: Any) -> Any:
        """Extract content from MCP result format."""
        if hasattr(result, 'content'):
            # Handle MCP result format
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    return content.text
                return content
            return result.content
        return result

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def call_tool(self, tool_name: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Call a tool through MACAW security.

        Flow:
        1. MACAWClient.invoke_tool() checks MAPL policy
        2. Signs the invocation
        3. Logs to audit
        4. Proxy handler forwards to upstream MCP server

        Args:
            tool_name: Name of the tool (e.g., "query_accounts")
            params: Tool parameters

        Returns:
            Tool execution result from upstream

        Raises:
            PermissionError: If policy denies access
            ConnectionError: If upstream is unreachable
        """
        if tool_name not in self.tool_schemas:
            available = list(self.tool_schemas.keys())
            raise ValueError(f"Unknown tool: {tool_name}. Available: {available}")

        # Use MAPL-compliant name: tool:{app_name}/{tool_name}
        mapl_name = f"tool:{self.app_name}/{tool_name}"

        # Invoke through MACAW (goes through PEP)
        return self.macaw_client.invoke_tool(
            tool_name=mapl_name,
            parameters=params or {},
            target_agent=self.agent_id
        )

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools from upstream MCP server.

        Returns:
            List of tool schemas with name, description, and input schema
        """
        return list(self.tool_schemas.values())

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get schema for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool schema or None if not found
        """
        return self.tool_schemas.get(tool_name)

    def bind_to_user(self, user_client) -> "BoundMCPProxy":
        """
        Bind proxy to a specific user's identity.

        For multi-tenant SaaS apps where the service maintains the upstream
        connection but each request runs with user's identity and policy.

        Args:
            user_client: MACAWClient instance with user's identity

        Returns:
            BoundMCPProxy that routes calls through user's identity

        Example:
            # Service creates proxy once
            proxy = SecureMCPProxy(app_name="salesforce", ...)

            # Per-request: bind to user
            user_proxy = proxy.bind_to_user(user_macaw_client)
            result = user_proxy.call_tool("query", {...})  # Alice's policy applies
        """
        return BoundMCPProxy(self, user_client)

    def refresh_tools(self):
        """
        Re-discover tools from upstream MCP server.

        Call this if upstream server's tools may have changed.
        """
        old_tools = set(self.tool_schemas.keys())
        self._connect_and_discover()
        new_tools = set(self.tool_schemas.keys())

        added = new_tools - old_tools
        removed = old_tools - new_tools

        if added:
            logger.info(f"New tools discovered: {added}")
            # Register new tools with MACAWClient
            for name in added:
                schema = self.tool_schemas[name]
                self.macaw_client.register_tool(
                    name,
                    handler=self._make_proxy_handler(name),
                    metadata={"schema": schema.get("schema", {})}
                )

        if removed:
            logger.info(f"Tools no longer available: {removed}")

    @property
    def is_connected(self) -> bool:
        """Check if connected to upstream MCP server."""
        return self._connected

    def __repr__(self) -> str:
        tool_count = len(self.tool_schemas)
        transport = self._transport.upper()
        return f"<SecureMCPProxy {self.app_name} [{transport}] -> {self.upstream_url} ({tool_count} tools)>"


class BoundMCPProxy:
    """
    MCP Proxy bound to a specific user's identity.

    All tool calls route through the user's MACAWClient,
    applying their policies and logging under their identity.
    """

    def __init__(self, proxy: SecureMCPProxy, user_client):
        """
        Initialize bound proxy.

        Args:
            proxy: The SecureMCPProxy instance
            user_client: MACAWClient with user's identity
        """
        self.proxy = proxy
        self.user_client = user_client

    def call_tool(self, tool_name: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Call a tool with user's identity and policy context.

        Args:
            tool_name: Name of the tool
            params: Tool parameters

        Returns:
            Tool execution result
        """
        if tool_name not in self.proxy.tool_schemas:
            available = list(self.proxy.tool_schemas.keys())
            raise ValueError(f"Unknown tool: {tool_name}. Available: {available}")

        # Use MAPL-compliant name: tool:{app_name}/{tool_name}
        mapl_name = f"tool:{self.proxy.app_name}/{tool_name}"

        # Invoke through user's MACAWClient (their policy applies)
        return self.user_client.invoke_tool(
            tool_name=mapl_name,
            parameters=params or {},
            target_agent=self.proxy.agent_id
        )

    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools."""
        return self.proxy.list_tools()

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool."""
        return self.proxy.get_tool_schema(tool_name)

    def __repr__(self) -> str:
        user_id = getattr(self.user_client, 'agent_id', 'unknown')
        return f"<BoundMCPProxy {self.proxy.app_name} as {user_id}>"
