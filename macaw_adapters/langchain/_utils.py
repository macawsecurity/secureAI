"""
Shared utilities for SecureLangChain adapter.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from macaw_client import MACAWClient

logger = logging.getLogger(__name__)

# Global registry of active MACAW clients (for cleanup)
_active_clients: Dict[str, MACAWClient] = {}


def get_or_create_client(
    client_id: str,
    intent_policy: Optional[Dict[str, Any]] = None,
    tools: Optional[Dict[str, Any]] = None
) -> Optional[MACAWClient]:
    """
    Get existing MACAW client or create a new one.

    Args:
        client_id: Unique identifier for the client
        intent_policy: Optional policy for the client
        tools: Optional unified tools config {name: {handler, prompts, ...}}

    Returns:
        MACAWClient instance or None if registration fails
    """
    if client_id not in _active_clients:
        client = MACAWClient(
            app_name=client_id,
            app_version="1.0.0",
            agent_type="agent",
            intent_policy=intent_policy,
            tools=tools
        )
        if client.register():
            _active_clients[client_id] = client
            logger.debug(f"Created MACAWClient: {client_id}")
        else:
            logger.warning(f"Failed to register MACAWClient: {client_id}")
            return None
    return _active_clients.get(client_id)


def register_client(client_id: str, client: MACAWClient) -> None:
    """Register an existing client for cleanup tracking."""
    _active_clients[client_id] = client


def _is_shutdown_error(e: Exception) -> bool:
    """Check if error is due to Python interpreter shutdown."""
    msg = str(e).lower()
    return "interpreter shutdown" in msg or "cannot schedule" in msg


def cleanup_all() -> None:
    """Clean up all active MACAW clients."""
    for client_id, client in list(_active_clients.items()):
        try:
            client.unregister()
            logger.debug(f"Cleaned up MACAWClient: {client_id}")
        except Exception as e:
            # Ignore errors during Python shutdown - process is ending anyway
            if not _is_shutdown_error(e):
                logger.error(f"Error cleaning up {client_id}: {e}")
    _active_clients.clear()


def cleanup_client(client_id: str) -> None:
    """Clean up a specific MACAW client."""
    if client_id in _active_clients:
        try:
            _active_clients[client_id].unregister()
            del _active_clients[client_id]
            logger.debug(f"Cleaned up MACAWClient: {client_id}")
        except Exception as e:
            # Ignore errors during Python shutdown - process is ending anyway
            if not _is_shutdown_error(e):
                logger.error(f"Error cleaning up {client_id}: {e}")
