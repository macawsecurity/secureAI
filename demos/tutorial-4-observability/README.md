# Tutorial 4: Observability

This tutorial demonstrates zero-instrumentation observability: every agent operation lands in your observability stack as OpenTelemetry, with no logging code.

## Why This Matters

Four problems teams hit when they try to observe AI agents, and how MACAW handles each:

| Problem | How MACAW handles it |
|---------|----------------------|
| You already run an observability stack (Datadog, Splunk, Grafana, Jaeger, New Relic) and the telemetry has to land there. | Point MACAW at that backend once in the Console over OTLP. No host agent, no env vars, no code. |
| A consistent instrumentation standard is hard to hold across services. | One OTel event schema is emitted identically by every adapter. |
| The libraries you call are third-party code you cannot edit to add logging. | The SDK adapters are already instrumented; wrapping the call is all it takes. |
| Custom, application-specific events do not fit the standard schema. | `log_event()` puts business events in the same audit stream; `signed=True` signs and hash-chains them for compliance. |

## Overview

The demo generates two kinds of traffic; both land in the same OTel stream with no logging code:

| Source | Shows | Emits |
|--------|-------|-------|
| `test_harness.py` (repo root) | auto-instrumentation across the SDK adapters | `prompt_received`, `policy_fetch`, `policy_decision`, `tool_execution` |
| `1b_custom_log_event.py` | a custom business event in the same stream | `agent_registered`, `export_start`, `export_complete`, `agent_unregistered` |




## Directory Structure

```
tutorial-4-observability/
├── 1b_custom_log_event.py   # a custom log_event business event
└── README.md
```

Auto-instrumentation is shown by the repo's own `secureAI/test_harness.py`, which exercises the SDK
adapters end to end. There is no separate script here for it: the point is that logging is automatic,
so any traffic through the SDK is enough.

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

### 3. Set Up the Datadog Endpoint

Nothing is installed on the host. You need two things: your Datadog site URL and an API key.

**Find your site.** Open your logged-in Datadog tab and read the hostname in the address bar, before
the first `/`. The site is chosen at signup and cannot be changed. Append the signal path `/v1/logs` —
for US1 that is `https://otlp.datadoghq.com/v1/logs`.

**Create the API key.**

1. Go to `https://<site-hostname>/organization-settings/api-keys`.
2. **New Key** → name it `macaw-otel` (label only) → create.
3. In the **New API Key** dialog click **Copy**. It is 32 hex characters. Copy now, it is masked
   after you leave.

It must be an **API key**, not an Application key, in the same org as your site. Ignore the
Remote Config / PAR toggles.

### 4. Configure MACAW

Add the OTEL endpoint in the Console; the key never leaves it.

1. Console → the pane holding the Events Log / Audit Log and the Endpoints table
   ("Export events to observability…").
2. **Add OTEL Endpoint**.
3. **TEMPLATE** → **Datadog**.
4. Replace the CONFIGURATION JSON with exactly these four fields:

```json
{
  "endpoint": "https://otlp.datadoghq.com/v1/logs",
  "service_name": "<your-service-name>",
  "headers": { "dd-api-key": "<32-hex key from step 3>" },
  "signal": "logs"
}
```

- `endpoint`: your site URL plus `/v1/logs`. Full path, no trailing slash.
- `service_name`: your choice; becomes Datadog's `service` tag and every query keys off it. One per
  deployment.
- `signal`: `"logs"`. Use `"traces"` only for a trace-only backend (Jaeger).

5. **Add Endpoint**. Open the new row's detail card: a green dot and the footer **Connected, last
   export &lt;time&gt;**.

### 5. Run the Demo

Both need only the SDK and the provider keys for the LLM calls. No OTel or Datadog variables anywhere,
the export is already wired in the Console.

```bash
source <path to venv>/bin/activate
export MACAW_HOME="<path to macaw-client>"


# Auto-instrumentation: the repo harness exercises the SDK adapters. No logging code.
python ../../test_harness.py

# Custom events: a business event in the same stream via log_event.
python 1b_custom_log_event.py
```

Both flow to Datadog with no logging code and no OTel setup on the host.

### 6. Verify in Datadog

Go to `https://<site-hostname>/logs` → time range **Last 15 minutes** → query
`service:<your-service-name>`.


## What the Demo Shows

1. **Zero-instrumentation logging**: the complete request flow (tool invocations, policy evaluations, prompt lifecycle, agent registration) is emitted as OTel audit with no instrumentation code
2. **A consistent schema**: the same event shape flows from every adapter.
3. **One-time wiring**: configured once in the Console, with no env vars and nothing on the host
4. **Custom events**: `log_event` puts business events in the same audit stream

