#!/usr/bin/env python3
"""
langchain_1d_llm_openai.py - SecureChatOpenAI drop-in replacement

Drop-in replacement for langchain_openai.ChatOpenAI with MACAW protection.
Demonstrates invoke and streaming with audit logging.

Use this when: You want MACAW security on LangChain OpenAI calls without
changing your application code.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - OPENAI_API_KEY environment variable

Run:
    export OPENAI_API_KEY=sk-...
    python langchain_1d_llm_openai.py
"""

import os

# BEFORE: from langchain_openai import ChatOpenAI
# AFTER:
from macaw_adapters.langchain.openai import ChatOpenAI, cleanup


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=sk-...")
        return

    print("=" * 60)
    print("Example 1d: SecureChatOpenAI (LangChain)")
    print("=" * 60)
    print("\nPattern: Drop-in replacement for langchain_openai.ChatOpenAI")
    print("Use when: Add MACAW audit logging to LangChain OpenAI calls")
    print("\nImport change:")
    print("  BEFORE: from langchain_openai import ChatOpenAI")
    print("  AFTER:  from macaw_adapters.langchain.openai import ChatOpenAI")

    # Create SecureChatOpenAI - same API as langchain_openai.ChatOpenAI
    print("\n--- Creating SecureChatOpenAI ---")
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=100
    )
    print(f"Model: {llm.model_name}")
    print(f"Temperature: {llm.temperature}")

    # Test 1: Basic invoke
    print("\n--- Test 1: Basic invoke ---")
    try:
        response = llm.invoke("What is 2 + 2? Answer in one word.")
        print(f"Response: {response.content}")
        print("(This call was audit-logged by MACAW)")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Invoke with message list
    print("\n--- Test 2: Invoke with messages ---")
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content="You are a helpful assistant. Be concise."),
            HumanMessage(content="Name three primary colors.")
        ]
        response = llm.invoke(messages)
        print(f"Response: {response.content}")
    except ImportError:
        print("Skipping (langchain_core not installed)")
    except Exception as e:
        print(f"Error: {e}")

    # Test 3: Streaming
    print("\n--- Test 3: Streaming ---")
    try:
        print("Response: ", end="", flush=True)
        for chunk in llm.stream("Count from 1 to 5, one number per line."):
            if hasattr(chunk, 'content'):
                print(chunk.content, end="", flush=True)
            else:
                print(chunk, end="", flush=True)
        print("\n(Streaming call was audit-logged by MACAW)")
    except Exception as e:
        print(f"\nError: {e}")

    # Test 4: Batch
    print("\n--- Test 4: Batch ---")
    try:
        prompts = [
            "What color is the sky? One word.",
            "What color is grass? One word."
        ]
        responses = llm.batch(prompts)
        for i, resp in enumerate(responses):
            print(f"  Q{i+1}: {prompts[i]}")
            print(f"  A{i+1}: {resp.content}")
    except Exception as e:
        print(f"Error: {e}")

    # Cleanup
    print("\n--- Cleanup ---")
    cleanup()

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)
    print("\nKey points:")
    print("  - Same API as langchain_openai.ChatOpenAI")
    print("  - All calls audit-logged through MACAW")
    print("  - Supports invoke, stream, batch, and async variants")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = str(e)
        print("\n" + "=" * 60)
        if "OPENAI_API_KEY" in err or "api_key" in err.lower():
            print("ERROR: OpenAI API key not configured")
            print("Fix: export OPENAI_API_KEY=sk-...")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        import sys
        sys.exit(1)
