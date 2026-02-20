#!/usr/bin/env python3
"""
1e_sampling_client.py - MCP Sampling (Server->Client LLM)

Demonstrates client.set_sampling_handler() for server->client LLM requests.

The client registers an LLM handler that the server's ctx.sample() calls.
Set ANTHROPIC_API_KEY environment variable to use real Claude API,
otherwise falls back to mock responses.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Sampling server running (1e_sampling_server.py)
    - ANTHROPIC_API_KEY environment variable (optional, for real Claude)

Run:
    # Terminal 1: Start the server
    python 1e_sampling_server.py

    # Terminal 2: Run this client (with optional API key)
    export ANTHROPIC_API_KEY=sk-ant-...  # Optional
    python 1e_sampling_client.py
"""

import os

from macaw_adapters.mcp import Client


def find_sampling_server(client):
    """Find the most recent sampling demo server."""
    agents = client.macaw_client.list_agents(agent_type="app")
    matching = [
        a["agent_id"] for a in agents
        if "sampling-demo" in a.get("agent_id", "")
        and "/tool." not in a.get("agent_id", "")
    ]
    return matching[-1] if matching else None  # Return last (most recent)


def create_llm_handler():
    """Create LLM handler - real Claude if API key available, else mock."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            print("Using Claude API (claude-sonnet-4-20250514)")

            def claude_handler(prompt, system_prompt=None, max_tokens=1000, temperature=0.7, **kwargs):
                print(f"  [Claude] Prompt: {prompt[:60]}...")
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=max_tokens,
                    system=system_prompt or "You are a helpful assistant.",
                    messages=[{"role": "user", "content": prompt}]
                )
                result = response.content[0].text
                print(f"  [Claude] Response: {result[:60]}...")
                return result

            return claude_handler
        except ImportError:
            print("anthropic package not installed, falling back to mock")
        except Exception as e:
            print(f"Error initializing Claude: {e}, falling back to mock")

    # Mock handler fallback
    print("Using mock LLM (set ANTHROPIC_API_KEY for real Claude)")

    def mock_handler(prompt, system_prompt=None, max_tokens=1000, temperature=0.7, **kwargs):
        print(f"  [Mock] Prompt: {prompt[:60]}...")
        if "summarize" in prompt.lower():
            return "This is a mock summary of the provided text."
        elif "sentiment" in prompt.lower():
            return '{"sentiment": "positive", "confidence": 0.85}'
        return "Mock LLM response"

    return mock_handler


def main():
    print("=" * 50)
    print("Example 1e: Sampling Demo Client")
    print("=" * 50)

    client = Client("sampling-client")
    print(f"Client: {client.client_id}")

    # Create and register LLM handler (Claude or mock)
    llm_handler = create_llm_handler()
    client.set_sampling_handler(llm_handler)
    print()

    server = find_sampling_server(client)
    if not server:
        print("\nNo sampling-demo server found!")
        print("Start it first: python3 1e_sampling_server.py")
        return

    print(f"Server: {server}")
    print()

    # Test summarize
    print("Testing summarize():")
    print("-" * 40)
    result = client.macaw_client.invoke_tool(
        "summarize",
        {"text": "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the alphabet and is commonly used for typing practice.", "max_length": 50},
        target_agent=server
    )
    print(f"  Result: {result}")
    print()

    # Test analyze_sentiment
    print("Testing analyze_sentiment():")
    print("-" * 40)
    result = client.macaw_client.invoke_tool(
        "analyze_sentiment",
        {"text": "I love this product! It's amazing and works perfectly!"},
        target_agent=server
    )
    print(f"  Result: {result}")
    print()

    print("=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = str(e)
        print("\n" + "=" * 50)
        if "Connection refused" in err or "connect" in err.lower():
            print("ERROR: Cannot connect to MACAW")
            print("Fix: Ensure MACAW is running")
        else:
            print(f"ERROR: {e}")
        print("=" * 50)
        import sys
        sys.exit(1)
