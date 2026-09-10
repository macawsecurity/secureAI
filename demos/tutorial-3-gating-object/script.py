"""
 =============================================================================
 Register this proxy as a stdio MCP server in Claude Code (TEST creds inlined).
 bash -lc form: activates the venv so `python` = the right interpreter + env.

   claude mcp add alation-databricks --scope user \
     -- bash -lc 'source /path/to/macaw-client && \
        export MACAW_HOME=" /path/to/macaw-client" && \
        export ALATION_MCP_URL=  && \
        export ALATION_BASE_URL=  && \
        export ALATION_TOKEN=  && \
        cd /path/to/file && \
        python script.py stdio'

 Remove with:  claude mcp remove alation-databricks
 =============================================================================
"""


import os
import sys
import logging


from macaw_adapters.mcp import SecureMCPProxy 





ALATION_MCP_URL = os.environ.get("ALATION_MCP_URL")
ALATION_TOKEN = os.environ.get("ALATION_TOKEN")

if not ALATION_MCP_URL or not ALATION_TOKEN:
    sys.exit("Make sure ALATION MCP URL and TOKEN are set")


proxy = SecureMCPProxy(
    app_name="alation",
    upstream_url=ALATION_MCP_URL,
    upstream_auth={"type": "bearer", "token":ALATION_TOKEN}
)


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utility"))
from alation_verifier import AlationSQLGuardVerifier
proxy.macaw_client.agent.verification_pipeline.add_verifier(AlationSQLGuardVerifier(), priority=20)


logging.info("Upstream Server serving %d tools",len(proxy.list_tools()))

transport  = sys.argv[1] if len(sys.argv) > 1 else "stdio"
port  = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
proxy.run(transport=transport, port=port) 