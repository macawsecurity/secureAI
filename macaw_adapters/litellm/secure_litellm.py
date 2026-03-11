#!/usr/bin/env python3
"""
SecureLiteLLM - MACAW-protected LiteLLM wrapper.

Drop-in replacement for litellm with MACAW security.
Supports 100+ LLM providers through LiteLLM's unified interface.
Uses MAPL-compliant tool names: tool:<app_name>/generate, tool:<app_name>/complete, etc.

Supports three usage paths:
1. Direct on service: client.chat.completions.create() - simplest, app-level identity
2. bind_to_user: service.bind_to_user(user_client) - per-user identity for SaaS
3. invoke_tool: user.invoke_tool("tool:xxx/generate", ...) - explicit A2A control

Architecture (service mode):
- macaw_client: Primary client owning LLM operations (tool:{app_name}/generate, etc.)
- _tools_client: Internal client owning user-registered tools (tool:{app_name}/*, not externally reachable)
- server_id: Points to macaw_client (the primary interface)
- Tool isolation: Only macaw_client can invoke tools on _tools_client

Install with: pip install -e /path/to/secureAI[litellm]
"""

import os
import json
import logging
import inspect
from typing import Dict, Any, Optional, Callable, List

import litellm
from macaw_client import MACAWClient

logger = logging.getLogger(__name__)

# MAPL-compliant resource naming: tool:<service>/<operation>
TOOL_OPERATIONS = {
    "generate": "generate",
    "complete": "complete",
    "embed": "embed"
}


