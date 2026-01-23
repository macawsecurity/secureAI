# SecureLangChain Reference

Drop-in replacements for LangChain functions with optional MACAW security. Security is transparent - no code changes required beyond adding a `security_policy` parameter.

## Installation

```python
from macaw_adapters.langchain.agents import (
    create_react_agent,
    create_openai_functions_agent,
    AgentExecutor,
    cleanup
)
```

Install the package:
```bash
pip install -e /path/to/secureAI
```

## Functions

### create_react_agent

Drop-in replacement for LangChain's `create_react_agent`.

```python
agent = create_react_agent(
    llm,                        # Language model
    tools,                      # List of tools
    prompt,                     # Prompt template
    security_policy={...}       # Optional: security policy
)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `llm` | BaseLLM | Yes | Language model to use |
| `tools` | List[BaseTool] | Yes | Available tools |
| `prompt` | PromptTemplate | Yes | Agent prompt template |
| `security_policy` | dict | No | Simple security policy format |
| `**kwargs` | dict | No | Additional args for original function |

### create_openai_functions_agent

Drop-in replacement for LangChain's `create_openai_functions_agent`.

```python
agent = create_openai_functions_agent(
    llm,                        # OpenAI-compatible model
    tools,                      # List of tools
    prompt,                     # Prompt template
    security_policy={...}       # Optional: security policy
)
```

### AgentExecutor

Drop-in replacement for LangChain's `AgentExecutor`.

```python
executor = AgentExecutor(
    agent,                      # Agent instance
    tools,                      # List of tools
    security_policy={...}       # Optional: security policy
)

result = executor.invoke({"input": "What's the weather?"})
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent` | Runnable | Yes | The agent to use |
| `tools` | List[BaseTool] | Yes | Available tools |
| `security_policy` | dict | No | Simple security policy format |
| `**kwargs` | dict | No | Additional args for original class |

### cleanup

Clean up all active MACAW clients.

```python
cleanup()
```

## Security Policy Format (Simple)

The adapter accepts a simplified policy format and converts it to MAPL:

```python
security_policy = {
    # Allowed tools (whitelist)
    "allowed_tools": ["calculator", "search", "weather"],

    # Blocked tools (blacklist)
    "blocked_tools": ["dangerous_tool", "admin_tool"],

    # Allowed file paths (patterns)
    "allowed_files": ["*reports*", "*public*", "*temp*"],

    # Blocked query patterns
    "blocked_queries": ["*password*", "*credentials*", "*secret*"]
}
```

### Policy Conversion

The simple format is automatically converted to MAPL:

| Simple Format | MAPL Format |
|---------------|-------------|
| `allowed_tools: ["calc"]` | `resources: ["tool:calc"]` |
| `blocked_tools: ["admin"]` | `denied_resources: ["tool:admin"]` |
| `allowed_files: ["*public*"]` | `constraints.parameters.tool:file_reader.path` |
| `blocked_queries: ["*pass*"]` | `constraints.denied_parameters.tool:*.query` |

## Examples

### Basic Usage (No Security)

```python
from langchain.chat_models import ChatOpenAI
from langchain.tools import Tool
from langchain.agents import create_react_agent
from langchain import hub

# Same as original LangChain - no security
llm = ChatOpenAI()
tools = [Tool(name="calculator", func=lambda x: eval(x), description="Calculator")]
prompt = hub.pull("hwchase17/react")

agent = create_react_agent(llm, tools, prompt)
```

### With Security Policy

```python
from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor

llm = ChatOpenAI()
tools = [
    Tool(name="calculator", func=lambda x: eval(x), description="Calculator"),
    Tool(name="search", func=lambda q: f"Results for {q}", description="Search")
]
prompt = hub.pull("hwchase17/react")

# Add security - just one parameter
agent = create_react_agent(
    llm, tools, prompt,
    security_policy={
        "allowed_tools": ["calculator", "search"],
        "blocked_queries": ["*password*", "*admin*"]
    }
)

executor = AgentExecutor(
    agent, tools,
    security_policy={
        "allowed_tools": ["calculator", "search"],
        "blocked_queries": ["*password*", "*admin*"]
    }
)

# Tool calls now routed through MACAW PEP
result = executor.invoke({"input": "Calculate 2+2"})
```

### Authenticated Prompts

LLM prompts are automatically authenticated when security is enabled:

```python
# When security_policy is provided:
# 1. LLM is invisibly wrapped with authenticated prompt creation
# 2. All prompts get cryptographic signatures
# 3. Audit trail captures prompt lineage
```

## Security Features

### Tool Wrapping

When `security_policy` is provided:

1. **SecureToolWrapper**: Each tool is wrapped with MACAW routing
2. **PEP Enforcement**: Tool calls go through Policy Enforcement Point
3. **Audit Logging**: All tool invocations are logged
4. **Policy Violations**: Blocked calls return "Access denied by security policy"

### LLM Wrapping

When `security_policy` is provided:

1. **_AuthenticatedLLMWrapper**: LLM invisibly wrapped
2. **Prompt Authentication**: All prompts get authenticated
3. **Security Context**: Policy and agent ID bound to prompts
4. **Transparent**: LLM interface unchanged

## Migration Guide

```python
# Before (original LangChain)
from langchain.agents import create_react_agent, AgentExecutor

agent = create_react_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)

# After (with security)
from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor

agent = create_react_agent(
    llm, tools, prompt,
    security_policy={"blocked_queries": ["*password*"]}
)
executor = AgentExecutor(
    agent=agent, tools=tools,
    security_policy={"blocked_queries": ["*password*"]}
)

# Same API - security is optional and transparent
```

## Cleanup

Always clean up MACAW clients when done:

```python
from macaw_adapters.langchain.agents import cleanup

# Manual cleanup
cleanup()

# Auto-cleanup on module exit is registered via atexit
```
