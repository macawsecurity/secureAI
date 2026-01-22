"""
MACAW SecureMCP - FastMCP-compatible API with MACAW Security.

Provides the same decorator-based API as FastMCP while routing all tool
invocations through the MACAW security layer for policy enforcement,
cryptographic signing, and audit logging.

Usage:
    from macaw_adapters.mcp import SecureMCP, Context

    mcp = SecureMCP("calculator")

    @mcp.tool(description="Add two numbers")
    def add(a: float, b: float) -> float:
        return a + b

    @mcp.resource("calc://history")
    def get_history(ctx: Context) -> list:
        return ctx.get("calc_history") or []

    if __name__ == "__main__":
        mcp.run()
"""

import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Context:
    """
    Request context passed to tool handlers.

    Provides access to context vault, progress reporting, and cross-tool calls.
    Compatible with FastMCP's Context object.
    """

    request_id: str = ""
    tool_name: str = ""
    source_agent: str = ""  # Caller's agent ID (for sampling/elicitation callbacks)
    _client: Any = None  # MACAWClient reference
    _metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        """Get value from context vault."""
        if self._client:
            return self._client.context_get(key)
        return None

    def set(self, key: str, value: Any) -> None:
        """Set value in context vault."""
        if self._client:
            self._client.context_set(key, value)

    async def report_progress(self, progress: float, message: str = None) -> None:
        """
        Report execution progress (0.0 to 1.0).

        This is async to support streaming progress updates.

        Args:
            progress: Progress percentage from 0.0 to 1.0
            message: Optional progress message
        """
        if self._client:
            self._client.log_event(
                event_type="tool_progress",
                action="progress",
                target=self.tool_name,
                metadata={
                    "request_id": self.request_id,
                    "progress": progress,
                    "message": message
                }
            )

    async def read_resource(self, uri: str) -> Any:
        """
        Read another resource (for resource dependencies).

        Args:
            uri: Resource URI to read

        Returns:
            Resource content
        """
        if self._client:
            return self._client.invoke_tool(f"resource:{uri}", {})
        return None

    async def sample(
        self,
        prompt: str,
        system_prompt: str = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Request an LLM completion from the client (MCP Sampling).

        This allows server tools to leverage the client's LLM capabilities
        for AI-assisted processing within tool execution.

        Args:
            prompt: The user prompt to send to the LLM
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0-1.0)
            **kwargs: Additional LLM parameters

        Returns:
            The LLM's text response

        Example:
            summary = await ctx.sample(
                prompt=f"Summarize this text: {long_text}",
                system_prompt="You are a helpful summarization assistant.",
                max_tokens=500
            )
        """
        if not self._client:
            raise RuntimeError("No client available for sampling")

        if not self.source_agent:
            raise RuntimeError("No source_agent available - sampling requires caller context")

        # Route sampling request back to the calling client's sampling handler
        logger.info(f"[ctx.sample] Calling back to source_agent: {self.source_agent}")
        result = self._client.invoke_tool(
            "_mcp_sample",
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "request_id": self.request_id,
                "source_tool": self.tool_name,
                **kwargs
            },
            target_agent=self.source_agent  # Call back to the original caller
        )

        if isinstance(result, dict):
            return result.get("response", result.get("result", str(result)))
        return str(result)

    async def elicit(
        self,
        prompt: str,
        options: List[str] = None,
        input_type: str = "text",
        default: str = None,
        required: bool = True,
        **kwargs
    ) -> Any:
        """
        Request user input from the client (MCP Elicitation).

        This allows server tools to interactively request information
        from the user during tool execution.

        Args:
            prompt: The question or prompt to show the user
            options: List of choices for selection input
            input_type: Type of input ("text", "select", "confirm", "number")
            default: Default value if user doesn't provide input
            required: Whether input is required
            **kwargs: Additional elicitation parameters

        Returns:
            User's input (string, bool for confirm, or selected option)

        Example:
            # Simple text input
            name = await ctx.elicit("What is your name?")

            # Confirmation
            proceed = await ctx.elicit(
                "Delete this file?",
                input_type="confirm",
                default="no"
            )

            # Selection from options
            color = await ctx.elicit(
                "Choose a color:",
                options=["red", "green", "blue"],
                input_type="select"
            )
        """
        if not self._client:
            raise RuntimeError("No client available for elicitation")

        if not self.source_agent:
            raise RuntimeError("No source_agent available - elicitation requires caller context")

        # Route elicitation request back to the calling client's handler
        result = self._client.invoke_tool(
            "_mcp_elicit",
            {
                "prompt": prompt,
                "options": options,
                "input_type": input_type,
                "default": default,
                "required": required,
                "request_id": self.request_id,
                "source_tool": self.tool_name,
                **kwargs
            },
            target_agent=self.source_agent  # Call back to the original caller
        )

        if isinstance(result, dict):
            response = result.get("response", result.get("result"))

            # Convert response based on input_type
            if input_type == "confirm":
                if isinstance(response, bool):
                    return response
                return str(response).lower() in ("yes", "y", "true", "1")
            elif input_type == "number":
                try:
                    return float(response) if "." in str(response) else int(response)
                except (ValueError, TypeError):
                    return default
            return response

        return result

    # ========================================
    # Logging methods (FastMCP-compatible)
    # ========================================

    def log(self, level: str, message: str, **kwargs) -> None:
        """
        Log a message at the specified level.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            **kwargs: Additional metadata
        """
        if self._client:
            self._client.log_event(
                event_type="tool_log",
                source=self.tool_name,
                action=level,
                target=self.request_id,
                outcome="success",  # Log events are informational, always "success"
                metadata={"level": level, "message": message, **kwargs}
            )

    def debug(self, message: str, **kwargs) -> None:
        """Log a debug message."""
        self.log("debug", message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log an info message."""
        self.log("info", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log a warning message."""
        self.log("warning", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log an error message."""
        self.log("error", message, **kwargs)

    def audit(
        self,
        action: str,
        target: str = None,
        outcome: str = "success",
        **metadata
    ) -> None:
        """
        Create a cryptographically signed audit entry.

        This is a MACAW-specific feature that creates tamper-evident audit logs
        with cryptographic signatures for compliance and forensics.

        Args:
            action: The action being audited (e.g., "data_access", "approval", "modification")
            target: What the action affects (e.g., resource name, record ID)
            outcome: Result of the action ("success", "failure", "denied")
            **metadata: Additional audit metadata

        Example:
            ctx.audit("data_access", target="customer_records", outcome="success",
                      records_accessed=42, query="SELECT * FROM customers")
        """
        if self._client:
            self._client.log_event(
                event_type="audit",
                source=self.tool_name,
                action=action,
                target=target or self.tool_name,
                outcome=outcome,
                signed=True,  # Top-level param for cryptographic signing
                metadata={
                    "request_id": self.request_id,
                    **metadata
                }
            )

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get request metadata."""
        return self._metadata

    def get_roots(self) -> List[str]:
        """
        Get the list of filesystem roots this server can access.

        Returns:
            List of root paths declared for this server
        """
        return self._metadata.get('roots', [])


class SecureMCP:
    """
    FastMCP-compatible server with MACAW security.

    All tool invocations are routed through MACAWClient for:
    - Cryptographic signing
    - Policy enforcement
    - Audit logging
    - Prompt lineage tracking
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        intent_policy: Optional[Dict[str, Any]] = None,
        roots: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Initialize SecureMCP server.

        Args:
            name: Server name (used in agent_id)
            version: Server version
            intent_policy: MAPL policy declaration (resources, denied_resources, etc.)
            roots: List of filesystem paths this server can access (MCP roots)
            **kwargs: Additional MACAWClient options (iam_token, provider, etc.)

        Example:
            # Server that can only access specific directories
            mcp = SecureMCP(
                "file-manager",
                roots=["/home/user/documents", "/tmp/workspace"]
            )
        """
        self.name = name
        self.version = version
        self.extra_config = kwargs

        # Store custom intent_policy or build default
        self._custom_intent_policy = intent_policy

        # MCP Roots - directories this server can access
        self._roots: List[str] = roots or []

        # Registries for MCP components
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._resources: Dict[str, Dict[str, Any]] = {}
        self._prompts: Dict[str, Dict[str, Any]] = {}

        # MACAWClient (initialized in run())
        self._client = None
        self.agent_id = None

    @property
    def roots(self) -> List[str]:
        """Get the list of filesystem roots this server can access."""
        return self._roots

    def tool(
        self,
        name: str = None,
        description: str = None,
        prompts: List[str] = None
    ) -> Callable:
        """
        Decorator to register a tool.

        Args:
            name: Tool name (defaults to function name)
            description: Tool description (defaults to docstring)
            prompts: List of parameter names that should be treated as prompts

        Example:
            @mcp.tool(description="Add two numbers")
            def add(a: float, b: float) -> float:
                return a + b

            @mcp.tool(prompts=["query"])
            def search(query: str) -> list:
                # query will be wrapped as AuthenticatedPrompt
                return do_search(query)
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or func.__doc__ or ""

            # Check if function wants Context parameter
            sig = inspect.signature(func)
            wants_context = "ctx" in sig.parameters or "context" in sig.parameters

            # Store tool info
            self._tools[tool_name] = {
                "handler": func,
                "description": tool_desc,
                "wants_context": wants_context,
                "prompts": prompts or [],
                "parameters": self._extract_parameters(func)
            }

            logger.debug(f"Registered tool: {tool_name}")
            return func

        return decorator

    def resource(
        self,
        uri_pattern: str,
        description: str = None
    ) -> Callable:
        """
        Decorator to register a resource (read-only).

        Args:
            uri_pattern: URI pattern (e.g., "config://settings", "file://{path}")
            description: Resource description

        Example:
            @mcp.resource("config://app")
            def get_config(ctx: Context) -> dict:
                return {"theme": "dark"}
        """
        def decorator(func: Callable) -> Callable:
            self._resources[uri_pattern] = {
                "handler": func,
                "description": description or func.__doc__ or "",
                "uri_pattern": uri_pattern
            }

            logger.debug(f"Registered resource: {uri_pattern}")
            return func

        return decorator

    def prompt(
        self,
        name: str = None,
        description: str = None
    ) -> Callable:
        """
        Decorator to register a prompt template.

        Args:
            name: Prompt name (defaults to function name)
            description: Prompt description

        Example:
            @mcp.prompt(description="Generate a greeting")
            def greeting(name: str) -> str:
                return f"Hello, {name}! How can I help?"
        """
        def decorator(func: Callable) -> Callable:
            prompt_name = name or func.__name__

            self._prompts[prompt_name] = {
                "handler": func,
                "description": description or func.__doc__ or "",
                "parameters": self._extract_parameters(func)
            }

            logger.debug(f"Registered prompt: {prompt_name}")
            return func

        return decorator

    def run(self, transport: str = "stdio") -> None:
        """
        Start the MCP server.

        Args:
            transport: Transport type ("stdio" or "sse")
        """
        asyncio.run(self._run_async(transport))

    async def _run_async(self, transport: str) -> None:
        """Async server run."""
        try:
            # Initialize MACAWClient with registered tools
            self._init_macaw_client()

            logger.info(f"SecureMCP server '{self.name}' started")
            logger.info(f"  Agent ID: {self.agent_id}")
            logger.info(f"  Tools: {list(self._tools.keys())}")
            logger.info(f"  Resources: {list(self._resources.keys())}")
            logger.info(f"  Prompts: {list(self._prompts.keys())}")

            # Keep running until interrupted
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            if self._client:
                self._client.unregister()
                logger.info(f"Unregistered agent: {self.agent_id}")

    def _init_macaw_client(self) -> None:
        """Initialize MACAWClient with all registered tools."""
        try:
            from macaw_client import MACAWClient

            # Collect tool metadata
            tools_metadata = {}
            tool_handlers = {}
            tool_names = []

            for tool_name, tool_info in self._tools.items():
                tool_names.append(tool_name)
                tools_metadata[tool_name] = {
                    "description": tool_info["description"],
                    "prompts": tool_info.get("prompts", [])
                }
                # Create handler wrapper
                tool_handlers[tool_name] = self._create_handler(
                    tool_name,
                    tool_info["handler"],
                    tool_info["wants_context"]
                )

            # Register resources as tools with resource: prefix
            for uri_pattern, res_info in self._resources.items():
                res_tool_name = f"resource:{uri_pattern}"
                tool_names.append(res_tool_name)
                tools_metadata[res_tool_name] = {
                    "description": res_info["description"],
                    "read_only": True
                }
                tool_handlers[res_tool_name] = self._create_handler(
                    uri_pattern,
                    res_info["handler"],
                    True  # Resources always get context
                )

            # Register prompts as tools with prompt: prefix
            for prompt_name, prompt_info in self._prompts.items():
                prompt_tool_name = f"prompt:{prompt_name}"
                tool_names.append(prompt_tool_name)
                tools_metadata[prompt_tool_name] = {
                    "description": prompt_info["description"]
                }
                tool_handlers[prompt_tool_name] = self._create_handler(
                    prompt_name,
                    prompt_info["handler"],
                    False
                )

            # Build intent policy
            if self._custom_intent_policy:
                intent_policy = self._custom_intent_policy
            else:
                intent_policy = {
                    "provided_capabilities": [{
                        "type": "tools",
                        "tools": tool_names,
                        "description": f"Tools provided by SecureMCP server {self.name}"
                    }],
                    "required_resources": [],
                    "data_access": ["none"],
                    "description": f"SecureMCP server: {self.name}"
                }

                # Add roots as MAPL resource declarations
                if self._roots:
                    intent_policy["roots"] = self._roots
                    intent_policy["required_resources"] = [
                        {
                            "resource": f"file://{root}/*",
                            "operations": ["read", "write", "list"],
                            "justification": f"MCP root: {root}"
                        }
                        for root in self._roots
                    ]
                    intent_policy["data_access"] = ["filesystem"]

            # Create MACAWClient
            self._client = MACAWClient(
                app_name=f"securemcp-{self.name}",
                app_version=self.version,
                intent_policy=intent_policy,
                tools=tools_metadata,
                tool_handlers=tool_handlers,
                persistent_connection=True,
                **self.extra_config
            )

            # Register with Local Agent
            if not self._client.register():
                raise RuntimeError("Failed to register with MACAW Local Agent")

            self.agent_id = self._client.agent_id
            logger.info(f"Registered as agent: {self.agent_id}")

        except ImportError as e:
            raise RuntimeError(f"MACAWClient not available: {e}")
        except Exception as e:
            raise RuntimeError(f"MACAW initialization failed: {e}")

    def _create_handler(
        self,
        tool_name: str,
        func: Callable,
        wants_context: bool
    ) -> Callable:
        """Create a handler wrapper for MACAWClient."""
        def handler(params: Dict[str, Any]) -> Any:
            try:
                if wants_context:
                    # Get source_agent from MACAWClient's current request context
                    # This is set during tool execution handling
                    source_agent = ""
                    if self._client and hasattr(self._client, 'current_request_context'):
                        source_agent = self._client.current_request_context.get('source_agent', '')
                        logger.debug(f"[SecureMCP] Tool '{tool_name}' invoked by source_agent: {source_agent}")

                    # Create context for this invocation
                    # Include roots in metadata for get_roots() access
                    metadata = params.pop("_metadata", {})
                    metadata["roots"] = self._roots
                    ctx = Context(
                        request_id=params.pop("_request_id", ""),
                        tool_name=tool_name,
                        source_agent=source_agent,  # For sampling/elicitation callbacks
                        _client=self._client,
                        _metadata=metadata
                    )
                    # Check parameter name (ctx or context)
                    sig = inspect.signature(func)
                    if "ctx" in sig.parameters:
                        params["ctx"] = ctx
                    elif "context" in sig.parameters:
                        params["context"] = ctx

                # Execute handler
                result = func(**params)

                # Handle async functions
                if asyncio.iscoroutine(result):
                    # Use asyncio.run() which creates a new event loop
                    # This works in threads without an existing event loop
                    result = asyncio.run(result)

                # Wrap result in dict format expected by MACAWClient
                if not isinstance(result, dict):
                    result = {"result": result}

                return result

            except Exception as e:
                logger.error(f"Handler error for {tool_name}: {e}")
                raise

        return handler

    def _extract_parameters(self, func: Callable) -> Dict[str, Any]:
        """Extract parameter info from function signature."""
        sig = inspect.signature(func)
        params = {}

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "ctx", "context"):
                continue

            param_info = {
                "required": param.default == inspect.Parameter.empty
            }

            # Map type annotations to JSON schema types
            if param.annotation != inspect.Parameter.empty:
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    dict: "object",
                    list: "array"
                }
                param_info["type"] = type_map.get(param.annotation, "string")
            else:
                param_info["type"] = "string"

            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default

            params[param_name] = param_info

        return params

    # Convenience methods for testing
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool programmatically (for testing).

        Args:
            tool_name: Name of tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        handler = self._tools[tool_name]["handler"]
        result = handler(**arguments)

        if asyncio.iscoroutine(result):
            result = await result

        return result
