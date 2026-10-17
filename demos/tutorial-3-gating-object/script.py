"""
script.py -- SecureMCPProxy in front of the Databricks managed SQL MCP server.

Register it as a stdio MCP server in Claude Code:

  claude mcp add databricks-object-proxy --scope user \
    -- bash -lc 'source <path to .venv>/bin/activate && \
       export MACAW_HOME="<path to macaw-client-*>" && \
       export DATABRICKS_MCP_URL="https://<workspace-host>/api/2.0/mcp/sql" && \
       export DATABRICKS_TOKEN="<your token>" && \
       cd <path to tutorial-3-gating-object> && \
       python script.py'

Remove with:  claude mcp remove databricks-object-proxy
"""

import os
import sys
import logging

from macaw_adapters.mcp import SecureMCPProxy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utility"))
from databricks_verifier import DatabricksSQLVerifier, DatabricksTableVerifier

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

DATABRICKS_TOKEN   = os.environ["DATABRICKS_TOKEN"]
DATABRICKS_MCP_URL = os.environ["DATABRICKS_MCP_URL"]

proxy = SecureMCPProxy(
    app_name="databricks-object-proxy",
    upstream_url=DATABRICKS_MCP_URL,
    upstream_auth={"type": "bearer", "token": DATABRICKS_TOKEN},
)
proxy.macaw_client.agent.verification_pipeline.add_verifier(DatabricksTableVerifier(), priority=10)
proxy.macaw_client.agent.verification_pipeline.add_verifier(DatabricksSQLVerifier(), priority=20)

proxy.run()
