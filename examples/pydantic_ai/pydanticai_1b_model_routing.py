"""
Policy-driven model routing with FallbackModel.

Pydantic AI's FallbackModel tries each candidate in turn until one succeeds.
SecureAgent secures the candidates rather than the router, so policy sees the
model that would actually call the provider - and a MACAW denial is just another
reason to move to the next candidate.

    router = FallbackModel(
        OpenAIChatModel("gpt-4o"),        # preferred
        OpenAIChatModel("gpt-4o-mini"),   # fallback
        fallback_on=(PermissionDenied,),
    )

The same MAPL constraint therefore governs cost tier, data residency, and access
at once, and degrades instead of failing the run.

Prerequisites:
    export OPENAI_API_KEY=sk-...
    MACAW LocalAgent running
    Workspace policy allowing tool:pydantic-agent/*

Run:
    python pydanticai_1b_model_routing.py
"""

import os
import sys

from macaw_client import PermissionDenied
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel

from macaw_adapters.pydantic_ai import SecureAgent

APP_NAME = "pydantic-agent"
GENERATE = f"tool:{APP_NAME}/generate"

PREFERRED = "gpt-4o"
FALLBACK = "gpt-4o-mini"


def run(permitted: str) -> None:
    """Route over both models with policy permitting only `permitted`."""
    router = FallbackModel(
        OpenAIChatModel(PREFERRED),
        OpenAIChatModel(FALLBACK),
        fallback_on=(PermissionDenied,),
    )

    agent = SecureAgent(
        router,
        app_name=APP_NAME,
        intent_policy={
            "resources": [GENERATE],
            "constraints": {"parameters": {GENERATE: {"model": [permitted]}}},
        },
    )

    result = agent.run_sync("Say the single word: hello")
    print(f"  policy permits : {permitted}")
    print(f"  candidates     : {[m.wrapped.model_name for m in router.models]}")
    print(f"  served by      : {result.response.model_name}")
    print(f"  output         : {result.output}")


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY first:")
        print("  export OPENAI_API_KEY=sk-...")
        return 1

    print(f"--- Policy permits the preferred model ({PREFERRED}) ---")
    run(PREFERRED)

    print(f"\n--- Policy permits only the fallback ({FALLBACK}) ---")
    run(FALLBACK)
    print(f"\n  {PREFERRED} was denied by MACAW, so the router moved on.")
    print("  The run succeeded on a permitted model instead of failing.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
