"""
SecureModel - the model seam.

Wraps any Pydantic AI model so every request is invoked as tool:<app>/generate.
MACAW dispatches to the wrapped model once the PEP allows the call, so the
request and the response both travel through invoke_tool - the same path a tool
call takes.

What policy sees per call:

    model          the model id, e.g. "anthropic.claude-haiku-4-5"
    messages       the conversation, declared as a prompt so invoke_tool creates
                   authenticated prompts from it
    native_tools   provider-side tools offered on this call
    <settings>     max_tokens, temperature, and anything else the caller set
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import anyio
from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel

from macaw_adapters.pydantic_ai._core import REQUEST_PARAMETERS_KEY

logger = logging.getLogger(__name__)

_RESPONSE = TypeAdapter(ModelResponse)
_REQUEST_PARAMETERS = TypeAdapter(ModelRequestParameters)


class SecureModel(WrapperModel):
    """A Pydantic AI model whose every request goes through the MACAW PEP."""

    def __init__(self, binding, wrapped):
        super().__init__(wrapped)
        self._macaw = binding
        binding.register_model(self.wrapped)

    @staticmethod
    def _native_tool_names(request_parameters) -> List[str]:
        """
        Names of the provider-side tools offered on this request.

        Read from the request rather than from what the application declared, so
        policy sees what the provider was actually asked for.
        """
        native = getattr(request_parameters, "native_tools", None) or []
        return sorted(
            getattr(tool, "kind", None) or type(tool).__name__ for tool in native
        )

    def _params(
        self,
        messages: List[Any],
        model_settings: Optional[Dict[str, Any]],
        request_parameters: ModelRequestParameters,
    ) -> Dict[str, Any]:
        return {
            "model": self.wrapped.model_name,
            "messages": ModelMessagesTypeAdapter.dump_python(messages, mode="json"),
            "native_tools": self._native_tool_names(request_parameters),
            REQUEST_PARAMETERS_KEY: _REQUEST_PARAMETERS.dump_python(
                request_parameters, mode="json"
            ),
            **(model_settings or {}),
        }

    async def request(self, messages, model_settings, model_request_parameters):
        params = self._params(messages, model_settings, model_request_parameters)
        result = await anyio.to_thread.run_sync(
            lambda: self._macaw.invoke("generate", params)
        )
        return _RESPONSE.validate_python(result)

    @asynccontextmanager
    async def request_stream(
        self, messages, model_settings, model_request_parameters, run_context=None
    ):
        """
        Streaming path.

        The call is authorized through invoke_tool and the events are then
        streamed from the wrapped model directly, so no stream event is
        re-serialized on the way to the caller.
        """
        params = self._params(messages, model_settings, model_request_parameters)
        params["stream"] = True
        await anyio.to_thread.run_sync(
            lambda: self._macaw.invoke("generate", dict(params, _authorize_only=True))
        )
        async with self.wrapped.request_stream(
            messages, model_settings, model_request_parameters, run_context
        ) as stream:
            yield stream
