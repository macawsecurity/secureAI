"""
Shared MACAW binding for the Pydantic AI adapter.

MacawBinding holds the MACAWClient, the set of registered resource names, and
the models reachable by the generate handler. SecureModel and SecureToolset are
constructed with a binding and call through it.

    MacawBinding(app_name=...)          registers the app; issues as the app
    binding.for_user(user_client)       shares that registration; issues as the user

    binding.register_tool(name, fn)     -> tool:<app>/<name>, dispatched by MACAW
    binding.register_ack(name)          -> tool:<app>/<name>, authorization only
    binding.invoke(resource, params)    -> invoke_tool(tool:<app>/<resource>, ...)
"""

import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Carries ModelRequestParameters through invoke_tool. invoke_tool has no channel
# other than `parameters`, so this rides alongside the policy inputs.
REQUEST_PARAMETERS_KEY = "_request_parameters"

try:
    from macaw_client import MACAWClient, PermissionDenied
except ImportError:  # pragma: no cover - surfaced at construction time
    MACAWClient = None
    PermissionDenied = None


def is_permission_denied(exc: BaseException) -> bool:
    """
    True if `exc` is a MACAW policy denial.

    macaw_client exports one PermissionDenied, and a second class of the same
    name is raised from the SDK core. Match on the name so a denial is never
    mistaken for a transport error.
    """
    if PermissionDenied is not None and isinstance(exc, PermissionDenied):
        return True
    return type(exc).__name__ == "PermissionDenied"


def as_handler(fn: Callable) -> Callable[[Dict[str, Any]], Any]:
    """
    Adapt a tool function into a MACAW handler.

    Handlers receive a params dict and run on MACAW's handler pool after the PEP
    has allowed the call. Async tools are driven to completion there - the pool
    thread has no event loop of its own.
    """

    def handler(params: Dict[str, Any]) -> Any:
        result = fn(**params)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return result

    return handler