class SecureLiteLLM:
    """
    Drop-in replacement for litellm with MACAW security.

    This version uses a two-client architecture for tool isolation:
    - macaw_client: Primary, owns LLM operations (tool:{app_name}/generate, etc.)
    - _tools_client: Internal, owns user-registered tools (not externally reachable)

    server_id points to macaw_client, making it the primary external interface.
    Tools are isolated: only macaw_client can invoke tools on _tools_client.

    Supports two modes:
    1. Service mode (default): Creates both clients, handles LLM calls
    2. User mode (jwt_token provided): Creates user agent with identity for direct calls

    For multi-user scenarios, use service mode + bind_to_user() to create per-user wrappers.
    """

    def __init__(
        self,
        app_name: str = None,
        api_base: str = None,
        api_key: str = None,
        intent_policy: Optional[Dict[str, Any]] = None,
        # User mode parameters
        jwt_token: str = None,
        user_name: str = None
    ):
        """
        Initialize SecureLiteLLM wrapper.

        Args:
            app_name: Application name for registration (default: macaw-litellm)
            api_base: Optional custom API endpoint (for vLLM, Ollama, etc.)
            api_key: Optional API key (LiteLLM uses env vars per provider by default)
            intent_policy: Application-defined MACAW intent policy
            jwt_token: If provided, creates user agent with this identity (user mode)
            user_name: Optional user name for user mode
        """
        # Store LiteLLM config
        self.api_base = api_base
        self.api_key = api_key

        # Application identity
        self.app_name = app_name or "macaw-litellm"

        # Determine mode based on jwt_token
        self._mode = "user" if jwt_token else "service"
        self._jwt_token = jwt_token
        self._user_name = user_name

        # User-registered tools (LLM can call these)
        self.user_tools = {}

        # Auto-discovered tools cache
        self._discovered_tools = {}
        self._tools_registered = False

        # Application-provided intent policy (no defaults!)
        self.intent_policy = intent_policy or {}

        if self._mode == "service":
            # SERVICE MODE: Two-client architecture for tool isolation
            # - macaw_client: Primary, owns LLM operations (externally reachable)
            # - _tools_client: Internal, owns user tools (not externally reachable)

            # Tools client name (same as app_name for cleaner policy names)
            self._tools_name = self.app_name

            # LLM tools on the primary client
            llm_tools = {
                f"tool:{self.app_name}/generate": {
                    "handler": self._handle_generate,
                    "prompts": ["messages"]
                },
                f"tool:{self.app_name}/complete": {
                    "handler": self._handle_complete,
                    "prompts": ["prompt"]
                },
                f"tool:{self.app_name}/embed": {
                    "handler": self._handle_embed,
                    "prompts": ["input"]
                }
            }

            # Primary client - owns LLM operations, externally reachable via server_id
            self.macaw_client = MACAWClient(
                app_name=self.app_name,
                app_version="1.0.0",
                intent_policy=self.intent_policy,
                tools=llm_tools
            )

            # Internal tools client - owns user-registered tools, NOT externally reachable
            self._tools_client = MACAWClient(
                app_name=self._tools_name,
                app_version="1.0.0",
                intent_policy=self.intent_policy,
                tools={}  # User tools added via register_tool
            )
        else:
            # USER MODE: Create user agent with identity
            self._tools_name = None
            self._tools_client = None

            self.macaw_client = MACAWClient(
                user_name=user_name,
                iam_token=jwt_token,
                agent_type="user",
                app_name=self.app_name,
                app_version="1.0.0",
                intent_policy=self.intent_policy or {
                    "purpose": f"LiteLLM access for {user_name or 'user'}"
                }
            )

        # Register with LocalAgent and get server ID(s)
        if self._mode == "service":
            # Register both clients
            if self.macaw_client.register() and self._tools_client.register():
                self.server_id = self.macaw_client.agent_id  # Primary interface!
                self._tools_server_id = self._tools_client.agent_id  # Internal, not exposed
                logger.info(f"SecureLiteLLM registered (two-client mode):")
                logger.info(f"   Primary (LLM): {self.server_id}")
                logger.info(f"   Internal (tools): {self._tools_server_id}")
            else:
                raise RuntimeError("Failed to register with MACAW LocalAgent")
        else:
            # User mode - single client
            if self.macaw_client.register():
                self.server_id = self.macaw_client.agent_id
                logger.info(f"SecureLiteLLM registered as: {self.server_id} (mode: {self._mode})")
            else:
                raise RuntimeError("Failed to register with MACAW LocalAgent")

        # Mimic OpenAI API structure for compatibility
        self.chat = self._ChatNamespace(self)
        self.completions = self._CompletionsNamespace(self)
        self.embeddings = self._EmbeddingsNamespace(self)

    def completion(self, model: str, messages: List[Dict], **kwargs):
        """
        Direct completion call - convenience method.

        This is the primary interface matching litellm.completion().
        """
        return self.chat.completions.create(model=model, messages=messages, **kwargs)

    def bind_to_user(self, user_client: 'MACAWClient') -> 'BoundSecureLiteLLM':
        """
        Bind this SecureLiteLLM service to a user's MACAW client.

        Creates a lightweight wrapper that routes calls through the user's
        client to this service, enabling per-user identity and policy enforcement.

        Only valid in service mode.

        Args:
            user_client: A registered MACAWClient with user identity

        Returns:
            BoundSecureLiteLLM wrapper for this user

        Raises:
            ValueError: If service not in service mode or client validation fails
        """
        if self._mode != "service":
            raise ValueError("bind_to_user() only valid for service-mode SecureLiteLLM")

        # Validate user_client is a MACAWClient instance
        if not hasattr(user_client, 'agent_id') or not hasattr(user_client, 'invoke_tool'):
            raise ValueError("bind_to_user() requires a valid MACAWClient instance")

        # Validate user_client is registered
        if not getattr(user_client, 'registered', False):
            raise ValueError("bind_to_user() requires a registered MACAWClient. Call register() first.")

        # Validate agent_type is "user" (warning only, not blocking)
        agent_type = getattr(user_client, 'agent_type', None)
        if agent_type and agent_type != "user":
            logger.warning(f"bind_to_user() called with agent_type='{agent_type}' (expected 'user'). "
                          f"User identity and policy enforcement may not work as expected.")

        return BoundSecureLiteLLM(self, user_client)

    def register_tool(self, name: str, handler: Callable) -> 'SecureLiteLLM':
        """
        Register a tool that the LLM can call.

        Tools are registered on _tools_client (internal, not externally reachable).
        This provides tool isolation - only the LLM can invoke these tools.

        Args:
            name: Tool name (must match function name in tools list)
            handler: Function to handle tool execution

        Returns:
            Self for chaining
        """
        # Store with MAPL-compliant name using tools client's app_name
        mapl_name = f"tool:{self._tools_name}/{name}"

        # Wrap handler to accept params dict and unpack as kwargs
        def wrapped_handler(params):
            return handler(**params)

        self.user_tools[name] = wrapped_handler  # Store by simple name for lookup
        self.user_tools[mapl_name] = wrapped_handler  # Also store by MAPL name

        # Register with _tools_client (internal) using MAPL name
        self._tools_client.register_tool(mapl_name, wrapped_handler)

        logger.info(f"Registered tool: {name} -> {mapl_name}")
        return self

    def _auto_discover_tools(self, tools_metadata):
        """
        Auto-discover tool implementations from caller's context.

        Args:
            tools_metadata: List of tool definitions from LLM call
        """
        if self._tools_registered:
            return  # Already discovered

        # Get caller's frame
        frame = inspect.currentframe()
        caller_frame = frame.f_back.f_back.f_back
        if not caller_frame:
            logger.warning("Could not access caller frame for auto-discovery")
            return

        caller_globals = caller_frame.f_globals
        caller_locals = caller_frame.f_locals

        # Combine locals and globals for search
        search_scope = {**caller_globals, **caller_locals}

        # Discover implementations for each tool
        for tool_def in tools_metadata:
            if isinstance(tool_def, dict) and tool_def.get("type") == "function":
                func_def = tool_def.get("function", {})
                func_name = func_def.get("name")

                mapl_name = f"tool:{self._tools_name}/{func_name}"
                if func_name and func_name not in self.user_tools:
                    if func_name in search_scope:
                        func = search_scope[func_name]
                        if callable(func):
                            logger.info(f"Auto-discovered tool: {func_name} -> {mapl_name}")
                            self._discovered_tools[func_name] = func
                            self.user_tools[func_name] = func
                            self.user_tools[mapl_name] = func
                    else:
                        logger.warning(f"Tool '{func_name}' not found in caller's scope")

        # Sync all discovered tools with _tools_client (internal)
        if self._discovered_tools:
            for func_name, func in self._discovered_tools.items():
                mapl_name = f"tool:{self._tools_name}/{func_name}"
                def create_handler(tool_func):
                    def handler(params):
                        return tool_func(**params)
                    return handler
                self._tools_client.register_tool(mapl_name, create_handler(func))
            self._tools_registered = True
            logger.info(f"Auto-registered {len(self._discovered_tools)} tools with _tools_client")

    def _call_litellm(self, **params):
        """
        Call LiteLLM with configured api_base and api_key.
        """
        # Add api_base and api_key if configured
        if self.api_base:
            params['api_base'] = self.api_base
        if self.api_key:
            params['api_key'] = self.api_key

        return litellm.completion(**params)

    def _handle_generate(self, params: Dict[str, Any]):
        """
        Handle 'generate' tool (chat completions).

        This runs on macaw_client. Tool callbacks route to _tools_client (internal).
        Returns a serializable dict for MACAW protocol, or an iterator for streaming.
        """
        try:
            # Check if streaming is requested
            is_streaming = params.get('stream', False)

            if is_streaming:
                return self._stream_generate(params)

            # Non-streaming mode
            response = self._call_litellm(**params)

            # Check if LLM wants to call tools
            if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
                tool_calls = response.choices[0].message.tool_calls
                logger.info(f"LLM requested {len(tool_calls)} tool calls")

                # Process each tool call
                tool_results = []
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    mapl_name = f"tool:{self._tools_name}/{func_name}"

                    logger.info(f"Processing tool call: {func_name} -> {mapl_name}")

                    if func_name not in self.user_tools and mapl_name not in self.user_tools:
                        result = {
                            'error': f"Tool not found: {mapl_name}",
                            'available_tools': list(self.user_tools.keys())
                        }
                    else:
                        try:
                            result = self.macaw_client.invoke_tool(
                                tool_name=mapl_name,
                                parameters=func_args,
                                target_agent=self._tools_server_id
                            )
                            logger.info(f"Tool {func_name} executed successfully via _tools_client")
                        except Exception as e:
                            error_msg = str(e)
                            if 'denied' in error_msg.lower() or 'policy' in error_msg.lower():
                                logger.warning(f"MACAW blocked tool {func_name}: {error_msg}")
                                result = {
                                    'error': 'Access denied by security policy',
                                    'tool': func_name,
                                    'reason': 'Policy violation'
                                }
                            else:
                                result = {'error': str(e)}

                    tool_results.append({
                        'tool_call_id': tool_call.id,
                        'result': result
                    })

                # Add tool results to conversation
                messages = list(params.get('messages', []))

                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in tool_calls]
                })

                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result['tool_call_id'],
                        "content": json.dumps(result['result'])
                    })

                # Continue conversation with tool results
                final_params = params.copy()
                final_params['messages'] = messages

                if 'tools' in final_params:
                    del final_params['tools']
                if 'tool_choice' in final_params:
                    del final_params['tool_choice']

                final_response = self._call_litellm(**final_params)
                return final_response.model_dump()

            return response.model_dump()

        except Exception as e:
            logger.error(f"Error in generate handler: {e}")
            return {'error': str(e)}

    def _stream_generate(self, params: Dict[str, Any]):
        """
        Handle streaming chat completions.
        """
        try:
            # Add api_base and api_key if configured
            if self.api_base:
                params['api_base'] = self.api_base
            if self.api_key:
                params['api_key'] = self.api_key

            stream = litellm.completion(**params)

            for chunk in stream:
                yield chunk.model_dump()

        except Exception as e:
            logger.error(f"Error in streaming generate: {e}")
            yield {'error': str(e)}

    def _handle_complete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'complete' tool (text completions).
        """
        try:
            if self.api_base:
                params['api_base'] = self.api_base
            if self.api_key:
                params['api_key'] = self.api_key

            response = litellm.text_completion(**params)
            return response.model_dump()
        except Exception as e:
            logger.error(f"Error in complete handler: {e}")
            return {'error': str(e)}

    def _handle_embed(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'embed' tool (embeddings).
        """
        try:
            if self.api_base:
                params['api_base'] = self.api_base
            if self.api_key:
                params['api_key'] = self.api_key

            response = litellm.embedding(**params)
            return response.model_dump()
        except Exception as e:
            logger.error(f"Error in embed handler: {e}")
            return {'error': str(e)}

    # Namespace classes to mimic OpenAI API structure
    class _ChatNamespace:
        def __init__(self, parent):
            self.parent = parent
            self.completions = self._Completions(parent)

        class _Completions:
            def __init__(self, parent):
                self.parent = parent

            def create(self, **kwargs):
                """
                Create chat completion - routes through MACAW.
                """
                tools = kwargs.get('tools', kwargs.get('functions'))
                if tools:
                    self.parent._auto_discover_tools(tools)

                tool_name = f"tool:{self.parent.app_name}/generate"
                is_streaming = kwargs.get('stream', False)

                result = self.parent.macaw_client.invoke_tool(
                    tool_name=tool_name,
                    parameters=kwargs,
                    target_agent=self.parent.server_id,
                    stream=is_streaming
                )

                if is_streaming:
                    return self._wrap_streaming_response(result)

                if isinstance(result, dict) and 'error' in result:
                    raise Exception(f"MACAW error: {result['error']}")

                # Return as ModelResponse (LiteLLM's response type)
                from litellm import ModelResponse
                return ModelResponse(**result)

            def _wrap_streaming_response(self, iterator):
                """Wrap streaming chunks."""
                for chunk in iterator:
                    if isinstance(chunk, dict):
                        if 'error' in chunk:
                            raise Exception(f"MACAW streaming error: {chunk['error']}")
                        yield chunk
                    else:
                        yield chunk

    class _CompletionsNamespace:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            """Create text completion - routes through MACAW."""
            tool_name = f"tool:{self.parent.app_name}/complete"

            result = self.parent.macaw_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.parent.server_id
            )

            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            from litellm import TextCompletionResponse
            return TextCompletionResponse(**result)

    class _EmbeddingsNamespace:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            """Create embeddings - routes through MACAW."""
            tool_name = f"tool:{self.parent.app_name}/embed"

            result = self.parent.macaw_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.parent.server_id
            )

            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            from litellm import EmbeddingResponse
            return EmbeddingResponse(**result)


