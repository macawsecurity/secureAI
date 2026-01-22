#!/usr/bin/env python3
"""
SecureAnthropic - MACAW-protected Anthropic Claude wrapper.

Drop-in replacement for Anthropic client with MACAW security.
Uses MAPL-compliant tool names: tool:<app_name>/generate, tool:<app_name>/complete.

Supports three usage paths:
1. Direct on service: client.messages.create() - simplest, app-level identity
2. bind_to_user: service.bind_to_user(user_client) - per-user identity for SaaS
3. invoke_tool: user.invoke_tool("tool:xxx/generate", ...) - explicit A2A control

Install with: pip install -e /path/to/secureAI
"""

import os
import json
import logging
import inspect
from typing import Dict, Any, Optional, List

from anthropic import Anthropic
from anthropic.types import Message, ContentBlock, TextBlock, Usage
from macaw_client import MACAWClient

logger = logging.getLogger(__name__)


class _StreamContextManager:
    """
    Context manager that provides Anthropic-compatible streaming interface.

    Usage:
        with client.messages.stream(...) as stream:
            for text in stream.text_stream:
                print(text, end="")
    """

    def __init__(self, iterator):
        self._iterator = iterator
        self._text_chunks = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up iterator if needed
        pass

    @property
    def text_stream(self):
        """Yield just the text content from streaming chunks."""
        for chunk in self._iterator:
            if isinstance(chunk, dict):
                # Handle content_block_delta events
                if chunk.get('type') == 'content_block_delta':
                    delta = chunk.get('delta', {})
                    text = delta.get('text', '')
                    if text:
                        yield text
            elif hasattr(chunk, 'delta') and hasattr(chunk.delta, 'text'):
                # Handle raw event objects
                if chunk.delta.text:
                    yield chunk.delta.text

    def __iter__(self):
        """Iterate over raw chunks."""
        return iter(self._iterator)


