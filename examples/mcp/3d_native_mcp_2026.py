#!/usr/bin/env python3
"""
Example 3d: MCP 2026-07-28 by hand - no client library at all.

MCP revision 2026-07-28 made the protocol stateless. There is no initialize
handshake and no Mcp-Session-Id: every request carries its own protocol version
and client capabilities in _meta, and servers answer server/discover to advertise
what they speak.

That is a good fit for MACAW, because MACAW never had connection state to lose.
Identity, policy, and the signature travel with each invocation, not with a
session - which is exactly what the spec moved toward.

This client is plain HTTP. No mcp package, no ClientSession, no handshake:

    this file --POST /mcp--> SecureMCP --invoke_tool--> LocalAgent --> PEP --> tool

Every call below is still policy-checked, signed, and audited, because the wire
format has nothing to do with where enforcement happens.

Run:
    # terminal 1 - requires mcp>=2
    python3 securemcp_calculator.py http

    # terminal 2
    python3 3d_native_mcp_2026.py
"""

import json
import sys
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8080/mcp"
PROTOCOL = "2026-07-28"

# Reserved _meta keys. Every request self-describes; there is no handshake to
# establish them once.
PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"


def rpc(method: str, params: dict | None = None, name: str | None = None) -> dict:
    """One stateless JSON-RPC call. No session, no prior state."""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {
            **(params or {}),
            "_meta": {
                PROTOCOL_VERSION: PROTOCOL,
                CLIENT_INFO: {"name": "raw-http-demo", "version": "1.0"},
                CLIENT_CAPABILITIES: {},
            },
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        # Selects the 2026-07-28 era. Without it the server answers the older
        # session-based revision for backward compatibility.
        "MCP-Protocol-Version": PROTOCOL,
        "Mcp-Method": method,
    }
    if name:
        headers["Mcp-Name"] = name

    req = urllib.request.Request(URL, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        session_id = resp.headers.get("mcp-session-id")
        text = resp.read().decode()

    # Responses may arrive as a one-event SSE stream.
    if text.startswith("event:"):
        text = "".join(l[6:] for l in text.splitlines() if l.startswith("data: "))

    payload = json.loads(text)
    if "error" in payload:
        raise RuntimeError(f"{method}: {payload['error']}")
    return {"result": payload["result"], "session_id": session_id}


def main() -> int:
    print("=" * 60)
    print(f"Raw HTTP client -> SecureMCP, protocol {PROTOCOL}")
    print("=" * 60)

    # 1. Discovery. Replaces the initialize handshake: ask what the server speaks.
    d = rpc("server/discover")
    discover, session_id = d["result"], d["session_id"]
    print(f"\nserver/discover  (session id: {session_id or 'none - stateless'})")
    print(f"  supportedVersions : {discover['supportedVersions']}")
    print(f"  capabilities      : {discover['capabilities']}")
    print(f"  serverInfo        : {discover['_meta'][ 'io.modelcontextprotocol/serverInfo']}")

    # 2. Tools. ttlMs/cacheScope are the server's caching contract with the client.
    listed = rpc("tools/list")["result"]
    print("\ntools/list")
    print(f"  resultType        : {listed['resultType']}")
    print(f"  ttlMs / cacheScope: {listed['ttlMs']} / {listed['cacheScope']}")
    print("     ttlMs=0 means do not cache. Which tools exist is an authorization")
    print("     answer, and a cached authorization answer is a stale one.")
    print(f"  tools             : {', '.join(t['name'] for t in listed['tools'])}")

    # 3. Calls. Each one is a fresh, self-describing request - and each one is
    #    policy-checked, signed, and audited by MACAW on the way through.
    print("\ntools/call (each policy-checked, signed, audited)")
    for tool, args in [
        ("add", {"a": 10, "b": 5}),
        ("divide", {"a": 100, "b": 4}),
        ("calculate", {"operation": "add", "a": 10, "b": 3}),
    ]:
        out = rpc("tools/call", {"name": tool, "arguments": args}, name=tool)["result"]
        shown = ", ".join(f"{k}={v}" for k, v in args.items())
        print(f"  {tool}({shown}) = {out['content'][0]['text']}")

    print("\n" + "=" * 60)
    print("No handshake, no session, no MCP library - and still fully enforced.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print(f"\nERROR: cannot reach {URL} ({e})")
        print("Start the server first:  python3 securemcp_calculator.py http")
        print("2026-07-28 requires mcp>=2 - check with: pip show mcp")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
