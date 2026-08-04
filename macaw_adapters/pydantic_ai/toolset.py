"""
SecureToolset - the tool seam.

Wraps a Pydantic AI toolset so every call is invoked as tool:<app>/<tool_name>.

Two cases, decided by whether MACAW can hold the callable:

    owned       plain functions (tools=, @agent.tool_plain, FunctionToolset).
                Registered with MACAW, which dispatches them - request and
                response both travel through invoke_tool.

    not owned   toolsets whose execution MACAW cannot hold, such as MCPToolset
                or a tool taking RunContext. The call is authorized through
                invoke_tool and then executed by the wrapped toolset.

Either way no tool runs until the PEP allows it.
"""

import logging
from typing import Any, Callable, Dict, Iterable, Optional

import anyio
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.toolsets import AbstractToolset, WrapperToolset

from macaw_adapters.pydantic_ai._core import is_permission_denied

logger = logging.getLogger(__name__)


class SecureToolset(WrapperToolset):
    """A Pydantic AI toolset whose every call goes through the MACAW PEP."""

    def __init__(
        self,
        binding,
        wrapped: AbstractToolset,
        owned: Iterable[Callable] = (),
    ):
        super().__init__(wrapped)
        self._macaw = binding
        self._owned = set()
        for fn in owned:
            self.own(fn)

    def own(self, fn: Callable, name: Optional[str] = None) -> Callable:
        """Register `fn` with MACAW so MACAW dispatches it."""
        tool_name = name or fn.__name__
        self._macaw.register_tool(tool_name, fn)
        self._owned.add(tool_name)
        return fn

    async def get_tools(self, ctx) -> Dict[str, Any]:
        """
        Resolve tools from the wrapped toolset and make each one a MACAW
        resource. Schemas and validation stay Pydantic AI's.
        """
        tools = await super().get_tools(ctx)
        for name in tools:
            if name not in self._owned:
                self._macaw.register_ack(name)
        return tools

    async def call_tool(self, name: str, tool_args: Dict[str, Any], ctx, tool) -> Any:
        """
        Invoke through MACAW. Owned tools are dispatched by MACAW; the rest are
        authorized here and executed by the wrapped toolset.

        A denial is re-raised as ToolFailed so the model sees it and adapts.
        Retrying would not change the outcome, which is why this is ToolFailed
        rather than ModelRetry.
        """
        try:
            result = await anyio.to_thread.run_sync(
                lambda: self._macaw.invoke(name, tool_args)
            )
        except Exception as exc:
            if is_permission_denied(exc):
                raise ToolFailed(
                    f"Access denied by security policy: {name}. {exc}"
                ) from exc
            raise

        if name in self._owned:
            return result
        return await self.wrapped.call_tool(name, tool_args, ctx, tool)
