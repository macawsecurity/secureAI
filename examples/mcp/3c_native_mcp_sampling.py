#!/usr/bin/env python3
"""
3c_native_mcp_sampling.py - MCP Sampling through the native endpoint

The duplex test. A vanilla MCP client (no MACAW code) calls a SecureMCP tool,
and that tool calls back OUT to this client's LLM via ctx.sample():

    this client --tools/call--> sampling-demo's MCP endpoint
                                     |
                                     +--> invoke_tool --> PEP --> summarize()
                                                                      |
                                                            ctx.sample()
                                                                      |
                              +--- invoke_tool("_mcp_sample") <-------+
                              |         (over the MACAW bus)
                              v
                       the endpoint's stub agent
                              |
                              +--- sampling/createMessage --> this client's callback
                                                                      |
                                                              Anthropic API
                                                                      |
    summary <---------------------------------------------------------+

Both directions cross the boundary: the request goes in over JSON-RPC and down
through the MACAW PEP; the LLM callback comes back out over the same JSON-RPC
session. This is the same _mcp_sample mechanism 1e_sampling_client.py uses over
the bus - the only difference is that the stub forwards it over MCP instead of
calling an LLM directly.

Prerequisites:
    - MACAW LocalAgent running
    - pip install mcp anthropic
    - ANTHROPIC_API_KEY set (this is the client's LLM - the whole point of sampling)

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    python 3c_native_mcp_sampling.py

    (this spawns 1e_sampling_server.py itself - no separate terminal needed)
"""

import asyncio
import os
import sys
from pathlib import Path

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext
import mcp.types as types

SERVER = Path(__file__).parent / "1e_sampling_server.py"
MODEL = "claude-opus-4-8"

llm = anthropic.Anthropic()


async def sampling_callback(
    context: RequestContext,
    params: types.CreateMessageRequestParams,
) -> types.CreateMessageResult | types.ErrorData:
    """Serve the server's ctx.sample() request using THIS client's LLM.

    This is the client half of MCP sampling: the server has no model of its own,
    so it borrows ours. Nothing here knows about MACAW.
    """
    prompt = "\n".join(
        block.text for m in params.messages
        if (block := m.content).type == "text"
    )
    print(f"  [LLM] <- server asked: {prompt[:70]}...")

    def call(**extra):
        return llm.messages.create(
            model=MODEL,
            max_tokens=params.maxTokens,
            system=params.systemPrompt or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
            **extra,
        )

    # Forward a temperature only if the tool asked for one, and don't assume whether
    # this model takes it - try, and fall back if it doesn't. Current Claude models
    # (Opus 4.8/4.7, Sonnet 5, Fable 5) reject temperature/top_p/top_k with a 400;
    # older ones accept it. MCP treats sampling params as hints a client may ignore,
    # so degrading beats failing the call over one.
    extra = {} if params.temperature is None else {"temperature": params.temperature}
    try:
        try:
            response = call(**extra)
        except anthropic.BadRequestError:
            if not extra:
                raise
            print(f"  [LLM] {MODEL} rejected temperature={params.temperature}; retrying without")
            response = call()
    except anthropic.APIStatusError as e:
        return types.ErrorData(code=types.INTERNAL_ERROR, message=str(e))

    text = next((b.text for b in response.content if b.type == "text"), "")
    print(f"  [LLM] -> answered: {text[:70]}...")

    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text=text),
        model=response.model,
        stopReason="endTurn",
    )


async def main() -> int:
    print("=" * 60)
    print("Vanilla MCP client + sampling -> SecureMCP")
    print("=" * 60)

    params = StdioServerParameters(command=sys.executable, args=[str(SERVER), "stdio"])

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(
            read_stream, write_stream, sampling_callback=sampling_callback
        ) as session:
            init = await session.initialize()
            print(f"\nConnected to: {init.serverInfo.name}")

            listed = await session.list_tools()
            print(f"Tools: {[t.name for t in listed.tools]}\n")

            print("summarize() - the tool will call back to our LLM:")
            print("-" * 60)
            result = await session.call_tool("summarize", {
                "text": (
                    "MACAW places a policy enforcement point between an agent and the "
                    "tools it calls. Every invocation is checked against policy, signed, "
                    "and written to an audit log, so a non-deterministic model still "
                    "produces deterministic, reviewable actions."
                ),
                "max_length": 40,
            })
            print(f"  RESULT: {result.content[0].text}\n")

            print("analyze_sentiment() - same round trip:")
            print("-" * 60)
            result = await session.call_tool("analyze_sentiment", {
                "text": "I love this product! It's amazing and works perfectly!"
            })
            print(f"  RESULT: {result.content[0].text}")

    print("\n" + "=" * 60)
    print("Done - request in over MCP, LLM callback back out over MCP,")
    print("policy and audit in the middle. No MACAW code in this file.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        print("Sampling means the SERVER borrows THIS client's LLM, so a real key")
        print("is required - there is no mock path in this example by design.")
        sys.exit(1)
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nCheck that the MACAW LocalAgent is running.")
        sys.exit(1)
