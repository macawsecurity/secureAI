# SecureLiteLLM - MACAW-Protected LiteLLM Adapter

Drop-in replacement for [LiteLLM](https://github.com/BerriAI/litellm) with MACAW security.
Supports 100+ LLM providers through LiteLLM's unified interface.

## Installation

```bash
pip install macaw-adapters[litellm]
```

Or for development:

```bash
pip install -e ".[litellm]"
```

## Usage

### Drop-in Replacement

Just change your import - everything else stays the same:

```python
# Before
import litellm

# After
from macaw_adapters import litellm
```

### Examples

```python
from macaw_adapters import litellm

# Groq (Llama, Mixtral)
response = litellm.completion(
    model="groq/llama3-70b-8192",
    messages=[{"role": "user", "content": "Hello"}]
)

# Together AI (100+ models)
response = litellm.completion(
    model="together_ai/meta-llama/Llama-3-70b",
    messages=[{"role": "user", "content": "Hello"}]
)

# Mistral
response = litellm.completion(
    model="mistral/mistral-large-latest",
    messages=[{"role": "user", "content": "Hello"}]
)

# Local vLLM
response = litellm.completion(
    model="openai/llama3",
    messages=[{"role": "user", "content": "Hello"}],
    api_base="http://localhost:8000/v1"
)

# Local Ollama
response = litellm.completion(
    model="ollama/llama3",
    messages=[{"role": "user", "content": "Hello"}],
    api_base="http://localhost:11434"
)

# With explicit app name for MACAW registration
response = litellm.completion(
    model="groq/llama3-70b",
    messages=[{"role": "user", "content": "Hello"}],
    app_name="my-production-service"
)
```

### Class-Based Usage

For advanced control over the client lifecycle:

```python
from macaw_adapters.litellm import SecureLiteLLM

# Create client with custom configuration
client = SecureLiteLLM(
    app_name="my-app",
    intent_policy={"resources": ["llm:*"]}
)

# Use like regular litellm
response = client.completion(
    model="groq/llama3-70b",
    messages=[{"role": "user", "content": "Hello"}]
)

# Or OpenAI-style API
response = client.chat.completions.create(
    model="groq/llama3-70b",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### Tool Registration

Register tools that the LLM can call:

```python
from macaw_adapters.litellm import SecureLiteLLM

client = SecureLiteLLM(app_name="my-app")

# Register a tool
def get_weather(city: str) -> dict:
    return {"city": city, "temperature": 72, "condition": "sunny"}

client.register_tool("get_weather", get_weather)

# LLM can now call this tool (through MACAW policy enforcement)
response = client.completion(
    model="groq/llama3-70b",
    messages=[{"role": "user", "content": "What's the weather in NYC?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
        }
    }]
)
```

## Supported Providers

SecureLiteLLM supports all providers that LiteLLM supports, including:

| Provider | Model Format | Example |
|----------|--------------|---------|
| OpenAI | `gpt-4`, `gpt-3.5-turbo` | `model="gpt-4"` |
| Groq | `groq/<model>` | `model="groq/llama3-70b-8192"` |
| Together AI | `together_ai/<model>` | `model="together_ai/meta-llama/Llama-3-70b"` |
| Mistral | `mistral/<model>` | `model="mistral/mistral-large-latest"` |
| Anthropic | `claude-3-opus`, etc. | `model="claude-3-opus-20240229"` |
| AWS Bedrock | `bedrock/<model>` | `model="bedrock/anthropic.claude-3"` |
| Google Vertex | `vertex_ai/<model>` | `model="vertex_ai/gemini-pro"` |
| Azure OpenAI | `azure/<deployment>` | `model="azure/my-deployment"` |
| Cohere | `cohere/<model>` | `model="cohere/command-r-plus"` |
| vLLM (local) | `openai/<model>` | `model="openai/llama3"` + `api_base` |
| Ollama (local) | `ollama/<model>` | `model="ollama/llama3"` |

See [LiteLLM Providers](https://docs.litellm.ai/docs/providers) for the full list.

## Key Features

- **Drop-in replacement**: Just change `import litellm` to `from macaw_adapters import litellm`
- **100+ providers**: All LiteLLM-supported providers work automatically
- **MACAW security**: Full policy enforcement, attestations, and audit logging
- **Default app_name**: `macaw-litellm` (can be overridden per-call or at client creation)
- **Tool isolation**: User-registered tools are isolated and policy-protected

## Policy IDs

When using SecureLiteLLM, the following MAPL resource patterns are used:

| Operation | Resource ID |
|-----------|-------------|
| Chat completion | `tool:{app_name}/generate` |
| Text completion | `tool:{app_name}/complete` |
| Embeddings | `tool:{app_name}/embed` |
| User tools | `tool:{app_name}/{tool_name}` |

Example policy for a LiteLLM-based service:

```json
{
    "policy_id": "tool:my-app/generate",
    "resources": ["tool:my-app/generate"],
    "constraints": {
        "parameters": {
            "tool:my-app/generate": {
                "model": ["groq/llama3-70b-8192", "gpt-4"]
            }
        }
    }
}
```

## Environment Variables

LiteLLM uses provider-specific environment variables for API keys:

```bash
# Groq
export GROQ_API_KEY="your-key"

# Together AI
export TOGETHER_API_KEY="your-key"

# Mistral
export MISTRAL_API_KEY="your-key"

# OpenAI
export OPENAI_API_KEY="your-key"

# Or pass directly
response = litellm.completion(
    model="groq/llama3-70b",
    messages=[...],
    api_key="your-key"
)
```

## More Information

- [MACAW Security](https://macawsecurity.ai)
- [MACAW Console](https://console.macawsecurity.ai)
- [LiteLLM Documentation](https://docs.litellm.ai)
