"""
Governing provider-side (native) tools.

Native tools such as web search and code execution run at the model provider,
not in your process, so they never reach a toolset and cannot be intercepted
after the fact. SecureAgent reports the native tools offered on each request as
a parameter of tool:<app>/generate, so MAPL can refuse the call before it is
made:

    "constraints": {
        "denied_parameters": {
            "tool:pydantic-agent/generate": {"native_tools": ["*web_search*"]}
        }
    }

The denial happens before the provider is contacted, so nothing is searched.

Prerequisites:
    export OPENAI_API_KEY=sk-...
    MACAW LocalAgent running
    Workspace policy allowing tool:pydantic-agent/*

Run:
    python pydanticai_1c_native_tools.py
"""

import os
import sys

from macaw_client import PermissionDenied
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.native_tools import WebSearchTool

from macaw_adapters.pydantic_ai import SecureAgent

APP_NAME = "pydantic-agent"
GENERATE = f"tool:{APP_NAME}/generate"

ALLOW = {"resources": [GENERATE]}
DENY_WEB_SEARCH = {
    "resources": [GENERATE],
    "constraints": {
        "denied_parameters": {GENERATE: {"native_tools": ["*web_search*"]}}
    },
}


def run(label: str, policy: dict, capabilities: list) -> None:
    agent = SecureAgent(
        OpenAIResponsesModel("gpt-4o-mini"),
        app_name=APP_NAME,
        intent_policy=policy,
        capabilities=capabilities,
    )
    print(f"\n--- {label} ---")
    try:
        result = agent.run_sync("What is the capital of France? One word.")
        print(f"  allowed: {result.output}")
    except PermissionDenied as e:
        print(f"  denied by MACAW: {e}")
        print("  The provider was never called, so nothing was searched.")


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY first:")
        print("  export OPENAI_API_KEY=sk-...")
        return 1

    run("No native tools offered; policy denies web_search", DENY_WEB_SEARCH, [])
    run(
        "web_search offered; policy denies it",
        DENY_WEB_SEARCH,
        [NativeTool(WebSearchTool())],
    )
    run("web_search offered; policy permits it", ALLOW, [NativeTool(WebSearchTool())])

    return 0


if __name__ == "__main__":
    sys.exit(main())
