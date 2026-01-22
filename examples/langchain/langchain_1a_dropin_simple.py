#!/usr/bin/env python3
"""
Example 1a: Drop-in Replacement (LangChain)

The simplest path - replace your LangChain imports and add a security_policy.
Use this when: Single app, need tool access control, app-level policies.

Run with:
    PYTHONPATH=/path/to/secureAI python langchain_1a_dropin_simple.py
"""

import os

# BEFORE: from langchain.agents import create_react_agent, AgentExecutor
# AFTER:
from macaw_adapters.langchain import create_react_agent, AgentExecutor, cleanup

from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from langchain.prompts import PromptTemplate


# Define some tools
def calculator(expression: str) -> str:
    """Evaluate a math expression."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"


def get_weather(city: str) -> str:
    """Get weather for a city (mock)."""
    # Mock weather data
    weather_data = {
        "new york": "72°F, Sunny",
        "london": "58°F, Cloudy",
        "tokyo": "68°F, Clear"
    }
    return weather_data.get(city.lower(), f"Weather for {city}: 65°F, Partly cloudy")


def admin_tool(command: str) -> str:
    """Execute admin command (dangerous!)."""
    return f"Executed admin command: {command}"


# Create tools list
TOOLS = [
    Tool(
        name="calculator",
        func=calculator,
        description="Useful for math calculations. Input should be a math expression."
    ),
    Tool(
        name="weather",
        func=get_weather,
        description="Get current weather for a city. Input should be a city name."
    ),
    Tool(
        name="admin",
        func=admin_tool,
        description="Execute admin commands. Input should be a command string."
    ),
]


# Simple ReAct prompt template
REACT_PROMPT = PromptTemplate.from_template("""Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}""")


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=sk-...")
        return

    print("=" * 60)
    print("Example 1a: Drop-in Replacement (LangChain)")
    print("=" * 60)
    print("\nPath: Direct agent with security_policy")
    print("Use when: Single app, need tool access control")

    # Create LLM
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

    # Create agent WITH security policy
    # - Only "calculator" and "weather" are allowed
    # - "admin" tool is blocked
    # - Queries containing "password" are blocked
    print("\n--- Creating secure agent ---")
    print("Policy: Allow calculator & weather, block admin")
    print("        Block queries with '*password*'")

    # SOSP format policy - direct, no conversion layer
    policy = {
        "resources": ["tool:calculator", "tool:weather"],  # Allowed tools
        "denied_resources": ["tool:admin"],                 # Blocked tools
        "constraints": {
            "denied_parameters": {
                "tool:*": {"input": ["*password*", "*secret*"]}  # Block sensitive queries
            }
        }
    }

    agent = create_react_agent(
        llm=llm,
        tools=TOOLS,
        prompt=REACT_PROMPT,
        security_policy=policy
    )

    # Create executor with same policy
    executor = AgentExecutor(
        agent=agent,
        tools=TOOLS,
        security_policy=policy,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=3
    )

    # Test 1: Allowed tool (calculator)
    print("\n--- Test 1: Allowed tool (calculator) ---")
    try:
        result = executor.invoke({"input": "What is 15 * 7 + 23?"})
        print(f"Result: {result.get('output', result)}")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Allowed tool (weather)
    print("\n--- Test 2: Allowed tool (weather) ---")
    try:
        result = executor.invoke({"input": "What's the weather in Tokyo?"})
        print(f"Result: {result.get('output', result)}")
    except Exception as e:
        print(f"Error: {e}")

    # Test 3: Blocked tool (admin) - should be denied
    print("\n--- Test 3: Blocked tool (admin) - SHOULD BE DENIED ---")
    try:
        result = executor.invoke({"input": "Run admin command: list users"})
        print(f"Result: {result.get('output', result)}")
        # If agent can't use admin tool, it should say it can't do this
    except Exception as e:
        error_msg = str(e).lower()
        if "denied" in error_msg or "blocked" in error_msg or "policy" in error_msg:
            print(f"Correctly blocked: {e}")
        else:
            print(f"Error: {e}")

    # Cleanup
    print("\n--- Cleanup ---")
    cleanup()

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
