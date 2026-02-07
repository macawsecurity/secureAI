#!/usr/bin/env python3
"""
Example: SecureMCP Calculator Server

Demonstrates the FastMCP-compatible SecureMCP API:
- @mcp.tool decorator for registering tools
- @mcp.resource decorator for read-only resources
- @mcp.prompt decorator for prompt templates
- Context object for vault access
- Context logging: ctx.debug(), ctx.info(), ctx.warning(), ctx.error()
- Context audit: ctx.audit() for signed audit entries
- Progress reporting: ctx.report_progress()
- mcp.run() for starting the server

This is the recommended way to build MCP servers with MACAW security.
"""

import asyncio
from typing import List, Dict, Any

from macaw_adapters.mcp import SecureMCP, Context


# Create SecureMCP server - same pattern as FastMCP
mcp = SecureMCP("calculator", version="1.0.0")


# Tool: Add two numbers
@mcp.tool(description="Add two numbers together")
def add(a: float, b: float) -> float:
    """Add a + b and return the result."""
    return a + b


# Tool: Subtract two numbers
@mcp.tool(description="Subtract b from a")
def subtract(a: float, b: float) -> float:
    """Subtract a - b and return the result."""
    return a - b


# Tool: Multiply two numbers
@mcp.tool(description="Multiply two numbers")
def multiply(a: float, b: float) -> float:
    """Multiply a * b and return the result."""
    return a * b


# Tool: Divide two numbers
@mcp.tool(description="Divide a by b")
def divide(a: float, b: float) -> dict:
    """Divide a / b and return the result."""
    if b == 0:
        return {"error": "Division by zero"}
    return {"result": a / b}


# Tool with Context: Calculator with history tracking and logging
@mcp.tool(description="Calculate and track history")
def calculate(ctx: Context, operation: str, a: float, b: float) -> Dict[str, Any]:
    """
    Perform calculation and store in history.

    Demonstrates Context usage for:
    - Storing results in context vault (ctx.set)
    - Retrieving previous values (ctx.get)
    - Logging with ctx.info(), ctx.debug(), ctx.warning()
    - Audit logging with ctx.audit()
    """
    ctx.info(f"Calculating: {a} {operation} {b}")

    # Map operations to functions
    ops = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "error:div_by_zero"
    }

    if operation not in ops:
        ctx.warning(f"Unknown operation requested: {operation}")
        return {
            "result": None,
            "status": "invalid_operation",
            "message": f"Unknown operation: {operation}"
        }

    # Check for division by zero
    if operation == "divide" and b == 0:
        ctx.warning("Division by zero attempted")

    result = ops[operation](a, b)
    ctx.debug(f"Result computed: {result}")

    # Get existing history from context vault
    history = ctx.get("calc_history") or []

    # Add this calculation to history
    entry = {
        "operation": operation,
        "a": a,
        "b": b,
        "result": result
    }
    history.append(entry)

    # Store updated history in context vault
    ctx.set("calc_history", history)

    # Audit the calculation
    ctx.audit(
        action="calculation",
        target="calculator",
        outcome="success",
        operation=operation,
        operands=[a, b],
        result=result
    )

    return {
        "result": result,
        "expression": f"{a} {operation} {b} = {result}",
        "history_count": len(history)
    }


# Tool with Progress: Batch calculations
@mcp.tool(description="Perform multiple calculations with progress")
async def batch_calculate(ctx: Context, calculations: list) -> Dict[str, Any]:
    """
    Perform multiple calculations, reporting progress.

    Demonstrates:
    - ctx.report_progress() for long-running operations
    - Async tool execution

    Args:
        calculations: List of {"op": str, "a": float, "b": float}
    """
    total = len(calculations)
    if total == 0:
        return {"results": [], "count": 0}

    ctx.info(f"Starting batch of {total} calculations")
    await ctx.report_progress(0.0, f"Processing {total} calculations")

    ops = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "error:div_by_zero"
    }

    results = []
    for i, calc in enumerate(calculations):
        op = calc.get("op", "add")
        a = calc.get("a", 0)
        b = calc.get("b", 0)

        progress = i / total
        await ctx.report_progress(progress, f"Calculating {i+1}/{total}: {a} {op} {b}")

        if op in ops:
            result = ops[op](a, b)
            results.append({"expression": f"{a} {op} {b}", "result": result})
        else:
            results.append({"expression": f"{a} {op} {b}", "error": "unknown op"})

        await asyncio.sleep(0.1)  # Simulate work

    await ctx.report_progress(1.0, "Batch complete")
    ctx.info(f"Batch complete: {total} calculations")

    ctx.audit(
        action="batch_calculation",
        target="calculator",
        outcome="success",
        count=total
    )

    return {"results": results, "count": total}


# Resource: Get calculation history
@mcp.resource("calc://history", description="Get calculation history")
def get_history(ctx: Context) -> List[Dict[str, Any]]:
    """
    Read-only resource that returns calculation history.

    Resources are treated as read-only tools in SecureMCP.
    """
    history = ctx.get("calc_history") or []
    return {
        "history": history,
        "count": len(history)
    }


# Prompt: Generate a calculation prompt
@mcp.prompt(description="Generate a prompt for calculations")
def calculation_prompt(numbers: str, operation: str = "add") -> str:
    """
    Generate a calculation prompt template.

    Prompts are starting points for AuthenticatedPrompt creation.
    """
    return f"Please {operation} the following numbers: {numbers}"


if __name__ == "__main__":
    print("=" * 60)
    print("SecureMCP Calculator Server")
    print("=" * 60)
    print()
    print("This server provides:")
    print("  Tools: add, subtract, multiply, divide, calculate, batch_calculate")
    print("  Resources: calc://history")
    print("  Prompts: calculation_prompt")
    print()
    print("Demonstrates:")
    print("  - ctx.info/debug/warning/error() - Logging")
    print("  - ctx.audit() - Signed audit entries")
    print("  - ctx.report_progress() - Progress reporting")
    print("  - ctx.get/set() - Context vault")
    print()
    print("All invocations are secured by MACAW:")
    print("  - Cryptographic signing")
    print("  - Policy enforcement")
    print("  - Audit logging")
    print()
    print("Starting server...")
    print("=" * 60)

    # Run the server
    mcp.run()
