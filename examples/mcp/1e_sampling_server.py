#!/usr/bin/env python3
"""
Example 1e: MCP Sampling - SERVER

Demonstrates ctx.sample() - server requesting LLM completions from client.

The server tools here use ctx.sample() to request AI assistance from
the client's configured LLM handler.

Run this server, then run 1e_sampling_client.py in another terminal.
"""

from macaw_adapters.mcp import SecureMCP, Context

mcp = SecureMCP("sampling-demo")


@mcp.tool(description="Summarize text using client's LLM")
async def summarize(ctx: Context, text: str, max_length: int = 100) -> dict:
    """Summarize text via client's LLM (ctx.sample)."""
    ctx.info(f"Summarizing {len(text)} characters")

    prompt = f"Summarize in {max_length} words or less:\n\n{text}\n\nSummary:"

    try:
        summary = await ctx.sample(
            prompt=prompt,
            system_prompt="You are a concise summarization assistant.",
            max_tokens=200,
            temperature=0.3
        )
        return {"summary": summary, "original_length": len(text)}
    except Exception as e:
        ctx.error(f"Sampling failed: {e}")
        return {"error": str(e)}


@mcp.tool(description="Analyze sentiment using client's LLM")
async def analyze_sentiment(ctx: Context, text: str) -> dict:
    """Analyze sentiment via client's LLM."""
    ctx.info("Analyzing sentiment")

    prompt = f"""Analyze sentiment. Respond with JSON:
{{"sentiment": "positive/negative/neutral", "confidence": 0.0-1.0}}

Text: {text}

JSON:"""

    try:
        analysis = await ctx.sample(
            prompt=prompt,
            system_prompt="You are a sentiment analyzer. Respond only with JSON.",
            max_tokens=100,
            temperature=0.1
        )
        return {"text": text[:50] + "..." if len(text) > 50 else text, "analysis": analysis}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import sys

    # Optional transport for native (non-MACAW) MCP clients:
    #   python 1e_sampling_server.py           MACAW mesh only (use 1e_sampling_client.py)
    #   python 1e_sampling_server.py stdio     also serve native MCP clients
    transport = sys.argv[1] if len(sys.argv) > 1 else None

    # stdout is the JSON-RPC stream when transport="stdio", so the banner goes to stderr.
    out = sys.stderr

    print("=" * 50, file=out)
    print("Example 1e: Sampling Demo Server", file=out)
    print("=" * 50, file=out)
    print(file=out)
    print("Tools: summarize, analyze_sentiment", file=out)
    print(file=out)
    print("These tools use ctx.sample() to request LLM completions", file=out)
    print("from the client's configured handler.", file=out)
    print(file=out)
    if transport:
        print(f"Also serving native MCP clients over: {transport}", file=out)
        print("Run client: python3 3c_native_mcp_sampling.py", file=out)
    else:
        print("Run client: python3 1e_sampling_client.py", file=out)
    print(file=out)
    print("Press Ctrl+C to stop", file=out)
    print("=" * 50, file=out)
    mcp.run(transport=transport)
