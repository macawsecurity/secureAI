#!/usr/bin/env python3
"""
Example: SecureMCPProxy with Databricks MCP Server

Connect to Databricks MCP servers with MACAW security for:
- Vector Search (RAG queries)
- Genie Space (natural language data analysis)
- SQL execution
- Unity Catalog functions

Databricks MCP Options:
1. Databricks Managed MCP Servers - HTTP-based, Unity Catalog integrated
2. Community server (databricks-mcp-server PyPI) - stdio-based

This example focuses on Databricks Managed MCP Servers (HTTP).

Prerequisites:
1. Databricks workspace (community edition is free)
2. MCP servers enabled in workspace
3. MACAW LocalAgent running
4. Install: pip install macaw-adapters[mcp-proxy]

References:
- Managed MCP: https://docs.databricks.com/aws/en/generative-ai/mcp/managed-mcp
- Unity Catalog: https://docs.databricks.com/en/data-governance/unity-catalog/

Usage:
    export DATABRICKS_HOST="https://your-workspace.databricks.com"
    export DATABRICKS_TOKEN="dapi..."
    python 2d_proxy_databricks.py
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_databricks_sql_proxy():
    """
    Connect to Databricks SQL MCP server through SecureMCPProxy.

    Databricks Managed MCP servers use OAuth/PAT authentication
    and expose SQL, Vector Search, Genie, and UC Functions.
    """
    from macaw_adapters.mcp import SecureMCPProxy

    # Databricks workspace URL and token
    workspace_host = os.environ.get(
        "DATABRICKS_HOST",
        "https://your-workspace.databricks.com"
    )
    token = os.environ.get("DATABRICKS_TOKEN", "")

    # Databricks SQL MCP endpoint
    # Pattern: https://<workspace>/api/2.0/mcp/sql
    sql_mcp_url = f"{workspace_host}/api/2.0/mcp/sql"

    # Create proxy with Databricks PAT authentication
    proxy = SecureMCPProxy(
        app_name="databricks-sql",
        upstream_url=sql_mcp_url,
        upstream_auth={
            "type": "bearer",
            "token": token
        }
    )

    print(f"\n{proxy}")

    # List discovered tools
    print("\nDiscovered Databricks SQL tools:")
    for tool in proxy.list_tools():
        print(f"  - {tool['name']}: {tool.get('description', '')[:60]}...")

    # Example: Execute SQL query
    try:
        result = proxy.call_tool("execute_sql", {
            "query": "SELECT current_user(), current_catalog(), current_schema()"
        })
        print(f"\nSQL result: {result}")
    except ValueError as e:
        print(f"\nSQL tool not available: {e}")
    except Exception as e:
        print(f"\nSQL error: {e}")


def example_databricks_vector_search():
    """
    Connect to Databricks Vector Search MCP server.

    Use case: RAG applications querying indexed documents.
    """
    from macaw_adapters.mcp import SecureMCPProxy

    workspace_host = os.environ.get("DATABRICKS_HOST", "https://your-workspace.databricks.com")
    token = os.environ.get("DATABRICKS_TOKEN", "")

    # Vector Search MCP endpoint
    # Pattern: https://<workspace>/api/2.0/mcp/vector-search/{catalog}/{schema}/{index}
    catalog = os.environ.get("DATABRICKS_CATALOG", "main")
    schema = os.environ.get("DATABRICKS_SCHEMA", "default")
    index_name = os.environ.get("DATABRICKS_VS_INDEX", "documents_index")

    vs_mcp_url = f"{workspace_host}/api/2.0/mcp/vector-search/{catalog}/{schema}/{index_name}"

    proxy = SecureMCPProxy(
        app_name="databricks-vector-search",
        upstream_url=vs_mcp_url,
        upstream_auth={"type": "bearer", "token": token}
    )

    print(f"\n{proxy}")

    # Example: Search documents
    try:
        result = proxy.call_tool("search", {
            "query": "How do I configure Unity Catalog?",
            "num_results": 5
        })
        print(f"\nVector search result: {result}")
    except ValueError as e:
        print(f"\nSearch tool not available: {e}")
    except Exception as e:
        print(f"\nSearch error: {e}")


def example_databricks_genie():
    """
    Connect to Databricks Genie Space MCP server.

    Use case: Natural language queries over structured data.
    """
    from macaw_adapters.mcp import SecureMCPProxy

    workspace_host = os.environ.get("DATABRICKS_HOST", "https://your-workspace.databricks.com")
    token = os.environ.get("DATABRICKS_TOKEN", "")

    # Genie Space MCP endpoint
    # Pattern: https://<workspace>/api/2.0/mcp/genie/{genie_space_id}
    genie_space_id = os.environ.get("DATABRICKS_GENIE_SPACE", "your-genie-space-id")

    genie_mcp_url = f"{workspace_host}/api/2.0/mcp/genie/{genie_space_id}"

    proxy = SecureMCPProxy(
        app_name="databricks-genie",
        upstream_url=genie_mcp_url,
        upstream_auth={"type": "bearer", "token": token}
    )

    print(f"\n{proxy}")

    # Example: Ask Genie a question
    try:
        result = proxy.call_tool("ask", {
            "question": "What were the top 5 products by revenue last quarter?"
        })
        print(f"\nGenie result: {result}")
    except ValueError as e:
        print(f"\nGenie tool not available: {e}")
    except Exception as e:
        print(f"\nGenie error: {e}")


def example_databricks_multi_user():
    """
    Multi-user pattern: data analysts with different Unity Catalog permissions.

    Use case: Data platform where teams have different catalog access.
    """
    from macaw_adapters.mcp import SecureMCPProxy
    from macaw_client import MACAWClient

    workspace_host = os.environ.get("DATABRICKS_HOST", "https://your-workspace.databricks.com")
    token = os.environ.get("DATABRICKS_TOKEN", "")

    # Service creates shared proxy
    proxy = SecureMCPProxy(
        app_name="databricks-data-platform",
        upstream_url=f"{workspace_host}/api/2.0/mcp/sql",
        upstream_auth={"type": "bearer", "token": token}
    )

    # Data Engineer - full access
    engineer = MACAWClient(
        user_name="data-engineer-sam",
        jwt_token=os.environ.get("SAM_JWT", "sam-jwt"),
        agent_type="user"
    )
    engineer.register()
    engineer_proxy = proxy.bind_to_user(engineer)

    # Analyst - read-only access
    analyst = MACAWClient(
        user_name="analyst-kim",
        jwt_token=os.environ.get("KIM_JWT", "kim-jwt"),
        agent_type="user"
    )
    analyst.register()
    analyst_proxy = proxy.bind_to_user(analyst)

    print("\nMulti-user Databricks access:")
    print(f"  Engineer (Sam): {engineer_proxy}")
    print(f"  Analyst (Kim): {analyst_proxy}")

    # Sam can create tables
    try:
        result = engineer_proxy.call_tool("execute_sql", {
            "statement": "CREATE TABLE IF NOT EXISTS analytics.metrics (id INT, value DOUBLE)"
        })
        print(f"\nSam's CREATE result: {result}")
    except PermissionError as e:
        print(f"\nSam denied: {e}")
    except Exception as e:
        print(f"\nSam error: {e}")

    # Kim can only query
    try:
        result = analyst_proxy.call_tool("execute_sql", {
            "statement": "SELECT * FROM analytics.metrics LIMIT 10"
        })
        print(f"\nKim's SELECT result: {result}")
    except PermissionError as e:
        print(f"\nKim denied: {e}")
    except Exception as e:
        print(f"\nKim error: {e}")


def setup_instructions():
    """Print setup instructions for Databricks MCP."""
    print("""
