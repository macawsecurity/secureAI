#!/usr/bin/env python3
"""
Example: SecureMCPProxy with Salesforce MCP Server

Connect to Salesforce MCP servers with MACAW security for:
- SOQL queries
- Record CRUD operations
- Metadata operations
- Apex execution

Salesforce MCP Options:
1. Salesforce Hosted MCP Servers (Beta) - HTTP-based, enterprise-grade
2. Community servers (kablewy/salesforce-mcp-server) - HTTP-based
3. Salesforce DX MCP (stdio-based - requires mcp-proxy bridge)

This example focuses on HTTP-based Salesforce MCP servers.

Prerequisites:
1. Salesforce Developer org (free: https://developer.salesforce.com/signup)
2. Salesforce MCP server running with HTTP transport
3. MACAW LocalAgent running
4. Install: pip install macaw-adapters[mcp-proxy]

References:
- Hosted MCP: https://developer.salesforce.com/blogs/2025/10/salesforce-hosted-mcp-servers-are-in-beta-today
- Community: https://github.com/kablewy/salesforce-mcp-server

Usage:
    export SALESFORCE_MCP_URL="https://your-org.salesforce.com/mcp"
    export SALESFORCE_ACCESS_TOKEN="your-oauth-token"
    python 2c_proxy_salesforce.py
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_salesforce_proxy():
    """
    Connect to Salesforce MCP server through SecureMCPProxy.

    This example shows the pattern for Salesforce Hosted MCP Servers
    or community HTTP-based Salesforce MCP implementations.
    """
    from macaw_adapters.mcp import SecureMCPProxy

    # Salesforce MCP server URL
    # For Hosted MCP: https://your-org.my.salesforce.com/services/mcp
    # For Community: http://localhost:3000 (or wherever you run it)
    upstream_url = os.environ.get(
        "SALESFORCE_MCP_URL",
        "http://localhost:3000/mcp"
    )

    # OAuth access token from Salesforce
    access_token = os.environ.get("SALESFORCE_ACCESS_TOKEN", "")

    # Create proxy with OAuth authentication
    proxy = SecureMCPProxy(
        app_name="salesforce-mcp",
        upstream_url=upstream_url,
        upstream_auth={
            "type": "bearer",
            "token": access_token
        } if access_token else None
    )

    print(f"\n{proxy}")

    # List discovered Salesforce tools
    print("\nDiscovered Salesforce tools:")
    for tool in proxy.list_tools():
        print(f"  - {tool['name']}: {tool.get('description', '')[:60]}...")

    # Example: Query accounts
    try:
        result = proxy.call_tool("query", {
            "soql": "SELECT Id, Name, Industry FROM Account LIMIT 5"
        })
        print(f"\nAccount query result: {result}")
    except ValueError as e:
        print(f"\nQuery tool not available: {e}")
    except Exception as e:
        print(f"\nQuery error: {e}")

    # Example: Get record
    try:
        result = proxy.call_tool("get_record", {
            "object_type": "Account",
            "record_id": "001XXXXXXXXXXXX"
        })
        print(f"\nRecord result: {result}")
    except ValueError as e:
        print(f"\nGet record not available: {e}")
    except Exception as e:
        print(f"\nGet record error: {e}")


def example_salesforce_multi_user():
    """
    Multi-user pattern: CRM users with different access levels.

    Use case: Sales app where reps see their accounts, managers see all.
    """
    from macaw_adapters.mcp import SecureMCPProxy
    from macaw_client import MACAWClient

    # Service creates shared proxy to Salesforce
    proxy = SecureMCPProxy(
        app_name="salesforce-crm",
        upstream_url=os.environ.get("SALESFORCE_MCP_URL", "http://localhost:3000/mcp"),
        upstream_auth={
            "type": "bearer",
            "token": os.environ.get("SALESFORCE_SERVICE_TOKEN", "")
        }
    )

    # Sales Rep - can only query their own accounts
    rep = MACAWClient(
        user_name="sales-rep-jane",
        jwt_token=os.environ.get("JANE_JWT", "jane-jwt"),
        agent_type="user"
    )
    rep.register()
    rep_proxy = proxy.bind_to_user(rep)

    # Manager - can query all accounts
    manager = MACAWClient(
        user_name="sales-manager-tom",
        jwt_token=os.environ.get("TOM_JWT", "tom-jwt"),
        agent_type="user"
    )
    manager.register()
    manager_proxy = proxy.bind_to_user(manager)

    print("\nMulti-user Salesforce access:")
    print(f"  Rep (Jane): {rep_proxy}")
    print(f"  Manager (Tom): {manager_proxy}")

    # Jane's query - MACAW policy enforces "OwnerId = current_user"
    try:
        result = rep_proxy.call_tool("query", {
            "soql": "SELECT Id, Name FROM Account WHERE OwnerId = :userId LIMIT 10"
        })
        print(f"\nJane's accounts: {result}")
    except PermissionError as e:
        print(f"\nJane denied: {e}")
    except Exception as e:
        print(f"\nJane error: {e}")

    # Tom's query - Manager policy allows broader access
    try:
        result = manager_proxy.call_tool("query", {
            "soql": "SELECT Id, Name, OwnerId FROM Account LIMIT 10"
        })
        print(f"\nTom's view (all accounts): {result}")
    except PermissionError as e:
        print(f"\nTom denied: {e}")
    except Exception as e:
        print(f"\nTom error: {e}")


def example_salesforce_with_policy():
    """
    Salesforce proxy with custom MACAW policy.

    Define what operations are allowed at the MACAW layer,
    independent of Salesforce's own permissions.
    """
    from macaw_adapters.mcp import SecureMCPProxy

    # Policy: Only allow read operations, no creates/updates/deletes
    read_only_policy = {
        "rules": [
            {
                "action": "allow",
                "tools": ["query", "get_record", "describe_object"],
                "description": "Allow read-only Salesforce operations"
            },
            {
                "action": "deny",
                "tools": ["create_record", "update_record", "delete_record"],
                "description": "Block write operations"
            }
        ]
    }

    proxy = SecureMCPProxy(
        app_name="salesforce-readonly",
        upstream_url=os.environ.get("SALESFORCE_MCP_URL", "http://localhost:3000/mcp"),
        upstream_auth={
            "type": "bearer",
            "token": os.environ.get("SALESFORCE_ACCESS_TOKEN", "")
        },
        intent_policy=read_only_policy
    )

    print(f"\nRead-only Salesforce proxy: {proxy}")

    # This should work
    try:
        result = proxy.call_tool("query", {"soql": "SELECT Id FROM Account LIMIT 1"})
        print(f"Query allowed: {result}")
    except Exception as e:
        print(f"Query error: {e}")

    # This should be denied by MACAW policy
    try:
        result = proxy.call_tool("create_record", {
            "object_type": "Account",
            "fields": {"Name": "Test Account"}
        })
        print(f"Create result: {result}")
    except PermissionError as e:
        print(f"Create denied by MACAW policy: {e}")
    except ValueError as e:
        print(f"Create tool not available: {e}")


def setup_instructions():
    """Print setup instructions for Salesforce MCP."""
    print("""