class BoundSecureLiteLLM:
    """
    Per-user wrapper for SecureLiteLLM service.

    Created via SecureLiteLLM.bind_to_user(user_client).
    Routes all calls through the user's MACAWClient to the service's LLM client,
    enabling per-user identity and policy enforcement.
    """

    def __init__(self, service: SecureLiteLLM, user_client: 'MACAWClient'):
        self._service = service
        self._user_client = user_client
        self._bound = True

        self.chat = self._ChatNamespace(self)
        self.completions = self._CompletionsNamespace(self)
        self.embeddings = self._EmbeddingsNamespace(self)

    @property
    def service(self) -> SecureLiteLLM:
        if not self._bound:
            raise RuntimeError("BoundSecureLiteLLM has been unbound.")
        return self._service

    @property
    def user_client(self) -> 'MACAWClient':
        if not self._bound:
            raise RuntimeError("BoundSecureLiteLLM has been unbound.")
        return self._user_client

    def completion(self, model: str, messages: List[Dict], **kwargs):
        """Direct completion call - convenience method."""
        return self.chat.completions.create(model=model, messages=messages, **kwargs)

    def unbind(self):
        """Unbind this wrapper, invalidating all future calls."""
        if not self._bound:
            return
        logger.info(f"Unbinding SecureLiteLLM from user {self._user_client.agent_id}")
        self._bound = False
        self._service = None
        self._user_client = None

    @property
    def is_bound(self) -> bool:
        return self._bound

    class _ChatNamespace:
        def __init__(self, bound: 'BoundSecureLiteLLM'):
            self.bound = bound
            self.completions = self._Completions(bound)

        class _Completions:
            def __init__(self, bound: 'BoundSecureLiteLLM'):
                self.bound = bound

            def create(self, **kwargs):
                tool_name = f"tool:{self.bound.service.app_name}/generate"
                is_streaming = kwargs.get('stream', False)

                result = self.bound.user_client.invoke_tool(
                    tool_name=tool_name,
                    parameters=kwargs,
                    target_agent=self.bound.service.server_id,
                    stream=is_streaming
                )

                if is_streaming:
                    return self._wrap_streaming_response(result)

                if isinstance(result, dict) and 'error' in result:
                    raise Exception(f"MACAW error: {result['error']}")

                from litellm import ModelResponse
                return ModelResponse(**result)

            def _wrap_streaming_response(self, iterator):
                for chunk in iterator:
                    if isinstance(chunk, dict):
                        if 'error' in chunk:
                            raise Exception(f"MACAW streaming error: {chunk['error']}")
                        yield chunk
                    else:
                        yield chunk

    class _CompletionsNamespace:
        def __init__(self, bound: 'BoundSecureLiteLLM'):
            self.bound = bound

        def create(self, **kwargs):
            tool_name = f"tool:{self.bound.service.app_name}/complete"

            result = self.bound.user_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.bound.service.server_id
            )

            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            from litellm import TextCompletionResponse
            return TextCompletionResponse(**result)

    class _EmbeddingsNamespace:
        def __init__(self, bound: 'BoundSecureLiteLLM'):
            self.bound = bound

        def create(self, **kwargs):
            tool_name = f"tool:{self.bound.service.app_name}/embed"

            result = self.bound.user_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.bound.service.server_id
            )

            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            from litellm import EmbeddingResponse
            return EmbeddingResponse(**result)
