#!/usr/bin/env python3
"""
Finance Agent Demo (User-Level Policies)

Tools: execute_trade, read_file, generate_report
Run: python <script>.py "Execute trade: buy 15000 of AAPL"
"""
import os
import sys
import json
from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider


def execute_trade(symbol: str, amount: float, action: str = "buy"):
    """Execute a stock trade."""
    print(f"[TRADE] {action} ${amount:,.0f} of {symbol}")
    return {"status": "executed", "symbol": symbol, "amount": amount}


def read_file(path: str):
    """Read contents of a file."""
    print(f"[FILE] Reading {path}")
    try:
        with open(path) as f:
            return {"path": path, "content": f.read()[:500]}
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}


def generate_report(report_type: str):
    """Generate a financial report."""
    print(f"[REPORT] Generating {report_type}")
    return {"status": "complete", "type": report_type}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_trade",
            "description": "Execute a stock trade order",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock symbol (e.g., AAPL)"},
                    "amount": {"type": "number", "description": "Trade amount in USD"},
                    "action": {"type": "string", "enum": ["buy", "sell"]}
                },
                "required": ["symbol", "amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "Generate a financial report",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {"type": "string", "description": "Type of report"}
                },
                "required": ["report_type"]
            }
        }
    }
]


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    # Authenticate as Alice
    jwt_token, _ = RemoteIdentityProvider().login("alice", "Alice123!")
    user = MACAWClient(
        user_name="alice",
        iam_token=jwt_token,
        agent_type="user",
        app_name="finance-agent"
    )
    user.register()

    # SecureOpenAI bound to user
    openai_service = SecureOpenAI(app_name="finance-agent")

    # Register tool handlers so _handle_generate can execute them
    openai_service.register_tool("execute_trade", execute_trade)
    openai_service.register_tool("read_file", read_file)
    openai_service.register_tool("generate_report", generate_report)

    client = openai_service.bind_to_user(user)

    try:
        prompt = " ".join(sys.argv[1:]) or "Execute trade: buy 15000 of AAPL"
        print(f"[AGENT] {prompt}\n")

        messages = [
            {"role": "system", "content": "You are a financial assistant. Use tools to help the user."},
            {"role": "user", "content": prompt}
        ]

        response = client.chat.completions.create(
            model="gpt-4",
            tools=TOOLS,
            messages=messages
        )

        # Handle tool calls if any
        if response.choices[0].message.tool_calls:
            # Add assistant message with tool calls
            messages.append(response.choices[0].message)

            # Execute each tool and add results
            for tc in response.choices[0].message.tool_calls:
                fn = globals()[tc.function.name]
                args = json.loads(tc.function.arguments)
                try:
                    result = fn(**args)
                    if isinstance(result, dict) and 'error' in result:
                        print(f"Error: {result.get('reason', result['error'])}")
                except Exception as e:
                    print(f"Error: {e}")
                    result = {"error": str(e)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)
                })

            # Continue conversation to get final response
            response = client.chat.completions.create(
                model="gpt-4",
                messages=messages
            )

        # Print final response
        if response.choices[0].message.content:
            print(f"[RESPONSE] {response.choices[0].message.content}")
    finally:
        openai_service.macaw_client.unregister()
        user.unregister()


if __name__ == "__main__":
    main()