================================================================================
Salesforce MCP Server Setup
================================================================================

OPTION 1: Community MCP Server (Recommended for testing)
---------------------------------------------------------

1. Get free Salesforce Developer org:
   https://developer.salesforce.com/signup

2. Create Connected App for OAuth:
   Setup > App Manager > New Connected App
   - Enable OAuth, add "api" scope
   - Note Consumer Key and Secret

3. Run community Salesforce MCP server:
   git clone https://github.com/kablewy/salesforce-mcp-server
   cd salesforce-mcp-server
   npm install
   # Configure with your Salesforce credentials
   npm start

4. Get OAuth access token (example using jsforce):
   const conn = new jsforce.Connection({ loginUrl: 'https://login.salesforce.com' });
   await conn.login(username, password + securityToken);
   console.log(conn.accessToken);

5. Run this example:
   export SALESFORCE_MCP_URL="http://localhost:3000/mcp"
   export SALESFORCE_ACCESS_TOKEN="your-access-token"
   python 2c_proxy_salesforce.py


OPTION 2: Salesforce Hosted MCP (Beta - Enterprise)
---------------------------------------------------

1. Contact Salesforce for Hosted MCP beta access
2. Enable MCP in your org's setup
3. Configure MCP server endpoint in your org
4. Use org's MCP URL directly

Reference: https://developer.salesforce.com/blogs/2025/10/salesforce-hosted-mcp-servers-are-in-beta-today


OPTION 3: Salesforce DX MCP (stdio - requires bridge)
-----------------------------------------------------

The Salesforce DX CLI MCP server uses stdio transport.
To use with SecureMCPProxy, you need an HTTP bridge:

1. Install mcp-proxy: pip install mcp-proxy
2. Run: mcp-proxy --command "npx @salesforce/mcp --orgs DEFAULT"
3. Point SecureMCPProxy at the HTTP endpoint

================================================================================
""")


if __name__ == "__main__":
    print("=" * 60)
    print("SecureMCPProxy + Salesforce MCP Server")
    print("=" * 60)

    setup_instructions()

    print("\n--- Example: Basic Salesforce Proxy ---")
    try:
        example_salesforce_proxy()
    except ConnectionError as e:
        print(f"\nConnection failed: {e}")
        print("Make sure Salesforce MCP server is running.")

    # Uncomment to test other examples:
    # print("\n--- Example: Multi-User Salesforce Access ---")
    # example_salesforce_multi_user()

    # print("\n--- Example: Read-Only Policy ---")
    # example_salesforce_with_policy()
