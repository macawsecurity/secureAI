"""
FastMCP Compatibility Layer for SecureMCP

Provides FastMCP-style features and API compatibility to make migration easier.
This allows developers familiar with FastMCP to use SecureMCP with minimal changes.
"""

import asyncio
import inspect
import logging
from typing import Optional, Dict, Any, Callable, Type, get_type_hints, Union
from contextlib import asynccontextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class TypeValidator:
    """
    Automatic type validation for tool parameters.
    
    FastMCP feature: Validates parameters against type hints automatically.
    """
    
    @staticmethod
    def validate_params(func: Callable, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and coerce parameters based on function type hints.
        
        Args:
            func: Function with type hints
            params: Parameters to validate
            
        Returns:
            Validated and coerced parameters
            
        Raises:
            TypeError: If validation fails
        """
        # Get type hints
        hints = get_type_hints(func)
        sig = inspect.signature(func)
        
        validated = {}
        
        for param_name, param_info in sig.parameters.items():
            if param_name == "self":
                continue
            
            # Get value from params or use default
            if param_name in params:
                value = params[param_name]
            elif param_info.default != inspect.Parameter.empty:
                value = param_info.default
            else:
                raise TypeError(f"Missing required parameter: {param_name}")
            
            # Get expected type
            if param_name in hints:
                expected_type = hints[param_name]
                
                # Handle Optional types
                if hasattr(expected_type, '__origin__') and expected_type.__origin__ is Union:
                    # This is Optional[T] or Union[T, None]
                    if value is not None:
                        # Get the non-None type
                        types = expected_type.__args__
                        expected_type = next(t for t in types if t != type(None))
                    else:
                        validated[param_name] = None
                        continue
                
                # Try to coerce type
                if not isinstance(value, expected_type):
                    try:
                        if expected_type == int:
                            value = int(value)
                        elif expected_type == float:
                            value = float(value)
                        elif expected_type == str:
                            value = str(value)
                        elif expected_type == bool:
                            value = bool(value)
                        else:
                            raise TypeError(f"Cannot coerce {value} to {expected_type}")
                    except (ValueError, TypeError) as e:
                        raise TypeError(f"Parameter {param_name}: expected {expected_type.__name__}, got {type(value).__name__}")
            
            validated[param_name] = value
        
        return validated


class FastMCPServer:
    """
    FastMCP-compatible server wrapper.
    
    Adds FastMCP-style features on top of SecureMCP Server.
    """
    
    def __init__(self, server):
        """
        Wrap a SecureMCP server with FastMCP compatibility.
        
        Args:
            server: SecureMCP Server instance
        """
        self.server = server
        self._original_tool = server.tool
        
        # Override tool decorator to add type validation
        server.tool = self.tool
        
        logger.info("FastMCP compatibility layer initialized")
    
    def tool(self, name: Optional[str] = None, description: str = ""):
        """
        Enhanced tool decorator with automatic type validation.
        
        FastMCP feature: Automatically validates types based on hints.
        """
        def decorator(func: Callable) -> Callable:
            # Get the original function for type hints
            original_func = func
            
            # Create wrapper that validates types
            def validated_wrapper(**kwargs):
                # Validate and coerce types
                validated_params = TypeValidator.validate_params(original_func, kwargs)
                
                # Call original function with validated params
                return original_func(**validated_params)
            
            # Copy metadata
            validated_wrapper.__name__ = original_func.__name__
            validated_wrapper.__doc__ = original_func.__doc__
            
            # Register with server using original decorator
            return self._original_tool(name, description)(validated_wrapper)
        
        return decorator
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool programmatically (dependency injection).
        
        FastMCP feature: Allows tools to call other tools.
        
        Args:
            tool_name: Name of tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result
        """
        if tool_name not in self.server.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool_info = self.server.tools[tool_name]
        function = tool_info["function"]
        
        # Call the tool
        result = function(**arguments)
        
        # Handle async functions
        if asyncio.iscoroutine(result):
            result = await result
        
        return result
    
    @asynccontextmanager
    async def test_client(self):
        """
        Create a test client for the server.
        
        FastMCP feature: Easy testing with context manager.
        
        Usage:
            async with server.test_client() as client:
                result = await client.call_tool("my-tool", {"arg": "value"})
        """
        from . import Client
        
        # Create a test client
        client = Client(f"test-client-{self.server.name}")
        
        # Create a mock connection (in-process)
        class TestConnection:
            def __init__(self, server):
                self.server = server
            
            async def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
                """Direct in-process tool call"""
                return await self.server.call_tool(name, args)
            
            async def get_resource(self, uri: str) -> Any:
                """Direct in-process resource read"""
                if uri in self.server.server.resources:
                    resource_info = self.server.server.resources[uri]
                    resource_class = resource_info["class"]
                    instance = resource_class(uri)
                    if hasattr(instance, 'read'):
                        return await instance.read()
                return None
            
            async def get_prompt(self, name: str, args: Dict[str, Any]) -> str:
                """Direct in-process prompt generation"""
                if name in self.server.server.prompts:
                    prompt_info = self.server.server.prompts[name]
                    function = prompt_info["function"]
                    return function(**args)
                return ""
        
        # Attach test connection to client
        test_conn = TestConnection(self)
        client.call_tool = test_conn.call_tool
        client.get_resource = test_conn.get_resource
        client.get_prompt = test_conn.get_prompt
        client.connected = True
        
        try:
            yield client
        finally:
            # Cleanup
            pass


@dataclass
class ErrorTemplate:
    """
    Standardized error response template.
    
    FastMCP feature: Consistent error formatting.
    """
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP error format"""
        result = {
            "error": {
                "code": self.code,
                "message": self.message
            }
        }
        if self.details:
            result["error"]["details"] = self.details
        return result


class Pagination:
    """
    Pagination helper for resources.
    
    FastMCP feature: Built-in pagination support.
    """
    
    @staticmethod
    def paginate(
        items: list,
        page: int = 1,
        page_size: int = 10
    ) -> Dict[str, Any]:
        """
        Paginate a list of items.
        
        Args:
            items: List to paginate
            page: Page number (1-based)
            page_size: Items per page
            
        Returns:
            Paginated response with metadata
        """
        total = len(items)
        total_pages = (total + page_size - 1) // page_size
        
        # Calculate slice
        start = (page - 1) * page_size
        end = start + page_size
        
        return {
            "items": items[start:end],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }


def add_fastmcp_compat(server):
    """
    Add FastMCP compatibility to a SecureMCP server.

    Usage:
        from macaw_adapters.mcp import Server
        from macaw_adapters.mcp.fastmcp_compat import add_fastmcp_compat

        server = Server("my-server")
        server = add_fastmcp_compat(server)

        # Now use FastMCP features
        @server.tool("typed-tool")
        def my_tool(path: str, count: int = 10):
            # Types are automatically validated!
            pass

    Args:
        server: SecureMCP Server instance
        
    Returns:
        Server with FastMCP compatibility
    """
    compat = FastMCPServer(server)
    
    # Add methods to server
    server.call_tool = compat.call_tool
    server.test_client = compat.test_client
    
    # Add helper classes
    server.ErrorTemplate = ErrorTemplate
    server.Pagination = Pagination
    
    return server


# Convenience decorators for standalone use
def typed_tool(name: Optional[str] = None, description: str = ""):
    """
    Standalone typed tool decorator.
    
    Usage:
        @typed_tool("calculate")
        def calculate(a: float, b: float) -> float:
            return a + b
    """
    def decorator(func: Callable) -> Callable:
        # Create wrapper that validates types
        def validated_wrapper(**kwargs):
            validated_params = TypeValidator.validate_params(func, kwargs)
            return func(**validated_params)
        
        validated_wrapper.__name__ = func.__name__
        validated_wrapper.__doc__ = func.__doc__
        
        return validated_wrapper
    
    return decorator