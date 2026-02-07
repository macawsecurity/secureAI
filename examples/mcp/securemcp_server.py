#!/usr/bin/env python3
"""
SecureMCP Calculator Server

Run this first, then use 1a_simple_invocation.py to test.
"""

from macaw_adapters.mcp import SecureMCP, Context

mcp = SecureMCP("calculator")


@mcp.tool(description="Add two numbers")
def add(a: float, b: float) -> float:
    return a + b


@mcp.tool(description="Subtract two numbers")
def subtract(a: float, b: float) -> float:
    return a - b


@mcp.tool(description="Multiply two numbers")
def multiply(a: float, b: float) -> float:
    return a * b


@mcp.tool(description="Divide two numbers")
def divide(a: float, b: float) -> float:
    if b == 0:
        return float('inf')
    return a / b


@mcp.tool(description="Calculate with history tracking")
def calculate(ctx: Context, op: str, a: float, b: float) -> dict:
    """Perform calculation and track in history."""
    ops = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else float('inf')
    }

    if op not in ops:
        return {"error": f"Unknown operation: {op}"}

    result = ops[op](a, b)

    # Track in context vault
    history = ctx.get("calc_history") or []
    history.append({"op": op, "a": a, "b": b, "result": result})
    ctx.set("calc_history", history)

    return {"result": result, "history_count": len(history)}


@mcp.resource("calc://history")
def get_history(ctx: Context) -> dict:
    """Get calculation history from context vault."""
    history = ctx.get("calc_history") or []
    return {"history": history, "count": len(history)}


if __name__ == "__main__":
    print("=" * 50)
    print("SecureMCP Calculator Server")
    print("=" * 50)
    print()
    print("Tools: add, subtract, multiply, divide, calculate")
    print("Resources: calc://history")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)
    mcp.run()
