#!/usr/bin/env python3
"""
script.py - Per-user LLM and Alation SQL access, gated by MACAW

alice (manager) and bob (analyst) each make 3 LLM calls and 2 Alation SQL calls
through identical code. MAPL policy is evaluated per request against the calling
user's identity, so the same call succeeds for one user and is blocked or held
for approval for the other.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Policies loaded in the Console (see Policies/)
    - Test users: alice.alation@gmail.com, bob.alation@gmail.com

Run:
    export MACAW_HOME=.../macaw-client-0.9.9.6-Linux-x86_64-py3.12
    export ALATION_MCP_URL=https://<tenant>.alationcloud.com/ai/mcp/<uuid>
    export ALATION_TOKEN=<fresh bearer>
    export OPENAI_API_KEY=sk-...
    python script.py
"""

import os
import sys
import logging

import httpx

from macaw_adapters.openai import SecureOpenAI
from macaw_adapters.mcp import SecureMCPProxy
from macaw_client import MACAWClient, RemoteIdentityProvider

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utility"))
from alation_verifier import AlationSQLGuardVerifier

logging.getLogger("macaw_client").setLevel(logging.ERROR)

PASSWORD = "test@123"
PROMPT = "What is compound interest? Answer in one short sentence."
DATA_PRODUCT = "databricks-macaw-product"
ENG_COMP = "workspace.macaw_demo.eng_comp"      # Databricks will not resolve a bare 'eng_comp'


# Test configurations based on user policies
# Alice: gpt-4o-mini/gpt-4o, max 2000 tokens; reads eng_comp freely
# Bob:   gpt-4o-mini only,   max 100 tokens;  eng_comp needs a manager's attestation
USER_TESTS = {
    "alice": {
        "email": "alice.alation@gmail.com",
        "policy_desc": "gpt-4o-mini/gpt-4o, max 2000 tokens",
        "llm": [
            # (model, max_tokens)
            ("gpt-4-turbo", 80),        # BLOCKED - model not allowed
            ("gpt-4o", 3000),           # BLOCKED - exceeds token ceiling
            ("gpt-4o", 500),            # ALLOWED
        ],
        "sql": [
            f"SELECT name, base_salary FROM {ENG_COMP} LIMIT 3",   # ALLOWED
            f"SELECT COUNT(*) FROM {ENG_COMP}",                    # ALLOWED
        ],
    },
    "bob": {
        "email": "bob.alation@gmail.com",
        "policy_desc": "gpt-4o-mini only, max 100 tokens",
        "llm": [
            ("gpt-4o", 80),             # BLOCKED - model not allowed
            ("gpt-4o-mini", 300),       # BLOCKED - exceeds token ceiling
            ("gpt-4o-mini", 80),        # ALLOWED
        ],
        "sql": [
            f"DELETE FROM {ENG_COMP} WHERE name = 'nobody'",       # BLOCKED - stmt_type
            f"SELECT name, base_salary FROM {ENG_COMP} LIMIT 3",   # ATTESTATION
        ],
    },
}


def get_env(name: str) -> str:
    """Read a required environment variable.

    Strips surrounding quotes, including the curly ones a copy-paste from a document
    leaves behind - those reach the Authorization header and fail as a bad credential.
    """
    value = os.environ.get(name, "").strip().strip("\"'“”‘’")
    if not value:
        sys.exit(f"Missing {name}. Set it with:  export {name}=...")
    if not value.isascii():
        sys.exit(f"{name} contains a non-ASCII character - re-copy it as plain text.")
    return value


def verdict_for(error: Exception) -> str:
    """Separate a MACAW policy decision from any other failure.

    A demo about policy enforcement must never report a broken credential or a network
    fault as though the policy had blocked it.
    """
    message = str(error).lower()
    if "attest" in message:
        return "ATTESTATION"
    if any(s in message for s in ("not in allowed", "exceeds maximum", "policy",
                                  "denied", "not permitted")):
        return "BLOCKED"
    return f"ERROR - {str(error)[:70]}"


def patch_proxy_timeout():
    """Tune the upstream HTTP client for Alation's long-running agent endpoint.

    httpx ships a 5s default that suits short request/response APIs. Here we widen the
    read timeout to 300s for this upstream while keeping connect, write and pool tight,
    so long analytical calls complete without loosening anything else.
    """
    def create_http_client(self):
        auth = self.upstream_auth
        headers = ({"Authorization": f"Bearer {auth.token}"}
                   if getattr(auth, "type", None) == "bearer" and getattr(auth, "token", None)
                   else {})
        return httpx.AsyncClient(
            headers=headers or None,
            timeout=httpx.Timeout(connect=30, read=300, write=30, pool=30),
        )
    SecureMCPProxy._create_http_client = create_http_client


def test_user(username: str, openai_service: SecureOpenAI, proxy: SecureMCPProxy):
    """Run one user's LLM and SQL calls under their own identity."""
    config = USER_TESTS[username]
    print(f"\n{'=' * 60}")
    print(f"{username.upper()} - {config['policy_desc']}")
    print("=" * 60)

    # 1. Authenticate and register the user agent
    jwt_token, _ = RemoteIdentityProvider().login(config["email"], PASSWORD)
    user = MACAWClient(user_name=username, iam_token=jwt_token,
                       agent_type="user", app_name="alation")
    user.register()

    # 2. LLM calls - A2A to the shared OpenAI service, gated on model and max_tokens
    for model, max_tokens in config["llm"]:
        try:
            result = user.invoke_tool(
                tool_name="tool:openai-service/generate",
                parameters={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": PROMPT}],
                },
                target_agent=openai_service.server_id,
            )
            answer = result["choices"][0]["message"]["content"].strip()
            print(f"  LLM  {model} /{max_tokens} -> {answer}")
        except Exception as e:
            print(f"  LLM  {model} /{max_tokens} -> {verdict_for(e)}")

    # 3. SQL calls - through the user-bound proxy, gated by the verifier and policy
    bound = proxy.bind_to_user(user)
    for sql in config["sql"]:
        try:
            result = bound.call_tool(
                "run_query_sql_custom_adi",
                {"sql": sql, "message": "demo", "data_product_id": DATA_PRODUCT},
            )
            print(f"  SQL  {sql}\n       -> {str(result)[:220]}")
        except Exception as e:
            print(f"  SQL  {sql} -> {verdict_for(e)}")


def main():
    openai_service = SecureOpenAI(api_key=get_env("OPENAI_API_KEY"), app_name="openai-service")

    patch_proxy_timeout()
    proxy = SecureMCPProxy(
        app_name="alation-remote-proxy",
        upstream_url=get_env("ALATION_MCP_URL"),
        upstream_auth={"type": "bearer", "token": get_env("ALATION_TOKEN")},
    )
    proxy.macaw_client.agent.verification_pipeline.add_verifier(
        AlationSQLGuardVerifier(), priority=20
    )

    for username in USER_TESTS:
        test_user(username, openai_service, proxy)


if __name__ == "__main__":
    main()
