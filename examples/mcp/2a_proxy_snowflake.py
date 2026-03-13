#!/usr/bin/env python3
"""
Example: SecureMCPProxy with Snowflake MCP Server

Connect to Snowflake's MCP server with MACAW security for:
- Cortex AI (search, analyst, agent)
- SQL execution
- Object management
- Semantic views

Prerequisites:
1. Snowflake account (free trial: https://signup.snowflake.com)
2. Snowflake Labs MCP server running with HTTP transport:
   uvx snowflake-labs-mcp --service-config-file config.yaml --transport streamable-http
3. MACAW LocalAgent running
4. Install: pip install macaw-adapters[mcp-proxy]

Reference: https://github.com/Snowflake-Labs/mcp

Usage:
    # Set environment variables
    export SNOWFLAKE_MCP_URL="http://localhost:9000/snowflake-mcp"
    export SNOWFLAKE_ACCOUNT="your-account"

    python 2b_proxy_snowflake.py
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_snowflake_proxy():
    """
    Connect to Snowflake MCP server through SecureMCPProxy.

    Snowflake Labs MCP supports HTTP transport, making it compatible
    with SecureMCPProxy's streamable_http_client.
    """
    from macaw_adapters.mcp import SecureMCPProxy

    # Snowflake MCP server URL (running with --transport streamable-http)
    upstream_url = os.environ.get(
        "SNOWFLAKE_MCP_URL",
        "http://localhost:9000/mcp"
    )

    # Create proxy - connects to Snowflake MCP, wraps with MACAW security
    # Note: Snowflake auth is handled by the MCP server itself via env vars
    # (SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, SNOWFLAKE_ACCOUNT, etc.)
    proxy = SecureMCPProxy(
        app_name="snowflake-mcp",
        upstream_url=upstream_url,
        # No upstream_auth needed - Snowflake MCP server handles auth internally
    )

    print(f"\n{proxy}")

    # List discovered tools from Snowflake
    print("\nDiscovered Snowflake tools:")
    for tool in proxy.list_tools():
        print(f"  - {tool['name']}: {tool.get('description', '')[:60]}...")

    # Example: Run SQL query
    try:
        result = proxy.call_tool("run_snowflake_query", {
            "statement": "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_DATABASE()"
        })
        print(f"\nSQL result: {result}")
    except ValueError as e:
        print(f"\nSQL not available: {e}")
    except Exception as e:
        print(f"\nSQL error: {e}")

    # Example: List databases
    try:
        result = proxy.call_tool("list_objects", {
            "object_type": "database"
        })
        # Result is a dict with 'result' key
        content = result.get('result', result) if isinstance(result, dict) else result
        preview = str(content)[:300] if content else "(empty)"
        print(f"\nList databases result: {preview}...")
    except ValueError as e:
        print(f"\nList objects not available: {e}")
    except Exception as e:
        print(f"\nList objects error: {e}")


def example_snowflake_multi_user():
    """
    Multi-user pattern: different users query Snowflake with their own policies.

    Use case: Data platform where analysts have different access levels.
    """
    from macaw_adapters.mcp import SecureMCPProxy
    from macaw_client import MACAWClient

    # Service creates shared proxy to Snowflake
    proxy = SecureMCPProxy(
        app_name="snowflake-data-platform",
        upstream_url=os.environ.get("SNOWFLAKE_MCP_URL", "http://localhost:9000/snowflake-mcp"),
    )

    # Analyst Alice - has access to sales data
    alice = MACAWClient(
        user_name="alice",
        jwt_token=os.environ.get("ALICE_JWT", "alice-jwt"),
        agent_type="user"
    )
    alice.register()
    alice_proxy = proxy.bind_to_user(alice)

    # Analyst Bob - restricted to aggregate queries only
    bob = MACAWClient(
        user_name="bob",
        jwt_token=os.environ.get("BOB_JWT", "bob-jwt"),
        agent_type="user"
    )
    bob.register()
    bob_proxy = proxy.bind_to_user(bob)

    print("\nMulti-user Snowflake access:")
    print(f"  Alice: {alice_proxy}")
    print(f"  Bob: {bob_proxy}")

    # Alice's query - MACAW policy checked against alice's permissions
    try:
        result = alice_proxy.call_tool("execute_sql", {
            "statement": "SELECT * FROM sales.customers LIMIT 10"
        })
        print(f"\nAlice's query result: {result}")
    except PermissionError as e:
        print(f"\nAlice denied: {e}")
    except Exception as e:
        print(f"\nAlice error: {e}")

    # Bob's query - MACAW policy checked against bob's permissions
    try:
        result = bob_proxy.call_tool("execute_sql", {
            "statement": "SELECT COUNT(*) FROM sales.customers"
        })
        print(f"\nBob's query result: {result}")
    except PermissionError as e:
        print(f"\nBob denied: {e}")
    except Exception as e:
        print(f"\nBob error: {e}")


def setup_instructions():
    """Print setup instructions for Snowflake MCP server."""
    print("""
================================================================================
Snowflake MCP Server Setup
================================================================================

1. Get Snowflake Account (free 30-day trial):
   https://signup.snowflake.com

2. Create config.yaml for Snowflake MCP:

   # config.yaml
   agent_services: []

   other_services:
     object_manager: true
     query_manager: true
     semantic_manager: true

   sql_statement_permissions:
     Select: true
     Create: false
     Drop: false

3. Set Snowflake credentials:
   export SNOWFLAKE_ACCOUNT="your-account"
   export SNOWFLAKE_USER="your-user"
   export SNOWFLAKE_PASSWORD="your-password"
   export SNOWFLAKE_WAREHOUSE="COMPUTE_WH"
   export SNOWFLAKE_DATABASE="your-db"
   export SNOWFLAKE_SCHEMA="PUBLIC"

4. Run Snowflake MCP server with HTTP transport:
   uvx snowflake-labs-mcp --service-config-file config.yaml --transport streamable-http

5. Run this example:
   export SNOWFLAKE_MCP_URL="http://localhost:9000/mcp"
   python 2b_proxy_snowflake.py

================================================================================
""")


if __name__ == "__main__":
    print("=" * 60)
    print("SecureMCPProxy + Snowflake MCP Server")
    print("=" * 60)

    setup_instructions()

    print("\n--- Example: Basic Snowflake Proxy ---")
    try:
        example_snowflake_proxy()
    except ConnectionError as e:
        print(f"\nConnection failed: {e}")
        print("Make sure Snowflake MCP server is running with HTTP transport.")

    # Uncomment to test multi-user:
    # print("\n--- Example: Multi-User Snowflake Access ---")
    # example_snowflake_multi_user()
