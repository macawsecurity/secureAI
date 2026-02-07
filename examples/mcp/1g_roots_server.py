#!/usr/bin/env python3
"""
Example 1g: MCP Roots via MAPL - SERVER

Demonstrates declaring filesystem roots that constrain server access.

Roots are declared via SecureMCP(roots=[...]) and translated to
MAPL resource policies. Tools use ctx.get_roots() to check boundaries.

Run this server, then run 1g_roots_client.py in another terminal.
"""

import os
from pathlib import Path

from macaw_adapters.mcp import SecureMCP, Context

# Setup test directory
DEMO_DIR = "/tmp/securemcp-roots-demo"
os.makedirs(DEMO_DIR, exist_ok=True)
(Path(DEMO_DIR) / "allowed.txt").write_text("This file is in an allowed root.")

# Create server with declared roots
mcp = SecureMCP(
    "roots-demo",
    roots=[DEMO_DIR]  # Only this directory is accessible
)


@mcp.tool(description="List files in directory")
def list_dir(ctx: Context, path: str) -> dict:
    """List directory contents (respects root boundaries)."""
    ctx.info(f"Listing: {path}")
    roots = ctx.get_roots()
    path = os.path.abspath(path)

    # Check boundaries
    if not any(path.startswith(os.path.abspath(r)) for r in roots):
        ctx.warning(f"Access denied: {path}")
        ctx.audit(action="list_dir", target=path, outcome="denied")
        return {"error": "Access denied - outside roots", "allowed_roots": roots}

    if os.path.exists(path):
        entries = os.listdir(path)
        ctx.audit(action="list_dir", target=path, outcome="success")
        return {"path": path, "entries": entries}
    return {"error": "Path not found"}


@mcp.tool(description="Read a file")
def read_file(ctx: Context, path: str) -> dict:
    """Read file contents (respects root boundaries)."""
    ctx.info(f"Reading: {path}")
    roots = ctx.get_roots()
    path = os.path.abspath(path)

    if not any(path.startswith(os.path.abspath(r)) for r in roots):
        ctx.audit(action="read_file", target=path, outcome="denied")
        return {"error": "Access denied - outside roots"}

    if os.path.isfile(path):
        content = Path(path).read_text()
        ctx.audit(action="read_file", target=path, outcome="success")
        return {"path": path, "content": content}
    return {"error": "File not found"}


if __name__ == "__main__":
    print("=" * 50)
    print("Example 1g: Roots Demo Server")
    print("=" * 50)
    print()
    print("Tools: list_dir, read_file")
    print()
    print("Declared Roots (via MAPL):")
    for root in mcp.roots:
        print(f"  - {root}")
    print()
    print(f"Test file: {DEMO_DIR}/allowed.txt")
    print()
    print("Run client: python3 1g_roots_client.py")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)
    mcp.run()
