"""
Pick the native MCP endpoint binding that matches the installed MCP SDK.

mcp 2.0 ships protocol revision 2026-07-28, which changed the server handler API
(see _endpoint2.py for the specifics). The two bindings present the same serve()
contract, so SecureMCP and SecureMCPProxy call this and stay version-agnostic:
the SDK you install decides which one runs.

    pip install "mcp<2"    ->  _endpoint.py    (2025-11-25 and earlier)
    pip install "mcp>=2"   ->  _endpoint2.py   (2026-07-28)
"""

from importlib import import_module
from importlib.metadata import version


def _binding() -> str:
    """Module name of the endpoint binding for the installed SDK."""
    major = int(version("mcp").split(".")[0])
    return "._endpoint2" if major >= 2 else "._endpoint"


async def serve(*args, **kwargs) -> None:
    """Serve MACAW-registered tools over native MCP. See _endpoint.serve()."""
    return await import_module(_binding(), __package__).serve(*args, **kwargs)
