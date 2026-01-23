"""
MACAW Agent Functions - Drop-in replacements for LangChain agent creation.

Usage:
    # Instead of: from langchain.agents import create_react_agent, AgentExecutor
    from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor

    agent = create_react_agent(llm, tools, prompt, security_policy={...})
    executor = AgentExecutor(agent=agent, tools=tools, security_policy={...})
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from macaw_client import MACAWClient
from ._utils import get_or_create_client, register_client, cleanup_all
from .tools import SecureToolWrapper, wrap_tools

logger = logging.getLogger(__name__)


class _AuthenticatedLLMWrapper:
    """
    Transparent wrapper that routes LLM prompts through MACAW authentication.

    Invisible to developers - presents same interface as original LLM.
    """

    def __init__(self, original_llm: Any, macaw_client: MACAWClient):
        self._llm = original_llm
        self._macaw = macaw_client

        # Copy non-callable attributes
        for attr in dir(original_llm):
            if not attr.startswith('_') and not callable(getattr(original_llm, attr)):
                try:
                    setattr(self, attr, getattr(original_llm, attr))
                except AttributeError:
                    pass

    def invoke(self, prompt, **kwargs):
        """Intercept and authenticate prompts."""
        try:
            auth_prompt = self._macaw.create_authenticated_prompt(
                prompt_text=str(prompt),
                metadata={
                    "agent_id": self._macaw.agent_id,
                    "source": "langchain_agent"
                }
            )
            logger.debug("[SecureAgent] Created authenticated prompt")
            return self._llm.invoke(auth_prompt, **kwargs)
        except Exception as e:
            logger.warning(f"Auth prompt failed, using original: {e}")
            return self._llm.invoke(prompt, **kwargs)

    def predict(self, text: str, **kwargs):
        """Handle predict interface."""
        try:
            auth_text = self._macaw.create_authenticated_prompt(
                prompt_text=text,
                metadata={"agent_id": self._macaw.agent_id}
            )
            return self._llm.predict(auth_text, **kwargs)
        except Exception as e:
            logger.warning(f"Auth prompt failed, using original: {e}")
            return self._llm.predict(text, **kwargs)

    def __getattr__(self, name):
        """Delegate to original LLM."""
        return getattr(self._llm, name)


def _setup_security(
    tools: List[Any],
    security_policy: Optional[Dict[str, Any]]
) -> tuple:
    """
    Set up MACAW security for tools.

    Args:
        tools: List of LangChain tools
        security_policy: MAPL format policy dict with resources, denied_resources, constraints

    Returns:
        (processed_tools, macaw_client) - wrapped tools and client, or originals if no policy

    Example policy (MAPL format):
        {
            "resources": ["tool:calculator", "tool:weather"],
            "denied_resources": ["tool:admin"],
            "constraints": {
                "denied_parameters": {"tool:*": {"query": ["*password*"]}}
            }
        }
    """
    if not security_policy:
        return tools, None

    # Filter tools based on policy - LLM should only see tools it can use
    # This prevents wasted iterations on blocked tools
    allowed_tools = tools
    if "resources" in security_policy:
        allowed_names = {r.replace("tool:", "") for r in security_policy["resources"]}
        allowed_tools = [t for t in tools if t.name in allowed_names]
        logger.debug(f"Filtered tools to allowed resources: {[t.name for t in allowed_tools]}")

    # Also exclude explicitly denied tools
    if "denied_resources" in security_policy:
        denied_names = {r.replace("tool:", "") for r in security_policy["denied_resources"]}
        allowed_tools = [t for t in allowed_tools if t.name not in denied_names]
        logger.debug(f"Excluded denied resources: {denied_names}")

    # Build tools dict with handlers and prompts declaration
    # Following the same pattern as SecureOpenAI
    tools_config = {}
    for tool in allowed_tools:
        handler = None
        if hasattr(tool, 'func'):
            # Wrap func to handle params as dict or string
            def make_handler(func):
                def handler(params):
                    if isinstance(params, dict):
                        # Try 'input' key first (standard), then unpack as kwargs
                        if 'input' in params:
                            return func(params['input'])
                        return func(**params)
                    return func(params)
                return handler
            handler = make_handler(tool.func)
        elif hasattr(tool, '_run'):
            def make_run_handler(t):
                def handler(params):
                    if isinstance(params, dict):
                        return t._run(**params)
                    return t._run(params)
                return handler
            handler = make_run_handler(tool)

        if handler:
            # Check if security_policy specifies prompts for this tool
            # Default: LangChain tools take 'input' as the prompt parameter
            tool_prompts = security_policy.get('tool_prompts', {}).get(tool.name, ['input'])
            tools_config[tool.name] = {
                "handler": handler,
                "prompts": tool_prompts
            }

    # Create MACAW client with unified tools config
    client = MACAWClient(
        app_name="secure-langchain-agent",
        app_version="1.0.0",
        intent_policy=security_policy,  # MAPL format policy passed directly
        tools=tools_config  # Unified: {name: {handler, prompts, ...}}
    )

    if client.register():
        register_client(client.agent_id, client)
        logger.info(f"SecureAgent registered: {client.agent_id}")
        return wrap_tools(allowed_tools, client), client
    else:
        logger.error("Failed to register with MACAW")
        return allowed_tools, None


def create_react_agent(
    llm: Any,
    tools: List[Any],
    prompt: Any,
    security_policy: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Any:
    """
    Drop-in replacement for LangChain's create_react_agent.

    Args:
        llm: Language model
        tools: List of tools
        prompt: Prompt template
        security_policy: Optional security policy (simple format)
        **kwargs: Additional arguments for original function

    Returns:
        Agent runnable

    Example:
        agent = create_react_agent(
            llm, tools, prompt,
            security_policy={"allowed_tools": ["calculator", "weather"]}
        )
    """
    from langchain.agents import create_react_agent as _create_react_agent

    wrapped_tools, client = _setup_security(tools, security_policy)

    # Wrap LLM if we have a client
    wrapped_llm = _AuthenticatedLLMWrapper(llm, client) if client else llm

    return _create_react_agent(wrapped_llm, wrapped_tools, prompt, **kwargs)


def create_openai_functions_agent(
    llm: Any,
    tools: List[Any],
    prompt: Any,
    security_policy: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Any:
    """
    Drop-in replacement for LangChain's create_openai_functions_agent.

    Args:
        llm: Language model
        tools: List of tools
        prompt: Prompt template
        security_policy: Optional security policy
        **kwargs: Additional arguments

    Returns:
        Agent runnable
    """
    from langchain.agents import create_openai_functions_agent as _create_openai_functions_agent

    wrapped_tools, client = _setup_security(tools, security_policy)
    wrapped_llm = _AuthenticatedLLMWrapper(llm, client) if client else llm

    return _create_openai_functions_agent(wrapped_llm, wrapped_tools, prompt, **kwargs)


class AgentExecutor:
    """
    Drop-in replacement for LangChain's AgentExecutor with security support.

    Uses composition to wrap the original while enforcing policies.
    """

    def __init__(
        self,
        agent: Any,
        tools: List[Any],
        security_policy: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize with optional security policy.

        Args:
            agent: The agent to use
            tools: List of tools
            security_policy: Optional security policy
            **kwargs: Arguments for original AgentExecutor
        """
        from langchain.agents import AgentExecutor as _AgentExecutor

        wrapped_tools, self._macaw = _setup_security(tools, security_policy)

        # Wrap agent's LLM if present
        if self._macaw and hasattr(agent, 'llm'):
            try:
                agent.llm = _AuthenticatedLLMWrapper(agent.llm, self._macaw)
            except Exception:
                pass

        self._executor = _AgentExecutor(agent=agent, tools=wrapped_tools, **kwargs)

    def invoke(self, input_data: Any, **kwargs) -> Any:
        return self._executor.invoke(input_data, **kwargs)

    def batch(self, inputs: List[Any], **kwargs) -> List:
        return self._executor.batch(inputs, **kwargs)

    def stream(self, input_data: Any, **kwargs):
        return self._executor.stream(input_data, **kwargs)

    async def ainvoke(self, input_data: Any, **kwargs) -> Any:
        return await self._executor.ainvoke(input_data, **kwargs)

    async def abatch(self, inputs: List[Any], **kwargs) -> List:
        return await self._executor.abatch(inputs, **kwargs)

    async def astream(self, input_data: Any, **kwargs):
        async for chunk in self._executor.astream(input_data, **kwargs):
            yield chunk

    def __getattr__(self, name: str) -> Any:
        return getattr(self._executor, name)


def cleanup():
    """Clean up all MACAW resources."""
    cleanup_all()


# Auto-cleanup on module exit
import atexit
atexit.register(cleanup)
