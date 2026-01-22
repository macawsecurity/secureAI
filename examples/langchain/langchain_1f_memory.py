#!/usr/bin/env python3
"""
Example 1f: Secure Memory (LangChain)

Drop-in replacement for LangChain memory classes with MACAW context backing.
Demonstrates multi-session isolation where each user gets separate memory.

Use this when: You want conversation memory backed by MACAW's secure context
vault with audit logging and session isolation.

Run with:
    PYTHONPATH=/path/to/secureAI python langchain_1f_memory.py
"""

import os

# BEFORE: from langchain.memory import ConversationBufferMemory
# AFTER:
from macaw_adapters.langchain.memory import (
    ConversationBufferMemory,
    ConversationBufferWindowMemory,
    cleanup
)
from macaw_adapters.langchain.openai import ChatOpenAI


def demonstrate_basic_memory():
    """Basic memory usage."""
    print("\n--- Basic ConversationBufferMemory ---")

    memory = ConversationBufferMemory(session_id="demo-session")

    # Simulate conversation
    memory.save_context(
        {"input": "Hi, my name is Alice"},
        {"output": "Hello Alice! How can I help you today?"}
    )
    memory.save_context(
        {"input": "What's the weather like?"},
        {"output": "I don't have real-time weather data, but I can help you find it."}
    )

    # Load memory
    history = memory.load_memory_variables({})
    print(f"Conversation history:\n{history['history']}")
    print("\n(All memory operations audit-logged by MACAW)")

    return memory


def demonstrate_multi_session():
    """Multi-session isolation - each user gets separate memory."""
    print("\n--- Multi-Session Isolation ---")
    print("Each user has isolated memory (different session_id)")

    # Alice's session
    alice_memory = ConversationBufferMemory(session_id="alice-session")
    alice_memory.save_context(
        {"input": "I want to order pizza"},
        {"output": "What toppings would you like?"}
    )
    alice_memory.save_context(
        {"input": "Pepperoni please"},
        {"output": "One pepperoni pizza coming up!"}
    )

    # Bob's session (completely isolated)
    bob_memory = ConversationBufferMemory(session_id="bob-session")
    bob_memory.save_context(
        {"input": "I need help with my order"},
        {"output": "Of course! What's your order number?"}
    )
    bob_memory.save_context(
        {"input": "Order #12345"},
        {"output": "I found your order. How can I help?"}
    )

    # Show isolation
    print("\nAlice's memory:")
    alice_hist = alice_memory.load_memory_variables({})
    print(f"  {alice_hist['history']}")

    print("\nBob's memory:")
    bob_hist = bob_memory.load_memory_variables({})
    print(f"  {bob_hist['history']}")

    print("\n(Sessions are isolated - Bob can't see Alice's conversation)")

    return alice_memory, bob_memory


def demonstrate_window_memory():
    """Window memory - only keeps last k turns."""
    print("\n--- ConversationBufferWindowMemory (k=2) ---")
    print("Only keeps last 2 conversation turns")

    memory = ConversationBufferWindowMemory(k=2, session_id="window-demo")

    # Add 4 turns
    conversations = [
        ("Turn 1: Hello", "Hi there!"),
        ("Turn 2: How are you?", "I'm doing well!"),
        ("Turn 3: What's your name?", "I'm an AI assistant."),
        ("Turn 4: Can you help me?", "Of course! What do you need?"),
    ]

    for user_msg, ai_msg in conversations:
        memory.save_context({"input": user_msg}, {"output": ai_msg})

    # Only last 2 turns should be visible
    history = memory.load_memory_variables({})
    print(f"Window memory (last 2 turns only):\n{history['history']}")

    return memory


def demonstrate_with_llm():
    """Use memory with actual LLM (if API key available)."""
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n--- Skipping LLM demo (no OPENAI_API_KEY) ---")
        return

    print("\n--- Memory with SecureChatOpenAI ---")

    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, max_tokens=50)
    memory = ConversationBufferMemory(session_id="llm-demo")

    # First turn
    user_input = "My favorite color is blue."
    print(f"User: {user_input}")

    response = llm.invoke(f"The user said: {user_input}. Acknowledge this.")
    ai_output = response.content
    print(f"AI: {ai_output}")

    memory.save_context({"input": user_input}, {"output": ai_output})

    # Second turn - AI should remember
    user_input2 = "What did I just tell you?"
    print(f"\nUser: {user_input2}")

    history = memory.load_memory_variables({})
    context = f"Previous conversation:\n{history['history']}\n\nUser: {user_input2}"

    response2 = llm.invoke(context)
    print(f"AI: {response2.content}")

    memory.save_context({"input": user_input2}, {"output": response2.content})

    print("\n(Memory backed by MACAW context vault)")


def main():
    print("=" * 60)
    print("Example 1f: Secure Memory (LangChain)")
    print("=" * 60)
    print("\nPattern: Drop-in replacement for langchain.memory classes")
    print("Use when: Need conversation memory with MACAW context backing")
    print("\nImport change:")
    print("  BEFORE: from langchain.memory import ConversationBufferMemory")
    print("  AFTER:  from macaw_adapters.langchain.memory import ConversationBufferMemory")

    # Demo 1: Basic memory
    basic_memory = demonstrate_basic_memory()

    # Demo 2: Multi-session isolation
    alice_memory, bob_memory = demonstrate_multi_session()

    # Demo 3: Window memory
    window_memory = demonstrate_window_memory()

    # Demo 4: With actual LLM
    demonstrate_with_llm()

    # Cleanup
    print("\n--- Cleanup ---")
    basic_memory.clear()
    alice_memory.clear()
    bob_memory.clear()
    window_memory.clear()
    cleanup()

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)
    print("\nKey points:")
    print("  - Same API as langchain.memory classes")
    print("  - Memory backed by MACAW context vault")
    print("  - All operations audit-logged")
    print("  - Session isolation via session_id")
    print("  - Supports: ConversationBufferMemory, WindowMemory, SummaryMemory")


if __name__ == "__main__":
    main()