def _acknowledge(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handler for resources MACAW authorizes but does not execute."""
    return {"authorized": True}


class MacawBinding:
    """Owns the MACAWClient and turns every seam into an invoke_tool call."""

    def __init__(
        self,
        app_name: Optional[str] = None,
        intent_policy: Optional[Dict[str, Any]] = None,
        jwt_token: Optional[str] = None,
        user_name: Optional[str] = None,
    ):
        if MACAWClient is None:
            raise ImportError(
                "MACAWClient not installed. Download from https://console.macawsecurity.ai"
            )

        self.app_name = app_name or "secure-pydantic-app"
        self._mode = "user" if jwt_token else "service"
        self._registered = set()
        self._models = {}  # model_name -> wrapped pydantic_ai Model

        # The model seam. Declaring "messages" as a prompt is what makes
        # invoke_tool create authenticated prompts for the conversation.
        self.tools = {
            f"tool:{self.app_name}/generate": {
                "handler": self._handle_generate,
                "prompts": ["messages"],
            }
        }

        identity = (
            {"user_name": user_name, "iam_token": jwt_token, "agent_type": "user"}
            if jwt_token
            else {}
        )

        self.macaw_client = MACAWClient(
            app_name=self.app_name,
            app_version="1.0.0",
            intent_policy=intent_policy or {},
            tools=self.tools,
            **identity,
        )

        if self.macaw_client.register():
            self.server_id = self.macaw_client.agent_id
            logger.info(
                "SecureAgent registered as %s (mode: %s)", self.server_id, self._mode
            )
        else:
            raise RuntimeError("Failed to register with MACAW LocalAgent")

    # ------------------------------------------------------------------ users

    def for_user(self, user_client: Any) -> "UserBinding":
        """Return a binding that issues invocations as `user_client`."""
        if self._mode != "service":
            raise ValueError("bind_to_user() is only valid on a service-mode agent")
        if not hasattr(user_client, "agent_id") or not hasattr(user_client, "invoke_tool"):
            raise ValueError("bind_to_user() requires a valid MACAWClient instance")
        if not getattr(user_client, "registered", False):
            raise ValueError(
                "bind_to_user() requires a registered MACAWClient. Call register() first."
            )

        agent_type = getattr(user_client, "agent_type", None)
        if agent_type and agent_type != "user":
            logger.warning(
                "bind_to_user() called with agent_type=%r (expected 'user'). "
                "User identity and policy enforcement may not work as expected.",
                agent_type,
            )

        return UserBinding(self, user_client)

    # -------------------------------------------------------------- resources

    def register_tool(self, name: str, fn: Callable) -> str:
        """Register a callable MACAW will dispatch."""
        return self._register(name, as_handler(fn))

    def register_ack(self, name: str) -> str:
        """Register a resource MACAW authorizes but does not execute."""
        return self._register(name, _acknowledge)

    def register_model(self, wrapped) -> None:
        """Make `wrapped` reachable by the tool:<app>/generate handler."""
        self._models[wrapped.model_name] = wrapped

    def _register(self, name: str, handler: Callable) -> str:
        mapl_name = f"tool:{self.app_name}/{name}"
        if mapl_name not in self._registered:
            self.macaw_client.register_tool(mapl_name, handler)
            self._registered.add(mapl_name)
            logger.info("Registered resource: %s", mapl_name)
        return mapl_name

    # ------------------------------------------------------------- invocation

    def invoke(self, resource: str, params: Dict[str, Any], **kwargs) -> Any:
        """
        Invoke a resource through MACAW.

        Blocking: policy, signing, and audit all happen inside this call. Callers
        on an event loop must run it off-thread.
        """
        return self.issuer.invoke_tool(
            tool_name=f"tool:{self.app_name}/{resource}",
            parameters=params,
            target_agent=self.server_id,
            **kwargs,
        )

    @property
    def issuer(self):
        """Client that issues invocations. UserBinding overrides this."""
        return self.macaw_client

    # ------------------------------------------------------------ model seam

    def _handle_generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handler for tool:<app>/generate.

        Runs on MACAW's handler pool once the PEP allows the call, so the
        provider request and its response both pass through invoke_tool - the
        same path an owned tool call takes.

        Streaming authorizes here and streams from the wrapped model in the
        caller, so no stream event is re-serialized on the way back.
        """
        from pydantic import TypeAdapter
        from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse
        from pydantic_ai.models import ModelRequestParameters

        p = dict(params)
        if p.get("stream"):
            return {"authorized": True}

        model_name = p.pop("model")
        messages = ModelMessagesTypeAdapter.validate_python(p.pop("messages"))
        request_parameters = TypeAdapter(ModelRequestParameters).validate_python(
            p.pop(REQUEST_PARAMETERS_KEY)
        )
        p.pop("native_tools", None)  # policy input; not a model setting

        wrapped = self._models.get(model_name)
        if wrapped is None:
            raise ValueError(f"No model registered under {model_name!r}")

        response = asyncio.run(wrapped.request(messages, p or None, request_parameters))
        return TypeAdapter(ModelResponse).dump_python(response, mode="json")


class UserBinding:
    """A MacawBinding that issues invocations as a specific user."""

    def __init__(self, base: MacawBinding, user_client: Any):
        self._base = base
        self._user_client = user_client

    @property
    def issuer(self):
        return self._user_client

    @property
    def app_name(self) -> str:
        return self._base.app_name

    @property
    def server_id(self) -> str:
        return self._base.server_id

    def register_tool(self, name: str, fn: Callable) -> str:
        return self._base.register_tool(name, fn)

    def register_ack(self, name: str) -> str:
        return self._base.register_ack(name)

    def register_model(self, wrapped) -> None:
        self._base.register_model(wrapped)

    def invoke(self, resource: str, params: Dict[str, Any], **kwargs) -> Any:
        return self._user_client.invoke_tool(
            tool_name=f"tool:{self.app_name}/{resource}",
            parameters=params,
            target_agent=self.server_id,
            **kwargs,
        )
