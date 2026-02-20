#!/usr/bin/env python3
"""
langchain_1c_orchestration.py - Agent Orchestration with supervisor routing

A supervisor agent routes tasks to specialized sub-agents, each with different
security policies. Demonstrates policy composition where chains can only
restrict, never relax permissions.

Use this when: Building multi-agent workflows with different permission levels.

In this example:
- Supervisor: Routes requests to appropriate agent
- Research Agent: Can use search, file_reader (public only)
- Finance Agent: Can use calculator, file_reader (reports only)
- Admin Agent: Can use admin tools (restricted access)

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - OPENAI_API_KEY environment variable (for ChatOpenAI)

Run:
    export OPENAI_API_KEY=sk-...
    python langchain_1c_orchestration.py
"""

import os
from typing import Dict, Any

from macaw_adapters.langchain import create_react_agent, AgentExecutor, cleanup

from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from langchain.prompts import PromptTemplate


# Define specialized tools for different agents
def calculator(expression: str) -> str:
    """Evaluate a math expression."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"


def search_web(query: str) -> str:
    """Search the web (mock)."""
    return f"Search results for '{query}': [Top 3 relevant articles about {query}]"


def file_reader(path: str) -> str:
    """Read a file."""
    if "report" in path.lower():
        return "Q4 Revenue: $1.2M, Growth: 15%, Expenses: $800K"
    elif "public" in path.lower():
        return "Public announcement: Company expanding to new markets"
    elif "secret" in path.lower() or "confidential" in path.lower():
        return "ACCESS DENIED - Classified content"
    return f"Contents of {path}: [document data]"


def admin_tool(command: str) -> str:
    """Execute admin command."""
    return f"Admin executed: {command}"


def send_email(input_str: str) -> str:
    """Send an email (mock). Input format: 'to@email.com: subject text'"""
    # Parse simple format: "to: subject" or just treat whole thing as recipient
    if ":" in input_str:
        parts = input_str.split(":", 1)
        to = parts[0].strip()
        subject = parts[1].strip() if len(parts) > 1 else "No subject"
    else:
        to = input_str.strip()
        subject = "Notification"
    return f"Email sent to {to}: {subject}"


# All available tools
ALL_TOOLS = [
    Tool(name="calculator", func=calculator, description="Math calculations"),
    Tool(name="search", func=search_web, description="Search the web for information"),
    Tool(name="file_reader", func=file_reader, description="Read files"),
    Tool(name="admin", func=admin_tool, description="Execute admin commands"),
    Tool(name="email", func=send_email, description="Send emails"),
]


# ReAct prompt template
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


# Specialized agent configurations with MAPL format policies
AGENT_CONFIGS = {
    "research": {
        "description": "Research Agent - web search and public documents",
        "policy": {
            "resources": ["tool:search", "tool:file_reader"],
            "denied_resources": ["tool:admin", "tool:calculator", "tool:email"],
            "constraints": {
                "parameters": {
                    "tool:file_reader": {"input": ["*public*"]}
                },
                "denied_parameters": {
                    "tool:*": {"input": ["*password*", "*secret*", "*confidential*"]}
                }
            }
        }
    },
    "finance": {
        "description": "Finance Agent - calculations and financial reports",
        "policy": {
            "resources": ["tool:calculator", "tool:file_reader"],
            "denied_resources": ["tool:admin", "tool:search", "tool:email"],
            "constraints": {
                "parameters": {
                    "tool:file_reader": {"input": ["*report*", "*forecast*", "*budget*"]}
                },
                "denied_parameters": {
                    "tool:*": {"input": ["*password*"]}
                }
            }
        }
    },
    "admin": {
        "description": "Admin Agent - system administration (restricted)",
        "policy": {
            "resources": ["tool:admin", "tool:email"],
            "denied_resources": ["tool:calculator", "tool:search", "tool:file_reader"],
            "constraints": {
                "denied_parameters": {
                    "tool:*": {"input": ["*delete*", "*drop*", "*truncate*"]}
                }
            }
        }
    }
}


def create_specialized_agent(name: str, config: Dict[str, Any], llm) -> AgentExecutor:
    """Create a specialized agent with its security policy."""
    agent = create_react_agent(
        llm=llm,
        tools=ALL_TOOLS,
        prompt=REACT_PROMPT,
        security_policy=config["policy"]
    )

    return AgentExecutor(
        agent=agent,
        tools=ALL_TOOLS,
        security_policy=config["policy"],
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=3
    )


class SupervisorAgent:
    """
    Supervisor that routes tasks to appropriate specialized agents.

    Key security concept: The supervisor can only delegate to agents
    with equal or more restrictive policies. It cannot grant permissions
    it doesn't have (policy intersection).
    """

    def __init__(self, llm):
        self.llm = llm
        self.agents: Dict[str, AgentExecutor] = {}

        # Create specialized agents
        print("\n  Creating specialized agents:")
        for name, config in AGENT_CONFIGS.items():
            print(f"    - {name}: {config['description']}")
            self.agents[name] = create_specialized_agent(name, config, llm)

    def route(self, query: str) -> str:
        """Route query to appropriate agent based on content."""
        query_lower = query.lower()

        # Simple routing logic (in production, could use LLM for routing)
        if any(word in query_lower for word in ["calculate", "math", "revenue", "profit", "cost", "budget"]):
            return "finance"
        elif any(word in query_lower for word in ["search", "find", "lookup", "research", "public"]):
            return "research"
        elif any(word in query_lower for word in ["admin", "restart", "status", "notify", "email"]):
            return "admin"
        else:
            return "research"  # Default to research

    def invoke(self, query: str) -> Dict[str, Any]:
        """Route and execute query through appropriate agent."""
        agent_name = self.route(query)
        agent = self.agents[agent_name]

        print(f"  Routing to: {agent_name}")
        print(f"  Policy: {AGENT_CONFIGS[agent_name]['policy'].get('resources', 'all')}")

        try:
            result = agent.invoke({"input": query})
            return {
                "routed_to": agent_name,
                "success": True,
                "output": result.get("output", str(result))
            }
        except Exception as e:
            error_msg = str(e).lower()
            if any(word in error_msg for word in ["denied", "blocked", "policy", "not allowed"]):
                return {
                    "routed_to": agent_name,
                    "success": False,
                    "blocked": True,
                    "output": f"Policy blocked: {str(e)[:80]}"
                }
            return {
                "routed_to": agent_name,
                "success": False,
                "output": f"Error: {str(e)[:80]}"
            }


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY environment variable")
        return

    print("=" * 60)
    print("Example 1c: Agent Orchestration (LangChain)")
    print("=" * 60)
    print("\nPattern: Supervisor routes to specialized sub-agents")
    print("Use when: Multi-agent workflows with different permission levels")
    print("\nArchitecture:")
    print("  Supervisor --> Research Agent (search, public files)")
    print("            --> Finance Agent (calculator, reports)")
    print("            --> Admin Agent (admin tools, email)")

    # Shared LLM
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

    # Create supervisor
    print("\n--- Creating Supervisor Agent ---")
    supervisor = SupervisorAgent(llm)

    # Test cases demonstrating routing and policy enforcement
    TEST_CASES = [
        # Should route to finance, use calculator
        ("Calculate the profit if revenue is 1200000 and expenses are 800000", "finance", True),

        # Should route to research, use search
        ("Search for public information about AI trends", "research", True),

        # Should route to admin, use email
        ("Send an email to team@company.com about the system status", "admin", True),

        # Should route to finance, but try to access secret file (blocked - not in allowed patterns)
        ("What is the profit in the secret internal file?", "finance", False),

        # Should route to research, but research agent can't use calculator
        ("Search for how to compute 100 * 50", "research", True),  # Research will search, not calculate
    ]

    print("\n" + "=" * 60)
    print("Running test cases")
    print("=" * 60)

    for query, expected_agent, should_succeed in TEST_CASES:
        print(f"\n  Query: {query}")
        print(f"  Expected: routes to '{expected_agent}', {'succeeds' if should_succeed else 'blocked'}")

        result = supervisor.invoke(query)

        routed = result["routed_to"]
        succeeded = result["success"]
        output = result["output"][:60] + "..." if len(result.get("output", "")) > 60 else result.get("output", "")

        # Check if routing was correct
        route_correct = routed == expected_agent
        outcome_correct = succeeded == should_succeed

        status = "PASS" if (route_correct and outcome_correct) else "UNEXPECTED"

        print(f"  Result: [{status}] Routed to '{routed}', {'succeeded' if succeeded else 'blocked/failed'}")
        print(f"  Output: {output}")

    # Cleanup
    print("\n--- Cleanup ---")
    cleanup()

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)
    print("\nKey concepts demonstrated:")
    print("  - Supervisor pattern for agent orchestration")
    print("  - Each sub-agent has isolated security policy")
    print("  - Policy enforcement at tool execution time")
    print("  - Routing based on task type")


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
