# Tutorial 4: Observability

This tutorial demonstrates zero-instrumentation audit logging and OTEL export. Every agent operation
is automatically captured with cryptographic integrity. The MACAW SDK adapters come with inbuilt
logging to observability, so every tool invocation, policy evaluation, prompt lifecycle step, and
agent registration is recorded with no instrumentation code in your app. Use any MACAW SDK, the OpenAI
drop-in, the MCP proxy, whichever, and the complete request flow is emitted as structured OTel audit
automatically. For custom, application-specific events you can also use `MACAWClient.log_event()`; use
`signed=True` for compliance. You point MACAW at your existing observability stack once, in the
Console, and the same schema flows from every adapter. We use Datadog as the observability platform;
Splunk, Grafana, Jaeger, and New Relic are supported the same way. 

## Overview


This demo exercises two paths:

| Script | Shows | Emits |
|--------|-------|-------|
| `1a_autologging.py` | auto-instrumentation across three adapters (OpenAI, Anthropic, Pydantic AI) | `prompt_received`, `policy_fetch`, `policy_decision`, `tool_execution` |
| `1b_custom_log_event.py` | a custom business event in the same stream | `agent_registered`, `export_start`, `export_complete`, `agent_unregistered` |




## Directory Structure

```
tutorial-4-observability/
├── 1a_autologging.py        # three adapters, auto-logged, no logging code
├── 1b_custom_log_event.py   # a custom log_event business event
└── README.md
```

## Quick Start

### 1. Prerequisites

- Python 3.12+
- MACAW console account
- macaw client installed and configured
- A Datadog account
- Provider keys for the LLM calls (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

### 2. Install Dependencies

```bash
pip install "$MACAW_HOME"/macaw_client-*.whl "$MACAW_HOME/secureAI[all]"
```

### 3. Add the Datadog Endpoint

This is the whole setup. Nothing is installed on the host; the API key is entered in the Console.

#### 3.1 Determine your Datadog site

Open your logged-in Datadog tab and read the hostname in the address bar, before the first `/`. The
site is chosen at signup and cannot be changed.


Append the signal path `/v1/logs`.
Example  For US1: `https://otlp.datadoghq.com/v1/logs`.

#### 3.2 Create the Datadog API key

1. Go to `https://<site-hostname>/organization-settings/api-keys`.
2. **New Key** → name it `macaw-otel` (label only) → create.
3. In the **New API Key** dialog click **Copy**. It is 32 hex characters. Copy now, it is masked
   after you leave.

It must be an **API key**, not an Application key, in the same org as the site from 3.1. Ignore the
Remote Config / PAR toggles.

#### 3.3 Add the endpoint in the MACAW Console

1. Console → the pane holding the Events Log / Audit Log and the Endpoints table
   ("Export events to observability…").
2. **Add OTEL Endpoint**.
3. **TEMPLATE** choose → **Datadog**.
4. Replace the CONFIGURATION JSON with exactly these four fields:

```json
{
  "endpoint": "https://otlp.datadoghq.com/v1/logs",
  "service_name": "<your-service-name>",
  "headers": { "dd-api-key": "<32-hex key from 3.2>" },
  "signal": "logs"
}
```

- `endpoint`: the base URL from 3.1 plus `/v1/logs`. Full path, no trailing slash.
- `service_name`: your choice; becomes Datadog's `service` tag and every query keys off it. One per
  deployment.
- `signal`: `"logs"`. Use `"traces"` only for a trace-only backend (Jaeger).

5. **Add Endpoint**.

Open the new row's detail card: a green dot and the footer **Connected, last export &lt;time&gt;**.


### 4. Generate Traffic

Run both scripts. Each needs a venv with the SDK and the provider keys for the LLM calls, with no OTel or
Datadog variables anywhere, the export is already wired in the Console.

```bash
source <path to venv>/bin/activate
export MACAW_HOME="<path to macaw-client>"
export OPENAI_API_KEY="<key>"        # 1a openai + pydantic blocks
export ANTHROPIC_API_KEY="<key>"     # 1a anthropic block

python 1a_autologging.py
python 1b_custom_log_event.py
```
Both flow to Datadog with nologging code and no OTel setup on the host.

### 5. Verify in Datadog

Go to `https://<site-hostname>/logs` → time range **Last 15 minutes** → query
`service:<your-service-name>`.


## What the Tutorial Shows

1. **Zero-instrumentation logging**: the complete request flow (tool invocations, policy evaluations, prompt lifecycle, agent registration) is emitted as OTel audit with no instrumentation code
2. **One-time wiring**: the backend is configured once in the Console, with no env vars and nothing on the host
3. **Custom events**: `log_event` puts business events in the same signed stream

