#!/usr/bin/env python3
"""
Example 1f: MCP Elicitation - SERVER

Demonstrates ctx.elicit() - server requesting user input from client.

The server tools here use ctx.elicit() to interactively request
information from the user during execution.

Run this server, then run 1f_elicitation_client.py in another terminal.
"""

from macaw_adapters.mcp import SecureMCP, Context

mcp = SecureMCP("elicitation-demo")


@mcp.tool(description="Create user profile interactively")
async def create_profile(ctx: Context) -> dict:
    """Create a profile by asking the user questions."""
    ctx.info("Starting profile creation")

    name = await ctx.elicit(
        prompt="What is your name?",
        input_type="text",
        required=True
    )

    role = await ctx.elicit(
        prompt="What is your role?",
        options=["Developer", "Designer", "Manager", "Other"],
        input_type="select"
    )

    ctx.audit(action="profile_created", target="user_profile", outcome="success", name=name)

    return {"name": name, "role": role, "status": "created"}


@mcp.tool(description="Delete with confirmation")
async def delete_item(ctx: Context, item_name: str) -> dict:
    """Delete an item with user confirmation."""
    ctx.info(f"Request to delete: {item_name}")

    confirmed = await ctx.elicit(
        prompt=f"Delete '{item_name}'? This cannot be undone.",
        input_type="confirm",
        default="no"
    )

    if confirmed:
        ctx.audit(action="delete", target=item_name, outcome="success")
        return {"deleted": item_name, "status": "deleted"}
    else:
        ctx.info("Deletion cancelled")
        return {"deleted": None, "status": "cancelled"}


if __name__ == "__main__":
    print("=" * 50)
    print("Example 1f: Elicitation Demo Server")
    print("=" * 50)
    print()
    print("Tools: create_profile, delete_item")
    print()
    print("These tools use ctx.elicit() to request user input")
    print("during execution (human-in-the-loop).")
    print()
    print("Run client: python3 1f_elicitation_client.py")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)
    mcp.run()
