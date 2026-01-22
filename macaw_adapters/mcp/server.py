"""
SecureMCP Server: Integrated with MACAW Local Agent

This provides a developer-friendly MCP API while leveraging MACAW Local Agent's
security infrastructure. All security is delegated to MACAWClient.

Simplified Architecture:
- SecureMCP provides MCP-style decorators (@tool, @resource, @prompt)
- All security handled by MACAWClient -> LocalAgent -> ToolAgent
- No duplicate permission checks - trust the MACAW protocol
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, Callable, List
from functools import wraps

logger = logging.getLogger(__name__)


class Server:
    """
    SecureMCP Server with MACAW Local Agent integration.
    
    - Requires MACAW Local Agent running
    - All security via Unix socket to Local Agent
    - No direct MACAW SDK imports
    """
    
    def __init__(
        self, 
        name: str,
        version: str = "1.0.0",
        port: int = 8080,
        host: str = "localhost",
        **kwargs
    ):
        """
        Initialize SecureMCP server.
        
        Args:
            name: Server name
            version: Server version
            port: Port to listen on
            host: Host to bind to
            **kwargs: Additional configuration
        """
        self.name = name
        self.version = version
        self.port = port
        self.host = host
        self.config = kwargs

        # Registries for MCP components
        self.tools = {}
        self.resources = {}
        self.prompts = {}

        # MACAW client (initialized in start() after tools are registered)
        self.macaw_client = None
        self.server_id = None
    
    def _init_with_macaw(self):
        """Initialize with MACAW Local Agent using agent-per-app model."""
        try:
            from macaw_client import MACAWClient
            
            # Create this SecureMCP server's own agent with unique identity
            # Following the agent-per-app model - each service is an autonomous agent
            server_app_name = f"securemcp-{self.name}"
            
            # Collect tools metadata and handlers first
            tools_metadata = {}
            tool_handlers = {}
            tool_names = []
            
            for tool_name, tool_info in self.tools.items():
                tool_names.append(tool_name)  # Collect tool names for intent_policy
                tools_metadata[tool_name] = {
                    'description': tool_info.get('description', ''),
                    'metadata': tool_info.get('metadata', {})
                }
                
                # Create handler wrapper for this tool
                func = tool_info['function']
                def create_handler(tool_func):
                    def handler(params):
                        try:
                            if asyncio.iscoroutinefunction(tool_func):
                                # Return coroutine for async functions - MACAWClient will await it
                                return tool_func(**params)
                            else:
                                return tool_func(**params)
                        except Exception as e:
                            logger.error(f"Tool execution error in {tool_func.__name__}: {e}")
                            raise
                    return handler
                
                tool_handlers[tool_name] = create_handler(func)
            
            # Define the intent policy with the actual tools this server provides
            intent_policy = {
                "provided_capabilities": [
                    {
                        "type": "tools", 
                        "tools": tool_names,  # Populated with actual tool names
                        "description": f"Tools provided by SecureMCP server {self.name}"
                    }
                ],
                "required_resources": [],
                "data_access": ["none"],
                "description": f"SecureMCP server: {self.name}"
            }
            
            # Create MACAWClient with agent-per-app model including tools
            self.macaw_client = MACAWClient(
                app_name=server_app_name,
                app_version=self.version,
                intent_policy=intent_policy,
                tools=tools_metadata,  # Pass tools during initialization
                tool_handlers=tool_handlers,  # Pass tool handlers
                persistent_connection=True,  # Server needs persistent connection for tool execution
                service_account=self.config.get('service_account')  # Pass service account if provided
            )
            
            # Register this server's agent with the Local Agent
            success = self.macaw_client.register()
            
            if success:
                self.server_id = self.macaw_client.agent_id
                logger.info(f"✅ SecureMCP server registered as agent: {self.server_id}")
                logger.info("All security handled by MACAWClient -> LocalAgent -> ToolAgent")
            else:
                raise RuntimeError("Failed to register SecureMCP server agent with MACAW Local Agent")
                
        except ImportError as e:
            logger.error(f"MACAW Local Agent client not available: {e}")
            raise RuntimeError("MACAW Local Agent required. Ensure macaw_client is installed.")
        except ConnectionError as e:
            logger.error(f"Cannot connect to MACAW Local Agent: {e}")
            raise RuntimeError("MACAW Local Agent service not running. Start with: sudo systemctl start macaw-local")
        except Exception as e:
            logger.error(f"Error initializing with MACAW: {e}")
            raise

    # ============================================
    # Tool Registration and Execution
    # ============================================
    
    def tool(self, name: str = None, description: str = "", **kwargs):
        """
        Decorator to register a tool.

        Security is handled by MACAWClient -> LocalAgent -> ToolAgent.
        No duplicate permission checks here - trust the MACAW protocol.

        Args:
            name: Tool name (uses function name if not provided)
            description: Tool description
            **kwargs: Additional metadata
        """
        def decorator(func):
            tool_name = name or func.__name__

            # Store the tool - MACAWClient will handle security when invoked
            self.tools[tool_name] = {
                'function': func,
                'description': description or func.__doc__ or "",
                'metadata': kwargs
            }

            # Return original function - all security via MACAW protocol
            # When invoked via LocalAgent, ToolAgent.verify_and_execute() handles:
            # - Signature verification
            # - Policy enforcement
            # - Audit logging
            return func
        return decorator
    
    # ============================================
    # Resource Registration
    # ============================================
    
    def resource(self, pattern: str, description: str = "", **kwargs):
        """
        Decorator to register a resource (read-only tool semantics).

        Resources are treated as read-only tools. Security is handled by
        MACAWClient -> LocalAgent -> ToolAgent with read-only policy.

        Args:
            pattern: Resource URI pattern (e.g., "config/{name}")
            description: Resource description
            **kwargs: Additional metadata
        """
        def decorator(cls):
            # Store the resource class - treated as read-only tool
            self.resources[pattern] = {
                'class': cls,
                'description': description or cls.__doc__ or "",
                'metadata': kwargs
            }

            # Return original class - all security via MACAW protocol
            return cls
        return decorator
    
    # ============================================
    # Prompt Registration
    # ============================================
    
    def prompt(self, name: str = None, description: str = "", **kwargs):
        """
        Decorator to register a prompt template.

        Prompts are starting points for AuthenticatedPrompt creation.
        Use MACAWClient.create_authenticated_prompt() to create signed,
        policy-bound prompts for LLM invocation.

        Args:
            name: Prompt name (uses function name if not provided)
            description: Prompt description
            **kwargs: Additional metadata
        """
        def decorator(func):
            prompt_name = name or func.__name__

            # Store the prompt template
            self.prompts[prompt_name] = {
                'function': func,
                'description': description or func.__doc__ or "",
                'metadata': kwargs
            }

            # Return original function - prompt templates are just starting points
            # Security comes from AuthenticatedPrompt when actually used
            return func
        return decorator
    
    # ============================================
    # Server Lifecycle
    # ============================================
    
    async def start(self):
        """Start the SecureMCP server"""
        logger.info(f"Starting SecureMCP server '{self.name}' on {self.host}:{self.port}")

        # Initialize MACAW now that all tools are registered
        # MACAWClient handles connection - raises clear error if LocalAgent unavailable
        self._init_with_macaw()

        logger.info(f"Server '{self.name}' is ready")
        logger.info(f"  Tools: {list(self.tools.keys())}")
        logger.info(f"  Resources: {list(self.resources.keys())}")
        logger.info(f"  Prompts: {list(self.prompts.keys())}")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await self.stop()
    
    async def stop(self):
        """Stop the SecureMCP server"""
        logger.info(f"Stopping SecureMCP server '{self.name}'")

        # Unregister from Local Agent
        if self.macaw_client:
            try:
                self.macaw_client.unregister()
                logger.info(f"✅ Unregistered agent {self.server_id} from Local Agent")
            except Exception as e:
                logger.error(f"Error unregistering from Local Agent: {e}")

        logger.info(f"Server '{self.name}' stopped")
    
    def run(self):
        """Run the server (blocking)"""
        asyncio.run(self.start())
    
    # ============================================
    # Helper Methods
    # ============================================
    
    def _extract_parameters(self, func: Callable) -> Dict[str, Any]:
        """Extract parameter information from function signature"""
        import inspect
        
        sig = inspect.signature(func)
        params = {}
        
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
                
            param_info = {
                "type": "string",  # Default type
                "required": param.default == inspect.Parameter.empty
            }
            
            # Try to extract type from annotation
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == str:
                    param_info["type"] = "string"
                elif param.annotation == int:
                    param_info["type"] = "integer"
                elif param.annotation == float:
                    param_info["type"] = "number"
                elif param.annotation == bool:
                    param_info["type"] = "boolean"
                elif param.annotation == dict:
                    param_info["type"] = "object"
                elif param.annotation == list:
                    param_info["type"] = "array"
            
            params[param_name] = param_info
        
        return params