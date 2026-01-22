"""
SecureMCP Client: Transparent security for MCP clients

Simplified Architecture:
- Automatically registers with MACAW LocalAgent via MACAWClient
- All security handled by MACAWClient -> LocalAgent -> ToolAgent
- No duplicate permission checks - trust the MACAW protocol
- Supports MCP Sampling (server->client LLM requests)
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable

logger = logging.getLogger(__name__)


class Client:
    """
    SecureMCP Client with automatic registration and security.

    All security is handled by MACAWClient -> LocalAgent -> ToolAgent.
    This is a thin wrapper providing MCP-style API over MACAWClient.
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        server_url: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize SecureMCP client.

        Args:
            name: Client name/application name
            version: Client version
            server_url: URL of the MCP server to connect to
            **kwargs: Additional configuration
        """
        self.name = name
        self.version = version
        self.server_url = server_url
        self.config = kwargs

        # Connection state
        self.connected = False
        self.default_server = None

        # Sampling handler for MCP server->client LLM requests
        self._sampling_handler: Optional[Callable] = None

        # Elicitation handler for MCP server->user input requests
        self._elicitation_handler: Optional[Callable] = None

        # Initialize MACAW client - handles all security
        self.macaw_client = None
        self._register_with_macaw()
    
    def _register_with_macaw(self):
        """Register with MACAW Local Agent via MACAWClient."""
        try:
            from macaw_client import MACAWClient

            # Create MACAWClient - it handles all security
            self.macaw_client = MACAWClient(
                app_name=f"securemcp-client-{self.name}",
                app_version=self.version,
                intent_policy={
                    "required_resources": [
                        {
                            "resource": "tool/*",
                            "operations": ["invoke"],
                            "justification": f"SecureMCP client {self.name} needs to invoke tools"
                        }
                    ],
                    "data_access": ["none"],
                    "description": f"SecureMCP client: {self.name}"
                }
            )

            # Register with Local Agent
            if self.macaw_client.register():
                logger.info(f"✅ Client registered: {self.macaw_client.agent_id}")
                logger.info("All security handled by MACAWClient -> LocalAgent")
            else:
                raise RuntimeError("Failed to register with MACAW Local Agent")

        except ImportError as e:
            raise RuntimeError(f"MACAWClient not available: {e}")
        except Exception as e:
            raise RuntimeError(f"MACAW registration failed: {e}")
    
    async def connect(self, server_url: Optional[str] = None, transport: str = "sse") -> bool:
        """
        Connect to an MCP server.

        Note: For MACAW-based routing, explicit connection is not required.
        Tools are invoked via LocalAgent routing using target_server parameter.

        Args:
            server_url: Server URL or "stdio" for STDIO transport
            transport: Transport type ("sse" or "stdio")

        Returns:
            True if connection successful
        """
        # Handle STDIO transport (direct connection without LocalAgent)
        if server_url == "stdio" or transport == "stdio":
            from .transport.stdio import StdioClient

            logger.info("Connecting via STDIO transport")
            self.stdio_client = StdioClient(self)

            try:
                capabilities = await self.stdio_client.initialize()
                self.connected = True
                logger.info(f"Connected via STDIO: {capabilities.get('serverInfo', {})}")
                return True
            except Exception as e:
                logger.error(f"STDIO connection failed: {e}")
                return False

        # For MACAW routing, we don't need explicit connection
        # Tools are invoked via LocalAgent using target_server
        if server_url:
            self.server_url = server_url
            self.set_default_server(server_url)

        self.connected = True
        logger.info("Client ready for MACAW LocalAgent routing")
        return True
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        target_server: Optional[str] = None
    ) -> Any:
        """
        Call a tool on the MCP server.

        Per MCP specification: tools are discovered and invoked within
        the context of a specific server connection. Security is handled
        by MACAWClient -> LocalAgent -> ToolAgent.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            target_server: Target server/agent (e.g., "local:mohan/app:securemcp-calc:abc123")

        Returns:
            Tool execution result
        """
        # Handle STDIO transport
        if hasattr(self, 'stdio_client'):
            return await self.stdio_client.call_tool(tool_name, arguments)

        # Determine target server
        target = target_server or self.default_server
        if not target:
            raise ValueError("target_server required (per MCP spec)")

        # Use MACAWClient for tool invocation - it handles all security
        logger.info(f"Invoking tool '{tool_name}' on '{target}'")
        result = self.macaw_client.invoke_tool(
            tool_name,
            parameters=arguments,
            target_agent=target
        )
        logger.info(f"Tool '{tool_name}' completed: {result}")
        return result
    
    async def get_resource(
        self,
        resource_uri: str,
        target_server: Optional[str] = None
    ) -> Any:
        """
        Get a resource from the MCP server (read-only tool semantics).

        Resources are registered as tools with "resource:" prefix.
        Security is handled by MACAWClient -> LocalAgent -> ToolAgent.

        Args:
            resource_uri: Resource URI (e.g., "calc://history")
            target_server: Target server providing the resource

        Returns:
            Resource content
        """
        target = target_server or self.default_server
        if not target:
            raise ValueError("target_server required for resource access")

        # Resources are registered as "resource:{uri}" tools
        return self.macaw_client.invoke_tool(
            f"resource:{resource_uri}",
            parameters={},
            target_agent=target
        )

    async def get_prompt(
        self,
        prompt_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        target_server: Optional[str] = None
    ) -> str:
        """
        Get a prompt template from the MCP server.

        Prompts are registered as tools with "prompt:" prefix.
        Use MACAWClient.create_authenticated_prompt() for secure prompts.

        Args:
            prompt_name: Name of the prompt
            arguments: Optional prompt arguments
            target_server: Target server providing the prompt

        Returns:
            Prompt template text
        """
        target = target_server or self.default_server
        if not target:
            raise ValueError("target_server required for prompt access")

        # Prompts are registered as "prompt:{name}" tools
        return self.macaw_client.invoke_tool(
            f"prompt:{prompt_name}",
            parameters=arguments or {},
            target_agent=target
        )
    
    async def list_servers(self) -> List[Dict[str, Any]]:
        """
        Discover available MCP servers registered with Local Agent.

        Returns:
            List of server information including:
            - name: Server name (e.g., "app/securemcp-calculator")
            - instance_id: Full instance ID
            - tools: List of tools provided
            - metadata: Additional server metadata
        """
        try:
            # Use public MACAWClient API for agent discovery
            agents = self.macaw_client.list_agents(agent_type="app")

            servers = []
            for agent in agents:
                agent_id = agent.get("agent_id", "")

                # Get full details to retrieve tools
                details = self.macaw_client.get_agent_info(agent_id)
                if not details:
                    continue

                tools = details.get("tools", {})
                if not tools:
                    continue  # Only include servers that provide tools

                # Tools is a dict, get the keys as tool names
                tool_list = list(tools.keys()) if isinstance(tools, dict) else tools

                server_info = {
                    "name": agent_id.split(":")[0] if ":" in agent_id else agent_id,
                    "instance_id": agent_id,
                    "tools": tool_list,
                    "metadata": details.get("metadata", {})
                }
                servers.append(server_info)

            return servers

        except Exception as e:
            logger.error(f"Error listing servers: {e}")
            return []
    
    async def list_tools(self, server_name: str = None) -> List[Dict[str, Any]]:
        """
        List tools available from a specific server or all servers.

        Tools are registered as ToolAgents with pattern: {server_id}/tool.{name}
        Filters out resources (resource:*) and prompts (prompt:*).

        Args:
            server_name: Optional server name filter (e.g., "securemcp-calculator")
                        If None, returns tools from all servers

        Returns:
            List of tool information including:
            - name: Tool name
            - description: Tool description
            - server: Server instance ID
        """
        tools = []

        # Get all app agents - tools are registered as separate ToolAgents
        agents = self.macaw_client.list_agents(agent_type="app")

        for agent in agents:
            agent_id = agent.get("agent_id", "")

            # Only look at tool agents (pattern: .../tool.{name})
            if "/tool." not in agent_id:
                continue

            # Filter by server name if specified
            if server_name and server_name not in agent_id:
                continue

            # Extract tool name from agent_id
            # Pattern: local:mohan/app:securemcp-calc:abc123/tool.add
            tool_name = agent_id.split("/tool.")[-1]

            # Skip resources and prompts
            if tool_name.startswith("resource:") or tool_name.startswith("prompt:"):
                continue

            # Extract server ID (part before /tool.)
            server_id = agent_id.rsplit("/tool.", 1)[0]

            # Get description from agent info if available
            details = self.macaw_client.get_agent_info(agent_id)
            description = ""
            if details and details.get("metadata"):
                description = details["metadata"].get("description", "")

            tool_info = {
                "name": tool_name,
                "description": description,
                "server": server_id
            }
            tools.append(tool_info)

        return tools

    async def list_resources(self, server_name: str = None) -> List[Dict[str, Any]]:
        """
        List resources available from a specific server or all servers.

        Resources are registered as ToolAgents with pattern: {server_id}/tool.resource:{uri}

        Args:
            server_name: Optional server name filter
                        If None, returns resources from all servers

        Returns:
            List of resource information including:
            - uri: Resource URI pattern
            - name: Resource name (derived from URI)
            - description: Resource description
            - server: Server instance ID
        """
        resources = []

        agents = self.macaw_client.list_agents(agent_type="app")

        for agent in agents:
            agent_id = agent.get("agent_id", "")

            # Only look at resource tool agents
            if "/tool.resource:" not in agent_id:
                continue

            if server_name and server_name not in agent_id:
                continue

            # Extract URI from agent_id
            # Pattern: .../tool.resource:calc://history
            uri = agent_id.split("/tool.resource:")[-1]
            server_id = agent_id.rsplit("/tool.resource:", 1)[0]

            # Get description from agent info if available
            details = self.macaw_client.get_agent_info(agent_id)
            description = ""
            if details and details.get("metadata"):
                description = details["metadata"].get("description", "")

            resource_info = {
                "uri": uri,
                "name": uri.split("://")[-1] if "://" in uri else uri,
                "description": description,
                "server": server_id
            }
            resources.append(resource_info)

        return resources

    async def list_prompts(self, server_name: str = None) -> List[Dict[str, Any]]:
        """
        List prompts available from a specific server or all servers.

        Prompts are registered as ToolAgents with pattern: {server_id}/tool.prompt:{name}

        Args:
            server_name: Optional server name filter
                        If None, returns prompts from all servers

        Returns:
            List of prompt information including:
            - name: Prompt name
            - description: Prompt description
            - server: Server instance ID
        """
        prompts = []

        agents = self.macaw_client.list_agents(agent_type="app")

        for agent in agents:
            agent_id = agent.get("agent_id", "")

            # Only look at prompt tool agents
            if "/tool.prompt:" not in agent_id:
                continue

            if server_name and server_name not in agent_id:
                continue

            # Extract prompt name from agent_id
            # Pattern: .../tool.prompt:calculation_prompt
            name = agent_id.split("/tool.prompt:")[-1]
            server_id = agent_id.rsplit("/tool.prompt:", 1)[0]

            # Get description from agent info if available
            details = self.macaw_client.get_agent_info(agent_id)
            description = ""
            if details and details.get("metadata"):
                description = details["metadata"].get("description", "")

            prompt_info = {
                "name": name,
                "description": description,
                "server": server_id
            }
            prompts.append(prompt_info)

        return prompts

    async def list_roots(self, server_name: str = None) -> List[Dict[str, Any]]:
        """
        List filesystem roots available from a specific server or all servers.

        Roots are declared via MAPL in the server's intent_policy.
        They define which directories a server has access to.

        Args:
            server_name: Optional server name filter
                        If None, returns roots from all servers

        Returns:
            List of root information including:
            - path: Filesystem path
            - server: Server instance ID
            - operations: Permitted operations (read, write, list)
        """
        roots = []

        agents = self.macaw_client.list_agents(agent_type="app")

        for agent in agents:
            agent_id = agent.get("agent_id", "")

            # Skip tool sub-agents
            if "/tool." in agent_id:
                continue

            if server_name and server_name not in agent_id:
                continue

            # Get server details to find roots
            details = self.macaw_client.get_agent_info(agent_id)
            if not details:
                continue

            # Roots are in intent_policy or metadata
            intent_policy = details.get("intent_policy", {})
            server_roots = intent_policy.get("roots", [])

            # Also check required_resources for file:// patterns
            for resource in intent_policy.get("required_resources", []):
                resource_pattern = resource.get("resource", "")
                if resource_pattern.startswith("file://"):
                    # Extract path from file://path/*
                    path = resource_pattern[7:]  # Remove "file://"
                    if path.endswith("/*"):
                        path = path[:-2]  # Remove "/*"
                    if path not in server_roots:
                        server_roots.append(path)

            for root_path in server_roots:
                root_info = {
                    "path": root_path,
                    "server": agent_id,
                    "operations": ["read", "write", "list"]  # Default operations
                }
                roots.append(root_info)

        return roots

    def set_default_server(self, server_name: str) -> None:
        """
        Set the default server for tool invocations.

        This allows calling tools without specifying target_server each time.

        Args:
            server_name: Server name (e.g., "app/securemcp-calculator")
        """
        self.default_server = server_name
        logger.info(f"Set default server to: {server_name}")

    def set_sampling_handler(
        self,
        handler: Callable[[str, Optional[str], int, float, Dict[str, Any]], str]
    ) -> None:
        """
        Set the handler for MCP Sampling requests (server->client LLM).

        When a server tool calls ctx.sample(), this handler is invoked to
        perform the LLM completion. This enables servers to leverage the
        client's LLM capabilities.

        Args:
            handler: Async or sync function that performs LLM completion.
                    Signature: (prompt, system_prompt, max_tokens, temperature, **kwargs) -> str

        Example:
            async def my_llm_handler(prompt, system_prompt, max_tokens, temperature, **kwargs):
                # Use your preferred LLM (OpenAI, Anthropic, etc.)
                response = await openai.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": system_prompt or "You are helpful."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return response.choices[0].message.content

            client.set_sampling_handler(my_llm_handler)
        """
        self._sampling_handler = handler

        # Register _mcp_sample tool to handle sampling requests from servers
        def sample_tool_handler(params: Dict[str, Any]) -> Dict[str, Any]:
            if not self._sampling_handler:
                return {"error": "No sampling handler configured"}

            prompt = params.get("prompt", "")
            system_prompt = params.get("system_prompt")
            max_tokens = params.get("max_tokens", 1000)
            temperature = params.get("temperature", 0.7)

            # Remove known params, pass rest as kwargs
            known_params = {"prompt", "system_prompt", "max_tokens", "temperature",
                          "request_id", "source_tool"}
            extra_kwargs = {k: v for k, v in params.items() if k not in known_params}

            try:
                result = self._sampling_handler(
                    prompt, system_prompt, max_tokens, temperature, **extra_kwargs
                )

                # Handle async handlers
                if asyncio.iscoroutine(result):
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            result = pool.submit(asyncio.run, result).result()
                    else:
                        result = loop.run_until_complete(result)

                return {"response": result}

            except Exception as e:
                logger.error(f"Sampling handler error: {e}")
                return {"error": str(e)}

        # Register the sampling tool with MACAWClient using public API
        if self.macaw_client:
            self.macaw_client.register_tool("_mcp_sample", sample_tool_handler)
            logger.info("Sampling handler registered - servers can now use ctx.sample()")

    def set_elicitation_handler(
        self,
        handler: Callable[[str, Optional[List[str]], str, Optional[str], bool, Dict[str, Any]], Any]
    ) -> None:
        """
        Set the handler for MCP Elicitation requests (server->user input).

        When a server tool calls ctx.elicit(), this handler is invoked to
        prompt the user and return their input.

        Args:
            handler: Function that prompts the user and returns their input.
                    Signature: (prompt, options, input_type, default, required, **kwargs) -> Any

        Example:
            def my_input_handler(prompt, options, input_type, default, required, **kwargs):
                if input_type == "confirm":
                    response = input(f"{prompt} (y/n): ")
                    return response.lower() in ("y", "yes")
                elif input_type == "select" and options:
                    print(prompt)
                    for i, opt in enumerate(options):
                        print(f"  {i+1}. {opt}")
                    choice = int(input("Enter number: ")) - 1
                    return options[choice]
                else:
                    return input(f"{prompt}: ") or default

            client.set_elicitation_handler(my_input_handler)
        """
        self._elicitation_handler = handler

        # Register _mcp_elicit tool to handle elicitation requests from servers
        def elicit_tool_handler(params: Dict[str, Any]) -> Dict[str, Any]:
            if not self._elicitation_handler:
                return {"error": "No elicitation handler configured"}

            prompt = params.get("prompt", "")
            options = params.get("options")
            input_type = params.get("input_type", "text")
            default = params.get("default")
            required = params.get("required", True)

            # Remove known params, pass rest as kwargs
            known_params = {"prompt", "options", "input_type", "default", "required",
                          "request_id", "source_tool"}
            extra_kwargs = {k: v for k, v in params.items() if k not in known_params}

            try:
                result = self._elicitation_handler(
                    prompt, options, input_type, default, required, **extra_kwargs
                )

                # Handle async handlers
                if asyncio.iscoroutine(result):
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            result = pool.submit(asyncio.run, result).result()
                    else:
                        result = loop.run_until_complete(result)

                return {"response": result}

            except Exception as e:
                logger.error(f"Elicitation handler error: {e}")
                return {"error": str(e)}

        # Register the elicitation tool with MACAWClient using public API
        if self.macaw_client:
            self.macaw_client.register_tool("_mcp_elicit", elicit_tool_handler)
            logger.info("Elicitation handler registered - servers can now use ctx.elicit()")
    
    async def disconnect(self):
        """Disconnect from the MCP server"""
        if self.macaw_client:
            try:
                self.macaw_client.unregister()
                logger.info("Disconnected from MACAW Local Agent")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
        self.connected = False

    def get_identity(self) -> Dict[str, Any]:
        """Get the client's identity information from MACAWClient."""
        if self.macaw_client:
            return {
                'client_id': self.macaw_client.agent_id,
                'public_key': self.macaw_client.public_key.hex() if self.macaw_client.public_key else None,
                'metadata': {'name': self.name, 'version': self.version}
            }
        return {'client_id': 'unknown', 'metadata': {'error': 'Not registered'}}

    @property
    def is_secure(self) -> bool:
        """Check if client has security features enabled"""
        return self.macaw_client is not None

    @property
    def client_id(self) -> str:
        """Get the client's unique ID from MACAWClient"""
        return self.macaw_client.agent_id if self.macaw_client else "unknown"

    def __repr__(self) -> str:
        """String representation"""
        status = "secure" if self.is_secure else "not-registered"
        return f"<SecureMCPClient {self.name} ({self.client_id}) [{status}]>"


# Convenience function for creating clients
def create_client(
    name: str,
    server_url: Optional[str] = None,
    **kwargs
) -> Client:
    """
    Create a SecureMCP client with automatic registration.
    
    This is the recommended way to create clients as it ensures
    proper registration and setup.
    
    Args:
        name: Client name
        server_url: Optional server URL
        **kwargs: Additional configuration
        
    Returns:
        Configured Client instance
    """
    return Client(name=name, server_url=server_url, **kwargs)