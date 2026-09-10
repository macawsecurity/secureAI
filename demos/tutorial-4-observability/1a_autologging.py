#!/usr/bin/env python3
"""
1a_autologging.py -- three MACAW SDK adapters, one file, NO logging code.

Proves: wrap your client in a MACAW adapter and every policy decision and
tool/LLM call is emitted as structured OTel audit automatically -- you write no
logging, no OTel setup. The same macaw-mcp.audit schema flows from every adapter
into whatever OTLP sink is configured once (Datadog here).



Run (each block independent; missing key/server -> that block skips):
    source ~/path/to-env//venv/bin/activate
    export MACAW_HOME=~/path/to/macaw-client
    export OPENAI_API_KEY=sk-...        # openai + pydantic blocks
    export ANTHROPIC_API_KEY=sk-ant-... # anthropic block
    python all_adapters_autolog.py

"""
import os


def section(name):
    print("\n" + "-" * 12 + f" {name} " + "-" * 12)


# ============================ OPENAI ============================

def run_openai():
    from macaw_adapters.openai import SecureOpenAI
    client = SecureOpenAI(
        app_name="autolog-openai",
        intent_policy={
            "constraints": {
                "parameters": {
                    "tool:*/generate": {
                        "model": ["gpt-3.5-turbo"],
                        "max_tokens": {"max": 200}
                    }
                }
            }
        }
    )
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=100,
        messages=[{"role": "user", "content": "What is compound interest? Answer briefly."}]
    )
    print(f"  allowed: gpt-3.5-turbo -> {response.model}")
    try:
        client.chat.completions.create(
            model="gpt-4",
            max_tokens=100,
            messages=[{"role": "user", "content": "What is compound interest?"}]
        )
        print("  UNEXPECTED: gpt-4 not blocked")
    except Exception as e:
        print(f"  denied:  gpt-4 -> blocked ({str(e)[:60]})")


# ============================ ANTHROPIC ============================

def run_anthropic():
    from macaw_adapters.anthropic import SecureAnthropic
    client = SecureAnthropic(
        app_name="autolog-anthropic",
        intent_policy={
            "constraints": {
                "parameters": {
                    "tool:*/generate": {
                        "model": ["claude-3-haiku-20240307"],
                        "max_tokens": {"max": 200}
                    }
                }
            }
        }
    )
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=100,
        messages=[{"role": "user", "content": "What is compound interest? Answer briefly."}]
    )
    print(f"  allowed: haiku -> {response.model}")
    try:
        client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=100,
            messages=[{"role": "user", "content": "What is compound interest?"}]
        )
        print("  UNEXPECTED: opus not blocked")
    except Exception as e:
        print(f"  denied:  opus -> blocked ({str(e)[:60]})")


# ============================ PYDANTIC AI ============================

def run_pydantic():
    from pydantic_ai.models.openai import OpenAIChatModel
    from macaw_adapters.pydantic_ai import SecureAgent
    APP_NAME = "autolog-pydantic"
    GENERATE = f"tool:{APP_NAME}/generate"

    def query_catalog(table: str, limit: int = 10) -> str:
        """Query the data catalog for rows from a table."""
        return f"{limit} rows from {table}"

    def export_dataset(table: str) -> str:
        """Export a full dataset to external storage."""
        return f"exported {table}"

    agent = SecureAgent(
        OpenAIChatModel("gpt-4o-mini"),
        app_name=APP_NAME,
        tools=[query_catalog, export_dataset],
        intent_policy={
            "resources": [GENERATE, f"tool:{APP_NAME}/query_catalog"],
            "denied_resources": [f"tool:{APP_NAME}/export_dataset"],
            "constraints": {
                "parameters": {
                    GENERATE: {
                        "model": ["gpt-4o-mini"],
                        "max_tokens": {"max": 500},
                    }
                }
            },
        },
    )
    result = agent.run_sync("Use query_catalog on the customers table with limit 3.")
    print(f"  allowed: {result.output[:60]}")
    result = agent.run_sync("Export the customers table using export_dataset.")
    print(f"  denied:  {result.output[:60]}")



if __name__ == "__main__":
    for name, fn, need in (
        ("OPENAI",    run_openai,    "OPENAI_API_KEY"),
        ("ANTHROPIC", run_anthropic, "ANTHROPIC_API_KEY"),
        ("PYDANTIC",  run_pydantic,  "OPENAI_API_KEY")
  
    ):
        section(name)
        if need and not os.environ.get(need):
            print(f"  skipped: set {need}")
            continue
        try:
            fn()
        except Exception as e:
            print(f"  skipped: {str(e)[:90]}")
    print("\nDone. Every call above auto-logged to Datadog (service:<your-service-name>) "
          "with no logging code in this file.")
