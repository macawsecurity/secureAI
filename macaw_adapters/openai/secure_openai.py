#!/usr/bin/env python3
"""
SecureOpenAI - MACAW-protected OpenAI wrapper.

Drop-in replacement for OpenAI client with MACAW security.
Uses MAPL-compliant tool names: tool:<app_name>/generate, tool:<app_name>/complete, etc.

Supports three usage paths:
1. Direct on service: client.chat.completions.create() - simplest, app-level identity
2. bind_to_user: service.bind_to_user(user_client) - per-user identity for SaaS
3. invoke_tool: user.invoke_tool("tool:xxx/generate", ...) - explicit A2A control

Install with: pip install -e /path/to/secureAI
"""

import os
import json
import logging
import inspect
from typing import Dict, Any, Optional, Callable, List

from openai import OpenAI
from macaw_client import MACAWClient

logger = logging.getLogger(__name__)

# MAPL-compliant resource naming: tool:<service>/<operation>
# Will be formatted with actual app_name at initialization
TOOL_OPERATIONS = {
    "generate": "generate",
    "complete": "complete",
    "embed": "embed"
}


class SecureOpenAI:
    """
    Drop-in replacement for OpenAI client with MACAW security.

    This NEW version uses proper resource names as tool names to match policies.

    Supports two modes:
    1. Service mode (default): Creates service agent, registers tools, handles OpenAI calls
    2. User mode (jwt_token provided): Creates user agent with identity for direct calls

    For multi-user scenarios, use service mode + bind_to_user() to create per-user wrappers.
    """

    def __init__(
        self,
        api_key: str = None,
        app_name: str = None,
        intent_policy: Optional[Dict[str, Any]] = None,
        # User mode parameters
        jwt_token: str = None,
        user_name: str = None
    ):
        """
        Initialize SecureOpenAI wrapper.

        Args:
            api_key: OpenAI API key (or from env)
            app_name: Application name for registration
            intent_policy: Application-defined MACAW intent policy
            jwt_token: If provided, creates user agent with this identity (user mode)
            user_name: Optional user name for user mode
        """
        # Get API key
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key required")

        # Real OpenAI client
        self.openai_client = OpenAI(api_key=self.api_key)

        # Application identity
        self.app_name = app_name or "secure-openai-app"

        # Determine mode based on jwt_token
        self._mode = "user" if jwt_token else "service"
        self._jwt_token = jwt_token
        self._user_name = user_name

        # User-registered tools (OpenAI can call these)
        self.user_tools = {}

        # Auto-discovered tools cache
        self._discovered_tools = {}
        self._tools_registered = False

        # Application-provided intent policy (no defaults!)
        self.intent_policy = intent_policy or {}

        if self._mode == "service":
            # SERVICE MODE: Register tools and handle OpenAI calls
            # Tools with prompts declaration - MAPL-compliant: tool:<service>/<operation>
            # Each tool declares which parameters are prompts for automatic authentication
            self.tools = {
                f"tool:{self.app_name}/generate": {
                    "handler": self._handle_generate,
                    "prompts": ["messages"]  # messages param is a prompt
                },
                f"tool:{self.app_name}/complete": {
                    "handler": self._handle_complete,
                    "prompts": ["prompt"]  # prompt param is a prompt
                },
                f"tool:{self.app_name}/embed": {
                    "handler": self._handle_embed,
                    "prompts": ["input"]  # input param is a prompt
                }
            }

            # Create MACAWClient with unified tools config
            self.macaw_client = MACAWClient(
                app_name=self.app_name,
                app_version="1.0.0",
                intent_policy=self.intent_policy,
                tools=self.tools  # Unified: {name: {handler, prompts, ...}}
            )
        else:
            # USER MODE: Create user agent with identity
            self.tools = {}

            self.macaw_client = MACAWClient(
                user_name=user_name,
                iam_token=jwt_token,
                agent_type="user",
                app_name=self.app_name,
                app_version="1.0.0",
                intent_policy=self.intent_policy or {
                    "purpose": f"OpenAI access for {user_name or 'user'}"
                }
            )

        # Register with LocalAgent and get server ID
        if self.macaw_client.register():
            self.server_id = self.macaw_client.agent_id
            logger.info(f"✅ SecureOpenAI registered as: {self.server_id} (mode: {self._mode})")
        else:
            raise RuntimeError("Failed to register with MACAW LocalAgent")

        # Mimic OpenAI API structure
        # MACAW-protected namespaces (route through PEP)
        self.chat = self._ChatNamespace(self)
        self.completions = self._CompletionsNamespace(self)
        self.embeddings = self._EmbeddingsNamespace(self)

    # =========================================================================
    # Pass-through properties for non-MACAW-protected APIs
    # These delegate directly to the underlying OpenAI client
    # =========================================================================

    @property
    def models(self):
        """
        Pass-through to OpenAI models API.

        Not MACAW-protected - provides direct access to model listing/retrieval.
        """
        return self.openai_client.models

    @property
    def images(self):
        """
        Pass-through to OpenAI images API (DALL-E).

        Not MACAW-protected - image generation uses service's API key directly.
        """
        return self.openai_client.images

    @property
    def audio(self):
        """
        Pass-through to OpenAI audio API (Whisper/TTS).

        Not MACAW-protected - audio transcription/speech uses service's API key directly.
        """
        return self.openai_client.audio

    @property
    def files(self):
        """
        Pass-through to OpenAI files API.

        Not MACAW-protected - file operations use service's API key directly.
        """
        return self.openai_client.files

    @property
    def fine_tuning(self):
        """
        Pass-through to OpenAI fine-tuning API.

        Not MACAW-protected - fine-tuning uses service's API key directly.
        """
        return self.openai_client.fine_tuning

    @property
    def moderations(self):
        """
        Pass-through to OpenAI moderations API.

        Not MACAW-protected - content moderation uses service's API key directly.
        """
        return self.openai_client.moderations

    @property
    def batches(self):
        """
        Pass-through to OpenAI batches API.

        Not MACAW-protected - batch operations use service's API key directly.
        """
        return self.openai_client.batches

    @property
    def beta(self):
        """
        Pass-through to OpenAI beta API (assistants, threads, vector stores).

        Not MACAW-protected - beta APIs use service's API key directly.
        """
        return self.openai_client.beta

    def bind_to_user(self, user_client: 'MACAWClient') -> 'BoundSecureOpenAI':
        """
        Bind this SecureOpenAI service to a user's MACAW client.

        Creates a lightweight wrapper that routes calls through the user's
        client to this service, enabling per-user identity and policy enforcement.

        Only valid in service mode.

        Security validations:
        - Service must be in service mode
        - User client must be a valid MACAWClient instance
        - User client must be registered with LocalAgent
        - User client should be a "user" type agent

        Args:
            user_client: A registered MACAWClient with user identity

        Returns:
            BoundSecureOpenAI wrapper for this user

        Raises:
            ValueError: If service not in service mode or client validation fails
        """
        if self._mode != "service":
            raise ValueError("bind_to_user() only valid for service-mode SecureOpenAI")

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

        return BoundSecureOpenAI(self, user_client)

    def register_tool(self, name: str, handler: Callable) -> 'SecureOpenAI':
        """
        Register a tool that OpenAI can call.

        Args:
            name: Tool name (must match OpenAI function name)
            handler: Function to handle tool execution

        Returns:
            Self for chaining
        """
        self.user_tools[name] = handler

        # Register with MACAWClient (public API handles sync)
        self.macaw_client.register_tool(name, handler)

        logger.info(f"Registered tool: {name}")
        return self

    def _auto_discover_tools(self, tools_metadata):
        """
        Auto-discover tool implementations from caller's context.

        Args:
            tools_metadata: List of tool definitions from OpenAI call
        """
        if self._tools_registered:
            return  # Already discovered

        # Get caller's frame (need to go back through the call stack)
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

                if func_name and func_name not in self.user_tools:
                    # Look for function in caller's scope
                    if func_name in search_scope:
                        func = search_scope[func_name]
                        if callable(func):
                            logger.info(f"Auto-discovered tool: {func_name}")
                            self._discovered_tools[func_name] = func
                            self.user_tools[func_name] = func
                    else:
                        logger.warning(f"Tool '{func_name}' not found in caller's scope")

        # Sync all discovered tools with MACAW agent
        if self._discovered_tools:
            # Register each discovered tool with MACAWClient (public API)
            for name, func in self._discovered_tools.items():
                # Create wrapper handler that accepts dict parameter
                def create_handler(tool_func):
                    def handler(params):
                        return tool_func(**params)
                    return handler
                self.macaw_client.register_tool(name, create_handler(func))
            self._tools_registered = True
            logger.info(f"Auto-registered {len(self._discovered_tools)} tools with MACAW")

    def _handle_generate(self, params: Dict[str, Any]):
        """
        Handle 'generate' tool (chat completions).

        This runs INSIDE ToolAgent, so it's already PEP-protected!
        Returns a serializable dict for MACAW protocol, or an iterator for streaming.
        """
        try:
            # Check if streaming is requested
            is_streaming = params.get('stream', False)

            if is_streaming:
                # Streaming mode: return iterator
                return self._stream_generate(params)

            # Non-streaming mode: existing behavior
            # Call real OpenAI (params are clean - no MACAW internals)
            response = self.openai_client.chat.completions.create(**params)

            # Check if OpenAI wants to call tools
            if response.choices[0].message.tool_calls:
                tool_calls = response.choices[0].message.tool_calls
                logger.info(f"OpenAI requested {len(tool_calls)} tool calls")

                # Process each tool call
                tool_results = []
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    logger.info(f"Processing tool call: {func_name}({func_args})")

                    # Check if we have this tool
                    if func_name not in self.user_tools:
                        result = {
                            'error': f"Tool not found: {func_name}",
                            'available_tools': list(self.user_tools.keys())
                        }
                    else:
                        # Invoke tool through MACAW (goes through PEP!)
                        try:
                            result = self.macaw_client.invoke_tool(
                                tool_name=func_name,
                                parameters=func_args,
                                target_agent=self.server_id  # Route to ourselves!
                            )
                            logger.info(f"Tool {func_name} executed successfully")
                        except Exception as e:
                            error_msg = str(e)
                            # Check if MACAW blocked it
                            if 'denied' in error_msg.lower() or 'policy' in error_msg.lower():
                                logger.warning(f"🛡️ MACAW blocked tool {func_name}: {error_msg}")
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

                # Add assistant message with tool calls
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

                # Add tool results
                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result['tool_call_id'],
                        "content": json.dumps(result['result'])
                    })

                # Continue conversation with tool results
                final_params = params.copy()
                final_params['messages'] = messages

                # Remove tools and tool_choice to prevent infinite recursion
                if 'tools' in final_params:
                    del final_params['tools']
                if 'tool_choice' in final_params:
                    del final_params['tool_choice']

                final_response = self.openai_client.chat.completions.create(**final_params)

                # Convert to serializable dict for MACAW protocol
                return final_response.model_dump()

            # No tool calls, convert response to dict
            return response.model_dump()

        except Exception as e:
            logger.error(f"Error in generate handler: {e}")
            return {'error': str(e)}

    def _stream_generate(self, params: Dict[str, Any]):
        """
        Handle streaming chat completions.

        Returns an iterator that yields chunks from the OpenAI streaming API.
        Each chunk is converted to a serializable dict.
        """
        try:
            # Call OpenAI with streaming
            stream = self.openai_client.chat.completions.create(**params)

            # Yield each chunk as a serializable dict
            for chunk in stream:
                yield chunk.model_dump()

        except Exception as e:
            logger.error(f"Error in streaming generate: {e}")
            # Yield error as final chunk
            yield {'error': str(e)}

    def _handle_complete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'complete' tool (text completions).

        Returns a serializable dict for MACAW protocol.
        """
        try:
            response = self.openai_client.completions.create(**params)
            return response.model_dump()
        except Exception as e:
            logger.error(f"Error in complete handler: {e}")
            return {'error': str(e)}

    def _handle_embed(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'embed' tool (embeddings).

        Returns a serializable dict for MACAW protocol.
        """
        try:
            response = self.openai_client.embeddings.create(**params)
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

                This mimics OpenAI's API but goes through PEP!
                Adapter creates authenticated prompts based on its own prompts declaration.
                Supports streaming when stream=True is passed.
                """
                # Auto-discover tools if provided
                tools = kwargs.get('tools', kwargs.get('functions'))
                if tools:
                    self.parent._auto_discover_tools(tools)

                tool_name = f"tool:{self.parent.app_name}/generate"
                is_streaming = kwargs.get('stream', False)

                # Route through MACAW's generate resource
                # MAPL-compliant: tool:<service>/generate
                # Authenticated prompts are auto-created by invoke_tool() based on registry
                result = self.parent.macaw_client.invoke_tool(
                    tool_name=tool_name,
                    parameters=kwargs,
                    target_agent=self.parent.server_id,  # Route to ourselves!
                    stream=is_streaming  # Explicit streaming flag
                )

                if is_streaming:
                    # Streaming mode: result is a StreamingResultIterator, wrap in OpenAI types
                    return self._wrap_streaming_response(result)

                # Non-streaming mode: handle errors and reconstruct type
                if isinstance(result, dict) and 'error' in result:
                    raise Exception(f"MACAW error: {result['error']}")

                # Reconstruct ChatCompletion from dict
                from openai.types.chat import ChatCompletion
                return ChatCompletion(**result)

            def _wrap_streaming_response(self, iterator):
                """Wrap streaming chunks in OpenAI ChatCompletionChunk objects."""
                from openai.types.chat import ChatCompletionChunk

                for chunk in iterator:
                    if isinstance(chunk, dict):
                        if 'error' in chunk:
                            raise Exception(f"MACAW streaming error: {chunk['error']}")
                        # Convert dict to ChatCompletionChunk
                        try:
                            yield ChatCompletionChunk(**chunk)
                        except Exception as e:
                            logger.warning(f"Could not convert chunk to ChatCompletionChunk: {e}")
                            yield chunk  # Return raw dict if conversion fails
                    else:
                        yield chunk

    class _CompletionsNamespace:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            """Create text completion - routes through MACAW."""
            tool_name = f"tool:{self.parent.app_name}/complete"

            # MAPL-compliant: tool:<service>/complete
            # Authenticated prompts are auto-created by invoke_tool() based on registry
            result = self.parent.macaw_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.parent.server_id  # Route to ourselves!
            )

            # Handle errors
            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            # Reconstruct Completion from dict
            from openai.types import Completion
            return Completion(**result)

    class _EmbeddingsNamespace:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            """Create embeddings - routes through MACAW."""
            tool_name = f"tool:{self.parent.app_name}/embed"

            # MAPL-compliant: tool:<service>/embed
            # Authenticated prompts are auto-created by invoke_tool() based on registry
            result = self.parent.macaw_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.parent.server_id  # Route to ourselves!
            )

            # Handle errors
            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            # Reconstruct CreateEmbeddingResponse from dict
            from openai.types import CreateEmbeddingResponse
            return CreateEmbeddingResponse(**result)


class BoundSecureOpenAI:
    """
    Per-user wrapper for SecureOpenAI service.

    Created via SecureOpenAI.bind_to_user(user_client).
    Routes all calls through the user's MACAWClient to the service,
    enabling per-user identity and policy enforcement.

    Authenticated prompts are auto-created by invoke_tool based on
    the service's prompts declaration in the registry.

    Call unbind() to invalidate this binding when done.
    """

    def __init__(self, service: SecureOpenAI, user_client: 'MACAWClient'):
        """
        Initialize bound wrapper.

        Args:
            service: The shared SecureOpenAI service (must be in service mode)
            user_client: User's registered MACAWClient with identity
        """
        self._service = service
        self._user_client = user_client
        self._bound = True

        # Create OpenAI-compatible API namespaces
        self.chat = self._ChatNamespace(self)
        self.completions = self._CompletionsNamespace(self)
        self.embeddings = self._EmbeddingsNamespace(self)

    @property
    def service(self) -> SecureOpenAI:
        """Get the bound service (raises if unbound)."""
        if not self._bound:
            raise RuntimeError("BoundSecureOpenAI has been unbound. Create a new binding with bind_to_user().")
        return self._service

    @property
    def user_client(self) -> 'MACAWClient':
        """Get the bound user client (raises if unbound)."""
        if not self._bound:
            raise RuntimeError("BoundSecureOpenAI has been unbound. Create a new binding with bind_to_user().")
        return self._user_client

    def unbind(self):
        """
        Unbind this wrapper, invalidating all future calls.

        After unbinding:
        - All API calls will raise RuntimeError
        - References to service and user_client are cleared
        - A new binding must be created via bind_to_user()

        This is useful for cleanup and ensuring bindings are not reused
        after a user session ends.
        """
        if not self._bound:
            logger.warning("BoundSecureOpenAI.unbind() called on already unbound instance")
            return

        logger.info(f"Unbinding SecureOpenAI from user {self._user_client.agent_id}")
        self._bound = False
        self._service = None
        self._user_client = None

    @property
    def is_bound(self) -> bool:
        """Check if this wrapper is still bound."""
        return self._bound

    # =========================================================================
    # Pass-through properties for non-MACAW-protected APIs
    # These delegate to the service's underlying OpenAI client
    # =========================================================================

    @property
    def models(self):
        """Pass-through to OpenAI models API via service."""
        return self.service.openai_client.models

    @property
    def images(self):
        """Pass-through to OpenAI images API (DALL-E) via service."""
        return self.service.openai_client.images

    @property
    def audio(self):
        """Pass-through to OpenAI audio API (Whisper/TTS) via service."""
        return self.service.openai_client.audio

    @property
    def files(self):
        """Pass-through to OpenAI files API via service."""
        return self.service.openai_client.files

    @property
    def fine_tuning(self):
        """Pass-through to OpenAI fine-tuning API via service."""
        return self.service.openai_client.fine_tuning

    @property
    def moderations(self):
        """Pass-through to OpenAI moderations API via service."""
        return self.service.openai_client.moderations

    @property
    def batches(self):
        """Pass-through to OpenAI batches API via service."""
        return self.service.openai_client.batches

    @property
    def beta(self):
        """Pass-through to OpenAI beta API (assistants, threads, vector stores) via service."""
        return self.service.openai_client.beta

    class _ChatNamespace:
        def __init__(self, bound: 'BoundSecureOpenAI'):
            self.bound = bound
            self.completions = self._Completions(bound)

        class _Completions:
            def __init__(self, bound: 'BoundSecureOpenAI'):
                self.bound = bound

            def create(self, **kwargs):
                """
                Create chat completion via user's client → service.

                Authenticated prompts are auto-created by invoke_tool.
                Supports streaming with stream=True parameter.
                """
                tool_name = f"tool:{self.bound.service.app_name}/generate"
                is_streaming = kwargs.get('stream', False)

                # Route through user's client (auto-creates auth prompts!)
                result = self.bound.user_client.invoke_tool(
                    tool_name=tool_name,
                    parameters=kwargs,
                    target_agent=self.bound.service.server_id,
                    stream=is_streaming  # Explicit streaming flag
                )

                if is_streaming:
                    # Streaming mode: result is a StreamingResultIterator, wrap in OpenAI types
                    return self._wrap_streaming_response(result)

                # Handle errors
                if isinstance(result, dict) and 'error' in result:
                    raise Exception(f"MACAW error: {result['error']}")

                # Reconstruct ChatCompletion from dict
                from openai.types.chat import ChatCompletion
                return ChatCompletion(**result)

            def _wrap_streaming_response(self, iterator):
                """Wrap streaming chunks in OpenAI ChatCompletionChunk objects."""
                from openai.types.chat import ChatCompletionChunk

                for chunk in iterator:
                    if isinstance(chunk, dict):
                        if 'error' in chunk:
                            raise Exception(f"MACAW streaming error: {chunk['error']}")
                        # Convert dict to ChatCompletionChunk
                        try:
                            yield ChatCompletionChunk(**chunk)
                        except Exception as e:
                            logger.warning(f"Could not convert chunk to ChatCompletionChunk: {e}")
                            yield chunk  # Return raw dict if conversion fails
                    else:
                        yield chunk

    class _CompletionsNamespace:
        def __init__(self, bound: 'BoundSecureOpenAI'):
            self.bound = bound

        def create(self, **kwargs):
            """Create text completion via user's client → service."""
            tool_name = f"tool:{self.bound.service.app_name}/complete"

            result = self.bound.user_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.bound.service.server_id
            )

            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            from openai.types import Completion
            return Completion(**result)

    class _EmbeddingsNamespace:
        def __init__(self, bound: 'BoundSecureOpenAI'):
            self.bound = bound

        def create(self, **kwargs):
            """Create embeddings via user's client → service."""
            tool_name = f"tool:{self.bound.service.app_name}/embed"

            result = self.bound.user_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.bound.service.server_id
            )

            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            from openai.types import CreateEmbeddingResponse
            return CreateEmbeddingResponse(**result)