================================================================================
Databricks Managed MCP Server Setup
================================================================================

1. Get Databricks workspace:
   - Enterprise: Contact Databricks
   - Community Edition (free): https://community.cloud.databricks.com

2. Enable MCP in your workspace:
   - Go to: Workspace > Agents > MCP Servers
   - View available MCP endpoints

3. Create Personal Access Token (PAT):
   - User Settings > Developer > Access Tokens
   - Generate new token with appropriate permissions

4. Set environment variables:
   export DATABRICKS_HOST="https://your-workspace.databricks.com"
   export DATABRICKS_TOKEN="dapi..."

5. MCP Endpoint Patterns:
   - SQL: {host}/api/2.0/mcp/sql
   - Vector Search: {host}/api/2.0/mcp/vector-search/{catalog}/{schema}/{index}
   - Genie: {host}/api/2.0/mcp/genie/{genie_space_id}
   - UC Functions: {host}/api/2.0/mcp/functions/{catalog}/{schema}/{function}

6. Run this example:
   python 2d_proxy_databricks.py


ALTERNATIVE: Community MCP Server (stdio-based)
-----------------------------------------------

For local development with stdio transport:

1. Install: pip install databricks-mcp-server
2. Run: uvx databricks-mcp-server@latest

Note: stdio servers require an HTTP bridge (mcp-proxy) for SecureMCPProxy.

================================================================================
""")


if __name__ == "__main__":
    print("=" * 60)
    print("SecureMCPProxy + Databricks MCP Server")
    print("=" * 60)

    setup_instructions()

    print("\n--- Example: Databricks SQL Proxy ---")
    try:
        example_databricks_sql_proxy()
    except ConnectionError as e:
        print(f"\nConnection failed: {e}")
        print("Make sure Databricks workspace is accessible and MCP is enabled.")

    # Uncomment to test other examples:
    # print("\n--- Example: Vector Search ---")
    # example_databricks_vector_search()

    # print("\n--- Example: Genie Space ---")
    # example_databricks_genie()

    # print("\n--- Example: Multi-User Access ---")
    # example_databricks_multi_user()
