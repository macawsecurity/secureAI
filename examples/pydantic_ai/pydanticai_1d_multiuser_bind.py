"""
Per-user policy on a shared agent.

One SecureAgent is built once for the service. bind_to_user() returns an agent
that issues every invocation as that user, so MACAW evaluates alice's and bob's
policies against the same application resources.

    service = SecureAgent(model, app_name="pydantic-agent", tools=[...])
    alice_agent = service.bind_to_user(alice_client)

The registration and the tools are shared; only the caller identity differs.

Prerequisites:
    export OPENAI_API_KEY=sk-...
    MACAW LocalAgent running
    Identity provider running with the demo users (Keycloak or Auth0)
    Workspace policies for user:alice and user:bob covering tool:pydantic-agent/*

Run:
    python pydanticai_1d_multiuser_bind.py
"""

import os
import sys

from macaw_client import MACAWClient, PermissionDenied, RemoteIdentityProvider
from pydantic_ai.models.openai import OpenAIChatModel

from macaw_adapters.pydantic_ai import SecureAgent

APP_NAME = "pydantic-agent"
GENERATE = f"tool:{APP_NAME}/generate"

USERS = [("alice", "Alice123!"), ("bob", "Bob@123!")]


def query_catalog(table: str, limit: int = 10) -> str:
    """Query the data catalog for rows from a table."""
    return f"{limit} rows from {table}"


def export_dataset(table: str) -> str:
    """Export a full dataset to external storage."""
    return f"exported {table}"


def login(username: str, password: str):
    """Authenticate against the identity provider and register a user agent."""
    jwt_token, _ = RemoteIdentityProvider().login(username, password)
    user = MACAWClient(
        user_name=username,
        iam_token=jwt_token,
        agent_type="user",
        app_name=APP_NAME,
    )
    if not user.register():
        raise RuntimeError(f"Failed to register user agent for {username}")
    return user


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY first:")
        print("  export OPENAI_API_KEY=sk-...")
        return 1

    # One service agent, shared by every user.
    service = SecureAgent(
        OpenAIChatModel("gpt-4o-mini"),
        app_name=APP_NAME,
        tools=[query_catalog, export_dataset],
        intent_policy={"resources": [GENERATE, f"tool:{APP_NAME}/*"]},
    )
    print(f"Service registered: {service._macaw.server_id}")

    for username, password in USERS:
        print(f"\n=== {username} ===")
        try:
            user = login(username, password)
        except Exception as e:
            print(f"  login failed: {e}")
            print("  Is the identity provider running? See demos/tutorial-1/setup/")
            continue

        agent = service.bind_to_user(user)

        for prompt in (
            "Use query_catalog on the customers table with limit 3.",
            "Export the customers table using export_dataset.",
        ):
            try:
                result = agent.run_sync(prompt)
                print(f"  {result.output}")
            except PermissionDenied as e:
                print(f"  denied by MACAW: {e}")

        user.unregister()

    print("\nSame agent, same tools. The difference is whose policy was resolved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