class SecureAnthropic:
    """
    Drop-in replacement for Anthropic Claude client with MACAW security.

    Supports two modes:
    1. Service mode (default): Creates service agent, registers tools, handles Claude calls
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
        Initialize SecureAnthropic wrapper.

        Args:
            api_key: Anthropic API key (or from env)
            app_name: Application name for registration
            intent_policy: Application-defined MACAW intent policy
            jwt_token: If provided, creates user agent with this identity (user mode)
            user_name: Optional user name for user mode
        """
        # Get API key
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key required")

        # Real Claude client
        self.claude_client = Anthropic(api_key=self.api_key)

        # Application identity
        self.app_name = app_name or "secure-claude-app"

        # Determine mode based on jwt_token
        self._mode = "user" if jwt_token else "service"
        self._jwt_token = jwt_token
        self._user_name = user_name

        # User-registered tools (Claude can call these)
        self.user_tools = {}

        # Auto-discovered tools cache
        self._discovered_tools = {}
        self._tools_registered = False

        # Application-provided intent policy (no defaults!)
        self.intent_policy = intent_policy or {}

        if self._mode == "service":
            # SERVICE MODE: Register tools and handle Claude calls
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
                }
            }

            # Extract handlers for backward compat
            self.tool_handlers = {k: v["handler"] for k, v in self.tools.items()}

            # Create MACAWClient
            self.macaw_client = MACAWClient(
                app_name=self.app_name,
                app_version="1.0.0",
                intent_policy=self.intent_policy,
                tool_handlers=self.tool_handlers,
                tools=self.tools,  # Pass tools with prompts declaration
                persistent_connection=True  # Required for tool execution
            )
        else:
            # USER MODE: Create user agent with identity
            self.tools = {}
            self.tool_handlers = {}

            self.macaw_client = MACAWClient(
                user_name=user_name,
                iam_token=jwt_token,
                agent_type="user",
                app_name=self.app_name,
                app_version="1.0.0",
                intent_policy=self.intent_policy or {
                    "purpose": f"Claude access for {user_name or 'user'}"
                }
            )

        # Register with LocalAgent and get server ID
        if self.macaw_client.register():
            self.server_id = self.macaw_client.agent_id
            logger.info(f"SecureAnthropic registered as: {self.server_id} (mode: {self._mode})")
        else:
            raise RuntimeError("Failed to register with MACAW LocalAgent")

        # Mimic Anthropic API structure
        # MACAW-protected namespaces (route through PEP)
        self.messages = self._MessagesNamespace(self)
        self.completions = self._CompletionsNamespace(self)

    # =========================================================================
    # Pass-through properties for non-MACAW-protected APIs
    # These delegate directly to the underlying Anthropic client
    # =========================================================================

    @property
    def beta(self):
        """
        Pass-through to Anthropic beta API (message batches).

        Not MACAW-protected - batch operations use service's API key directly.
        """
        return self.claude_client.beta

    def count_tokens(self, *args, **kwargs):
        """
        Pass-through to Anthropic count_tokens method.

        Not MACAW-protected - token counting uses service's API key directly.
        """
        return self.claude_client.count_tokens(*args, **kwargs)

    def bind_to_user(self, user_client: 'MACAWClient') -> 'BoundSecureAnthropic':
        """
        Bind this SecureAnthropic service to a user's MACAW client.

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
            BoundSecureAnthropic wrapper for this user

        Raises:
            ValueError: If service not in service mode or client validation fails
        """
        if self._mode != "service":
            raise ValueError("bind_to_user() only valid for service-mode SecureAnthropic")

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

        return BoundSecureAnthropic(self, user_client)

    def register_tool(self, name: str, handler: callable) -> 'SecureAnthropic':
        """
        Register a tool that Claude can call.

        Args:
            name: Tool name (must match Claude function name)
            handler: Function to handle tool execution

        Returns:
            Self for chaining
        """
        self.user_tools[name] = handler
        self.tool_handlers[name] = handler

        # Update MACAWClient with new tool using public API
        self.macaw_client.register_tool(name, handler)

        logger.info(f"Registered tool: {name}")
        return self

    def _auto_discover_tools(self, tools_metadata):
        """
        Auto-discover tool implementations from caller's context.

        Args:
            tools_metadata: List of tool definitions from Claude call
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
            func_name = tool_def.get("name")

            if func_name and func_name not in self.user_tools:
                # Look for function in caller's scope
                if func_name in search_scope:
                    func = search_scope[func_name]
                    if callable(func):
                        logger.info(f"Auto-discovered tool: {func_name}")
                        self._discovered_tools[func_name] = func
                        self.user_tools[func_name] = func
                        self.tool_handlers[func_name] = func
                else:
                    logger.warning(f"Tool '{func_name}' not found in caller's scope")

        # Sync all discovered tools with MACAW agent using public API
        if self._discovered_tools:
            # Update MACAWClient with all new tools
            for name, func in self._discovered_tools.items():
                # Create wrapper handler that accepts dict parameter
                def create_handler(tool_func):
                    def handler(params):
                        return tool_func(**params)
                    return handler
                self.macaw_client.register_tool(name, create_handler(func))
            self._tools_registered = True
            logger.info(f"Auto-registered {len(self._discovered_tools)} tools with MACAW")

    def _handle_generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'generate' tool (messages creation).

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
            # Call real Claude API (params are clean - no MACAW internals)
            response = self.claude_client.messages.create(**params)

            # Check if Claude wants to call tools
            if hasattr(response, 'content') and response.content:
                for content_block in response.content:
                    if content_block.type == 'tool_use':
                        tool_name = content_block.name
                        tool_args = content_block.input
                        logger.info(f"Claude requested tool use: {tool_name}")

                        # Check if we have this tool
                        if tool_name not in self.user_tools:
                            result = {
                                'error': f"Tool not found: {tool_name}",
                                'available_tools': list(self.user_tools.keys())
                            }
                        else:
                            # Invoke tool through MACAW (goes through PEP!)
                            try:
                                result = self.macaw_client.invoke_tool(
                                    tool_name=tool_name,
                                    parameters=tool_args,
                                    target_agent=self.server_id  # Route to ourselves!
                                )
                                logger.info(f"Tool {tool_name} executed successfully")
                            except Exception as e:
                                error_msg = str(e)
                                # Check if MACAW blocked it
                                if 'denied' in error_msg.lower() or 'policy' in error_msg.lower():
                                    logger.warning(f"MACAW blocked tool {tool_name}: {error_msg}")
                                    result = {
                                        'error': 'Access denied by security policy',
                                        'tool': tool_name,
                                        'reason': 'Policy violation'
                                    }
                                else:
                                    result = {'error': str(e)}

                        # Build messages for continuation
                        messages = list(params.get('messages', []))

                        # Add assistant message with tool use
                        messages.append({
                            "role": "assistant",
                            "content": [{"type": "tool_use", "id": content_block.id,
                                        "name": tool_name, "input": tool_args}]
                        })

                        # Add tool result
                        messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": content_block.id,
                                "content": json.dumps(result)
                            }]
                        })

                        # Continue conversation with tool results
                        final_params = params.copy()
                        final_params['messages'] = messages

                        # Remove tools to prevent infinite recursion
                        if 'tools' in final_params:
                            del final_params['tools']

                        final_response = self.claude_client.messages.create(**final_params)

                        # Convert to serializable dict for MACAW protocol
                        return self._response_to_dict(final_response)

            # No tool calls, convert response to dict
            return self._response_to_dict(response)

        except Exception as e:
            logger.error(f"Error in generate handler: {e}")
            return {'error': str(e)}

    def _stream_generate(self, params: Dict[str, Any]):
        """
        Handle streaming message creation.

        Returns an iterator that yields chunks from the Anthropic streaming API.
        Each chunk is converted to a serializable dict.
        """
        try:
            # Call Anthropic with streaming
            with self.claude_client.messages.stream(**{k: v for k, v in params.items() if k != 'stream'}) as stream:
                for event in stream:
                    # Convert event to serializable dict
                    if hasattr(event, 'type'):
                        chunk_dict = {
                            'type': event.type,
                        }
                        # Handle different event types
                        if event.type == 'content_block_delta':
                            if hasattr(event, 'delta') and hasattr(event.delta, 'text'):
                                chunk_dict['delta'] = {'text': event.delta.text}
                            if hasattr(event, 'index'):
                                chunk_dict['index'] = event.index
                        elif event.type == 'message_start':
                            if hasattr(event, 'message'):
                                chunk_dict['message'] = {
                                    'id': event.message.id,
                                    'model': event.message.model,
                                    'role': event.message.role,
                                }
                        elif event.type == 'message_delta':
                            if hasattr(event, 'delta'):
                                chunk_dict['delta'] = {}
                                if hasattr(event.delta, 'stop_reason'):
                                    chunk_dict['delta']['stop_reason'] = event.delta.stop_reason
                            if hasattr(event, 'usage'):
                                chunk_dict['usage'] = {
                                    'output_tokens': event.usage.output_tokens
                                }
                        elif event.type == 'message_stop':
                            pass  # Just mark end of stream

                        yield chunk_dict

        except Exception as e:
            logger.error(f"Error in streaming generate: {e}")
            # Yield error as final chunk
            yield {'error': str(e)}

    def _handle_complete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'complete' tool (legacy completions).

        Returns a serializable dict for MACAW protocol.
        """
        try:
            response = self.claude_client.completions.create(**params)
            return {
                'id': getattr(response, 'id', None),
                'type': 'completion',
                'completion': response.completion,
                'model': getattr(response, 'model', None),
                'stop_reason': getattr(response, 'stop_reason', None)
            }
        except Exception as e:
            logger.error(f"Error in complete handler: {e}")
            return {'error': str(e)}

    def _response_to_dict(self, response) -> Dict[str, Any]:
        """Convert Anthropic Message response to serializable dict."""
        result = {
            'id': response.id,
            'type': response.type,
            'role': response.role,
            'model': response.model,
            'content': [],
            'stop_reason': response.stop_reason,
            'stop_sequence': response.stop_sequence,
            'usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens
            } if response.usage else None
        }

        # Convert content blocks
        for block in response.content:
            if hasattr(block, 'text'):
                result['content'].append({
                    'type': 'text',
                    'text': block.text
                })
            elif hasattr(block, 'type') and block.type == 'tool_use':
                result['content'].append({
                    'type': 'tool_use',
                    'id': block.id,
                    'name': block.name,
                    'input': block.input
                })

        return result

    def _dict_to_message(self, data: Dict[str, Any]) -> Message:
        """Reconstruct Anthropic Message from dict."""
        # Build content blocks
        content = []
        for block_data in data.get('content', []):
            if block_data.get('type') == 'text':
                content.append(TextBlock(type='text', text=block_data['text']))
            # Add other block types as needed

        # Build usage
        usage = None
        if data.get('usage'):
            usage = Usage(
                input_tokens=data['usage']['input_tokens'],
                output_tokens=data['usage']['output_tokens']
            )

        return Message(
            id=data['id'],
            type=data.get('type', 'message'),
            role=data.get('role', 'assistant'),
            model=data['model'],
            content=content,
            stop_reason=data.get('stop_reason'),
            stop_sequence=data.get('stop_sequence'),
            usage=usage
        )

    def _create_authenticated_prompts_for_tool(
        self, tool_name: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Create authenticated prompts for a tool invocation.

        The adapter knows its own prompts declaration (from self.tools).
        Uses the simple create_authenticated_prompt() API which auto-handles
        root vs derived internally.

        Args:
            tool_name: Name of the tool being invoked
            params: The invocation parameters

        Returns:
            Dict mapping param names to AuthenticatedPrompt.to_dict(), or None
        """
        # Check if authenticated prompts are enabled
        if not self.macaw_client.agent.authenticate_prompts:
            return None

        # Get prompts declaration from our own tools config
        prompts_decl = self.tools.get(tool_name, {}).get("prompts", [])
        if not prompts_decl:
            return None

        authenticated_prompts = {}
        for param_name in prompts_decl:
            if param_name not in params:
                continue

            # Serialize the parameter value
            param_value = params[param_name]
            prompt_text = json.dumps(param_value) if isinstance(param_value, (list, dict)) else str(param_value)

            # Simple call - SDK handles root vs derive internally
            auth_prompt = self.macaw_client.agent.create_authenticated_prompt(
                prompt_text=prompt_text,
                metadata={'param': param_name, 'tool': tool_name}
            )
            authenticated_prompts[param_name] = auth_prompt.to_dict()

        return authenticated_prompts or None

    # Namespace classes to mimic Anthropic API structure
    class _MessagesNamespace:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            """
            Create message - routes through MACAW.

            This mimics Anthropic's API but goes through PEP!
            Adapter creates authenticated prompts based on its own prompts declaration.
            Supports streaming when stream=True is passed.
            """
            # Auto-discover tools if provided
            tools = kwargs.get('tools')
            if tools:
                self.parent._auto_discover_tools(tools)

            tool_name = f"tool:{self.parent.app_name}/generate"
            is_streaming = kwargs.get('stream', False)

            # Adapter creates authenticated prompts ITSELF
            # No registry lookup needed - we KNOW our prompts declaration
            authenticated_prompts = self.parent._create_authenticated_prompts_for_tool(
                tool_name, kwargs
            )

            # Route through MACAW's generate resource
            # MAPL-compliant: tool:<service>/generate
            result = self.parent.macaw_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.parent.server_id,  # Route to ourselves!
                authenticated_prompts=authenticated_prompts,  # Pass authenticated prompts directly
                stream=is_streaming  # Explicit streaming flag
            )

            if is_streaming:
                # Streaming mode: result is a StreamingResultIterator, wrap in Anthropic types
                return self._wrap_streaming_response(result)

            # Handle errors
            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            # Reconstruct Message from dict
            return self.parent._dict_to_message(result)

        def _wrap_streaming_response(self, iterator):
            """Wrap streaming chunks for Anthropic-compatible iteration."""
            for chunk in iterator:
                if isinstance(chunk, dict):
                    if 'error' in chunk:
                        raise Exception(f"MACAW streaming error: {chunk['error']}")
                    yield chunk
                else:
                    yield chunk

        def stream(self, **kwargs):
            """
            Stream message creation - context manager style.

            Usage:
                with client.messages.stream(...) as stream:
                    for text in stream.text_stream:
                        print(text, end="")
            """
            # Use create with stream=True, wrap in context manager
            kwargs['stream'] = True
            return _StreamContextManager(self.create(**kwargs))

    class _CompletionsNamespace:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            """Create completion - routes through MACAW."""
            tool_name = f"tool:{self.parent.app_name}/complete"

            # Adapter creates authenticated prompts ITSELF
            authenticated_prompts = self.parent._create_authenticated_prompts_for_tool(
                tool_name, kwargs
            )

            # MAPL-compliant: tool:<service>/complete
            result = self.parent.macaw_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.parent.server_id,  # Route to ourselves!
                authenticated_prompts=authenticated_prompts
            )

            # Handle errors
            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            # Return raw completion dict (legacy API)
            return result


class BoundSecureAnthropic:
    """
    Per-user wrapper for SecureAnthropic service.

    Created via SecureAnthropic.bind_to_user(user_client).
    Routes all calls through the user's MACAWClient to the service,
    enabling per-user identity and policy enforcement.

    Authenticated prompts are auto-created by invoke_tool based on
    the service's prompts declaration in the registry.

    Call unbind() to invalidate this binding when done.
    """

    def __init__(self, service: SecureAnthropic, user_client: 'MACAWClient'):
        """
        Initialize bound wrapper.

        Args:
            service: The shared SecureAnthropic service (must be in service mode)
            user_client: User's registered MACAWClient with identity
        """
        self._service = service
        self._user_client = user_client
        self._bound = True

        # Create Anthropic-compatible API namespaces
        self.messages = self._MessagesNamespace(self)
        self.completions = self._CompletionsNamespace(self)

    @property
    def service(self) -> SecureAnthropic:
        """Get the bound service (raises if unbound)."""
        if not self._bound:
            raise RuntimeError("BoundSecureAnthropic has been unbound. Create a new binding with bind_to_user().")
        return self._service

    @property
    def user_client(self) -> 'MACAWClient':
        """Get the bound user client (raises if unbound)."""
        if not self._bound:
            raise RuntimeError("BoundSecureAnthropic has been unbound. Create a new binding with bind_to_user().")
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
            logger.warning("BoundSecureAnthropic.unbind() called on already unbound instance")
            return

        logger.info(f"Unbinding SecureAnthropic from user {self._user_client.agent_id}")
        self._bound = False
        self._service = None
        self._user_client = None

    @property
    def is_bound(self) -> bool:
        """Check if this wrapper is still bound."""
        return self._bound

    # =========================================================================
    # Pass-through properties for non-MACAW-protected APIs
    # These delegate to the service's underlying Anthropic client
    # =========================================================================

    @property
    def beta(self):
        """Pass-through to Anthropic beta API (message batches) via service."""
        return self.service.claude_client.beta

    def count_tokens(self, *args, **kwargs):
        """Pass-through to Anthropic count_tokens method via service."""
        return self.service.claude_client.count_tokens(*args, **kwargs)

    class _MessagesNamespace:
        def __init__(self, bound: 'BoundSecureAnthropic'):
            self.bound = bound

        def create(self, **kwargs):
            """
            Create message via user's client -> service.

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
                # Streaming mode: result is a StreamingResultIterator, wrap for iteration
                return self._wrap_streaming_response(result)

            # Handle errors
            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            # Reconstruct Message from dict
            return self.bound.service._dict_to_message(result)

        def _wrap_streaming_response(self, iterator):
            """Wrap streaming chunks for Anthropic-compatible iteration."""
            for chunk in iterator:
                if isinstance(chunk, dict):
                    if 'error' in chunk:
                        raise Exception(f"MACAW streaming error: {chunk['error']}")
                    yield chunk
                else:
                    yield chunk

        def stream(self, **kwargs):
            """
            Stream message creation - context manager style.

            Usage:
                with user_client.messages.stream(...) as stream:
                    for text in stream.text_stream:
                        print(text, end="")
            """
            # Use create with stream=True, wrap in context manager
            kwargs['stream'] = True
            return _StreamContextManager(self.create(**kwargs))

    class _CompletionsNamespace:
        def __init__(self, bound: 'BoundSecureAnthropic'):
            self.bound = bound

        def create(self, **kwargs):
            """Create completion via user's client -> service."""
            tool_name = f"tool:{self.bound.service.app_name}/complete"

            result = self.bound.user_client.invoke_tool(
                tool_name=tool_name,
                parameters=kwargs,
                target_agent=self.bound.service.server_id
            )

            if isinstance(result, dict) and 'error' in result:
                raise Exception(f"MACAW error: {result['error']}")

            # Return raw completion dict (legacy API)
            return result
