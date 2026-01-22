#!/usr/bin/env python3
"""
Example 1b: Multi-user Agents (LangChain)

Create different agent instances per user role, each with their own security policy.
Use this when: Different users need different tool access levels.

In this example:
- alice (Analyst): Can only use calculator
- bob (Manager): Can use calculator and weather
- carol (Admin): Can use all tools including admin

Run with:
    PYTHONPATH=/path/to/secureAI python langchain_1b_multiuser.py
"""

import os

from macaw_adapters.langchain import create_react_agent, AgentExecutor, cleanup

from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from langchain.prompts import PromptTemplate


# Define tools
def calculator(expression: str) -> str:
    """Evaluate a math expression."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"


def get_weather(city: str) -> str:
    """Get weather for a city (mock)."""
    weather_data = {
        "new york": "72°F, Sunny",
        "london": "58°F, Cloudy",
        "tokyo": "68°F, Clear"
    }
    return weather_data.get(city.lower(), f"Weather for {city}: 65°F, Partly cloudy")


def admin_tool(command: str) -> str:
    """Execute admin command."""
    return f"Executed admin command: {command}"


def file_reader(path: str) -> str:
    """Read a file."""
    # Mock - returns different content based on path
    if "report" in path.lower():
        return "Q4 Revenue: $1.2M, Growth: 15%"
    elif "secret" in path.lower():
        return "ACCESS DENIED - Classified content"
    return f"Contents of {path}: [mock data]"


# All available tools
ALL_TOOLS = [
    Tool(name="calculator", func=calculator, description="Math calculations"),
    Tool(name="weather", func=get_weather, description="Get weather for a city"),
    Tool(name="admin", func=admin_tool, description="Execute admin commands"),
    Tool(name="file_reader", func=file_reader, description="Read files"),
]


# User role configurations with SOSP format policies
USER_CONFIGS = {
    "alice": {
        "role": "Financial Analyst",
        "security_policy": {
            "resources": ["tool:calculator", "tool:file_reader"],
            "denied_resources": ["tool:admin"],
            "constraints": {
                "parameters": {
                    "tool:file_reader": {"input": ["*report*", "*public*"]}
                },
                "denied_parameters": {
                    "tool:*": {"input": ["*password*", "*secret*"]}
                }
            }
        },
        "tests": [
            ("What is 100 * 12?", "ALLOWED - calculator"),
            ("Read the Q4 report", "ALLOWED - file_reader for reports"),
            ("Run admin command: list users", "BLOCKED - admin tool"),
            ("What's the weather in London?", "BLOCKED - weather not allowed"),
        ]
    },
    "bob": {
        "role": "Finance Manager",
        "security_policy": {
            "resources": ["tool:calculator", "tool:weather", "tool:file_reader"],
            "denied_resources": ["tool:admin"],
            "constraints": {
                "parameters": {
                    "tool:file_reader": {"input": ["*report*", "*forecast*", "*public*"]}
                },
                "denied_parameters": {
                    "tool:*": {"input": ["*password*"]}
                }
            }
        },
        "tests": [
            ("What is 250 + 750?", "ALLOWED - calculator"),
            ("What's the weather in Tokyo?", "ALLOWED - weather"),
            ("Read the Q4 report", "ALLOWED - file_reader"),
            ("Run admin command: restart", "BLOCKED - admin tool"),
        ]
    },
    "carol": {
        "role": "IT Administrator",
        "security_policy": {
            "resources": ["tool:calculator", "tool:weather", "tool:file_reader", "tool:admin"],
            # No denied_resources - full tool access
            "constraints": {
                "parameters": {
                    "tool:file_reader": {"input": ["*"]}  # All files
                }
            }
        },
        "tests": [
            ("What is 999 * 111?", "ALLOWED - calculator"),
            ("What's the weather in New York?", "ALLOWED - weather"),
            ("Run admin command: status check", "ALLOWED - admin access"),
            ("Read the secret file", "ALLOWED - full file access"),
        ]
    }
}


# Simple ReAct prompt
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


def create_user_executor(username: str, config: dict, llm) -> AgentExecutor:
    """Create a security-scoped executor for a specific user."""
    print(f"\n  Creating executor for {username} ({config['role']})")
    print(f"  Policy: {config['security_policy'].get('resources', 'all')}")

    agent = create_react_agent(
        llm=llm,
        tools=ALL_TOOLS,
        prompt=REACT_PROMPT,
        security_policy=config["security_policy"]
    )

    executor = AgentExecutor(
        agent=agent,
        tools=ALL_TOOLS,
        security_policy=config["security_policy"],
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=3
    )

    return executor


def test_user(username: str, config: dict, executor: AgentExecutor):
    """Test a user's executor with their test cases."""
    print(f"\n{'=' * 60}")
    print(f"Testing {username.upper()} ({config['role']})")
    print(f"Allowed tools: {config['security_policy'].get('resources', 'all')}")
    print("=" * 60)

    for query, expected in config["tests"]:
        print(f"\n  Query: {query}")
        print(f"  Expected: {expected}")

        try:
            result = executor.invoke({"input": query})
            output = result.get("output", str(result))

            # Check if it was blocked
            if "denied" in output.lower() or "access denied" in output.lower():
                print(f"  Result: BLOCKED - {output[:50]}...")
            elif "cannot" in output.lower() or "don't have" in output.lower():
                print(f"  Result: BLOCKED (agent refused) - {output[:50]}...")
            else:
                print(f"  Result: SUCCESS - {output[:60]}...")

        except Exception as e:
            error_msg = str(e).lower()
            if any(word in error_msg for word in ["denied", "blocked", "policy", "not allowed"]):
                print(f"  Result: CORRECTLY BLOCKED - {str(e)[:50]}...")
            else:
                print(f"  Result: ERROR - {str(e)[:50]}...")


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY environment variable")
        return

    print("=" * 60)
    print("Example 1b: Multi-user Agents (LangChain)")
    print("=" * 60)
    print("\nPattern: Separate executor per user with role-based policies")
    print("Use when: Different users need different tool access levels")
    print("\nUsers:")
    print("  alice (Analyst): calculator, file_reader (reports only)")
    print("  bob (Manager): calculator, weather, file_reader")
    print("  carol (Admin): all tools, all files")

    # Shared LLM
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

    # Create and test each user
    for username, config in USER_CONFIGS.items():
        executor = create_user_executor(username, config, llm)
        test_user(username, config, executor)

    # Cleanup
    print("\n--- Cleanup ---")
    cleanup()

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
