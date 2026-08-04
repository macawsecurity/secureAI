"""
SecureAgent - drop-in replacement for pydantic_ai.Agent.

    # Before
    from pydantic_ai import Agent
    agent = Agent(OpenAIChatModel("gpt-4o"), tools=[query_catalog])

    # After
    from macaw_adapters.pydantic_ai import SecureAgent
    agent = SecureAgent(OpenAIChatModel("gpt-4o"), app_name="acme",
                        tools=[query_catalog])

Every way Pydantic AI takes tools is governed:

    tools=[fn]                       registered with MACAW
    @agent.tool / @agent.tool_plain  registered with MACAW
    toolsets=[FunctionToolset(...)]  functions registered with MACAW
    toolsets=[MCPToolset(...)]       authorized here, executed by the server it
                                     connects to (governed there by SecureMCP or
                                     SecureMCPProxy)

run(), run_sync(), run_stream(), and override() wrap any model or toolsets
passed to them, so a per-call override cannot route around the adapter.

Multi-user:

    alice_agent = agent.bind_to_user(alice_client)
"""

import logging
from contextlib import contextmanager
from typing import Any, Callable, List, Optional, Sequence

from pydantic_ai import Agent as _Agent
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset

from macaw_adapters.pydantic_ai._core import MacawBinding
from macaw_adapters.pydantic_ai.model import SecureModel
from macaw_adapters.pydantic_ai.toolset import SecureToolset

logger = logging.getLogger(__name__)


def _functions_of(toolset: AbstractToolset) -> Optional[List[Callable]]:
    """
    The plain functions behind a toolset, or None if MACAW cannot hold them.

    FunctionToolset exposes `.tools` as {name: Tool}, with Tool.function being
    the original callable.
    """
    if not isinstance(toolset, FunctionToolset):
        return None
    return [t.function for t in toolset.tools.values() if hasattr(t, "function")]


class SecureAgent(_Agent):
    """A pydantic_ai.Agent whose model and tool calls route through MACAW."""

    def __init__(
        self,
        model=None,
        *,
        app_name: Optional[str] = None,
        intent_policy: Optional[dict] = None,
        jwt_token: Optional[str] = None,
        user_name: Optional[str] = None,
        tools: Sequence[Callable] = (),
        toolsets: Optional[Sequence[AbstractToolset]] = None,
        _binding: Optional[MacawBinding] = None,
        **kwargs,
    ):
        self._macaw = _binding or MacawBinding(
            app_name=app_name,
            intent_policy=intent_policy,
            jwt_token=jwt_token,
            user_name=user_name,
        )

        # Kept so bind_to_user() can rebuild an identical agent on a user binding.
        self._raw_model = model
        self._raw_tools = list(tools)
        self._raw_toolsets = list(toolsets or [])
        self._raw_kwargs = dict(kwargs)

        # tools= and the @agent.tool decorators share one governed toolset.
        functions = list(tools)
        passthrough = []
        for toolset in self._raw_toolsets:
            fns = _functions_of(toolset)
            if fns is None:
                passthrough.append(toolset)
            else:
                functions.extend(fns)

        self._tools = SecureToolset(
            self._macaw, FunctionToolset(tools=functions), owned=functions
        )

        super().__init__(
            self._secure_model(model),
            toolsets=[self._tools] + [self._secure_toolset(t) for t in passthrough],
            **kwargs,
        )

    # --------------------------------------------------------------- wrapping

    def _secure_model(self, model):
        if model is None or isinstance(model, SecureModel):
            return model
        if isinstance(model, str):
            from pydantic_ai.models import infer_model

            model = infer_model(model)

        # A router such as FallbackModel keeps its candidates in .models and
        # reports a composite model_name. Secure the candidates instead, so
        # policy always sees the model that actually calls a provider.
        members = getattr(model, "models", None)
        if members:
            model.models = [self._secure_model(m) for m in members]
            return model

        return SecureModel(self._macaw, model)

    def _secure_toolset(self, toolset: AbstractToolset):
        if isinstance(toolset, SecureToolset):
            return toolset
        fns = _functions_of(toolset)
        if fns is None:
            return SecureToolset(self._macaw, toolset)
        return SecureToolset(self._macaw, toolset, owned=fns)

    def _secure_toolsets(self, toolsets):
        if toolsets is None:
            return None
        return [self._secure_toolset(t) for t in toolsets]

    # ------------------------------------------------------------- decorators

    def tool(self, func=None, /, **kwargs):
        """Register a tool that takes RunContext. Governed like any other."""
        return self._tool_decorator(func, takes_ctx=True, **kwargs)

    def tool_plain(self, func=None, /, **kwargs):
        """Register a tool that does not take RunContext."""
        return self._tool_decorator(func, takes_ctx=False, **kwargs)

    def _tool_decorator(self, func, *, takes_ctx: bool, **kwargs):
        def register(fn):
            self._tools.wrapped.add_function(fn, takes_ctx=takes_ctx, **kwargs)
            name = kwargs.get("name") or fn.__name__
            if takes_ctx:
                # A tool taking RunContext cannot be dispatched by MACAW, which
                # passes only a params dict, so it is authorized instead.
                self._macaw.register_ack(name)
            else:
                self._tools.own(fn, name=name)
            return fn

        return register if func is None else register(func)

    # ------------------------------------------------------------------ seams
    # Per-call model/toolsets replace the agent's own, so they are wrapped too.

    async def run(self, *args, model=None, toolsets=None, **kwargs):
        return await super().run(
            *args,
            model=self._secure_model(model),
            toolsets=self._secure_toolsets(toolsets),
            **kwargs,
        )

    def run_sync(self, *args, model=None, toolsets=None, **kwargs):
        return super().run_sync(
            *args,
            model=self._secure_model(model),
            toolsets=self._secure_toolsets(toolsets),
            **kwargs,
        )

    def run_stream(self, *args, model=None, toolsets=None, **kwargs):
        return super().run_stream(
            *args,
            model=self._secure_model(model),
            toolsets=self._secure_toolsets(toolsets),
            **kwargs,
        )

    @contextmanager
    def override(self, *, model=None, toolsets=None, **kwargs):
        overrides = dict(kwargs)
        if model is not None:
            overrides["model"] = self._secure_model(model)
        if toolsets is not None:
            overrides["toolsets"] = self._secure_toolsets(toolsets)
        with super().override(**overrides):
            yield

    # ------------------------------------------------------------------ users

    def bind_to_user(self, user_client: Any) -> "SecureAgent":
        """
        Return an agent that issues invocations as `user_client`.

        Shares this agent's registration and tools; policy is evaluated for the
        user on every model and tool call.
        """
        return SecureAgent(
            self._raw_model,
            tools=self._raw_tools,
            toolsets=self._raw_toolsets,
            _binding=self._macaw.for_user(user_client),
            **self._raw_kwargs,
        )


# Drop-in alias (same class, native naming)
Agent = SecureAgent
