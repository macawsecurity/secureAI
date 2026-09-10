# Tutorial 3: Object-Based Access Control

This tutorial demonstrates object-based access controls, where the policy that applies to a request
is chosen by the Alation catalog object the request touches. Controls are specified through MAPL
policies enforced by the MACAW runtime invisbly. The Alation tools are accessed by Claude Code. We
use Alation as the contextual data layer and Databricks as the backend lakehouse. All these
components are replaceable modularly.

## Overview

The demo shows how a request is gated by the object it names, not just by who asks. The app policy
carries a dynamic object reference, `alation:{params.data_product_id}`, and MACAW resolves it at
request time:

- If a policy for that data product exists, it is used, and it **extends** the data source policy
  `alation:databricks` (intersection — the data product can only narrow what the data source allows).
- If no policy for that data product exists, resolution **falls back** to `alation:base`, which
  requires an admin attestation before anything runs.

The same tool call therefore resolves to a different effective policy depending on which catalog
object it names.

| Object | Policy | Effect |
|--------|--------|--------|
| Data source (Databricks) | `alation:databricks` | which SQL tools may run against the data source |
| Data product | `alation:<your-data_product_id>` | extends `alation:databricks`; allows a set of tables, denies `eng_comp` |
| *(no data product policy)* | `alation:base` (fallback) | `admin_approval_required` |

## Directory Structure

```
tutorial-3-gating-object/
├── script.py                       # SecureMCPProxy over the Alation MCP, registered as an MCP server
├── Policy/
│   ├── base.json                   # alation:base
│   ├── app_alation.json            # app:alation
│   ├── databricks_datasource.json  # alation:databricks (data source object)
│   └── dataproduct.json            # alation:<your-data_product_id> (data product object)
├── utility/
│   ├── alation_verifier.py         # AlationSQLGuardVerifier
│   └── get_token.py                # Alation OAuth + PKCE token
└── Readme.md
```

## Quick Start

### 1. Prerequisites

- Python 3.12+
- MACAW console account
- macaw client installed and configured
- env's configured
- A alation tenant
- A databricks workspace

#### Platform setup

Before the policies mean anything, the catalog objects they name have to exist. Set these up once:

- **Databricks tables** — create a `macaw_demo` schema in your `workspace` catalog with the tables
  the demo gates on: `workspace.macaw_demo.eng_comp` (the sensitive table the data product policy
  denies) plus a few tables whose names match the allowed set — `customer`, `finance`,
  `engineering`, or `sales_`.
- **Data source** — attach that Databricks workspace to Alation as a data source. Its policy is
  `alation:databricks`.
- **Data product** — create a data product on top of that data source. Its id becomes the policy id
  `alation:<your-data_product_id>`.
- **Custom agent tool** — in Alation, create a custom agent / tool that takes a `sql` parameter, so
  Claude Code can call it. Use its name for `<your-custom-agent-tool-name>` in the policies (step 5).

```bash
export ALATION_BASE_URL="https://<tenant>.alationcloud.com"
export ALATION_CLIENT_ID="<oauth client id>"
export ALATION_CLIENT_SECRET="<oauth client secret>"
export ALATION_MCP_URL="https://<tenant>.alationcloud.com/ai/mcp/<uuid>"
```

### 2. Install Dependencies

```bash
pip install "$MACAW_HOME"/macaw_client-*.whl "$MACAW_HOME/secureAI[all]"
pip install sqlglot
```



### 3. Get the Alation Token

To get alation token run, `utility/get_token.py`

This open a browser where you login to get a access token and a refresh token.

```bash
export ALATION_TOKEN="<the access token>"
```

Later you can use the same refresh token to get a new access token without the going through the
browser again.

```bash
python utility/get_token.py --refresh <REFRESH_TOKEN>
```

### 4. Load Policies

Import the policies from the `Policy/` directory into your MACAW workspace via the Console.
Load each one: Policies → Add Policy → Code Editor → paste JSON → Validate → Save.

Before loading, replace the placeholders with your own values. The policies guard a single Alation
agent tool that takes a `sql` parameter, which the verifier stamps `stmt_type` on. You must have
created that tool in Alation (see Platform setup) before the policies mean anything.

- `<your-custom-agent-tool-name>` → the name of the custom agent tool you created in Alation. Replace
  it in `databricks_datasource.json` and `dataproduct.json`.
- `<your-data_product_id>` → the data product id you query (the policy id becomes `alation:<that id>`).
  Replace it in `dataproduct.json`.

| # | File | Policy id |
|---|---|---|
| 1 | `Policy/base.json` | `alation:base` |
| 2 | `Policy/app_alation.json` | `app:alation` |
| 3 | `Policy/databricks_datasource.json` | `alation:databricks` |
| 4 | `Policy/dataproduct.json` | `alation:<your-data_product_id>` |

#### Policy Hierarchy

The policies demonstrate MACAW's object policy model:

```
app:alation
    tool:alation/<sql tool>  attests  alation:{params.data_product_id}
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
        data product policy exists                                no such policy
                    │                                                   │
    alation:<your-data_product_id>                                  alation:base
                    └── extends alation:databricks              admin_approval_required
```

A data product policy can only restrict, never expand, what `alation:databricks` allows.

### 5. Register the Proxy

`script.py` fronts the Alation MCP with a `SecureMCPProxy` and adds the verifier. Register it as a
stdio MCP server. Fill in the four placeholders below with your own values — everything lives inside
the one command.

```bash
claude mcp add alation-databricks --scope user \
  -- bash -lc 'source <path to venv>/bin/activate && \
     export MACAW_HOME="<path to macaw-client-0.9.9.6-Linux-x86_64-py3.12>" && \
     export ALATION_MCP_URL="https://<tenant>.alationcloud.com/ai/mcp/<uuid>" && \
     export ALATION_BASE_URL= "<your-alation-tenant>" && \
     export ALATION_TOKEN="<fresh bearer>" && \
     cd <path to tutorial-3-gating-object> && \
     python script.py stdio'
```

Remove with:  `claude mcp remove alation-databricks`

You can also run it directly to confirm it starts and lists the upstream tools:

```bash
python script.py stdio
```

## Custom Verifier

Custom verifiers run inside the verification pipeline before the policy decision, compute facts
about the request, and stamp them onto the parameters so MAPL can gate on them.

`utility/alation_verifier.py` — AlationSQLGuardVerifier

```python
proxy.macaw_client.agent.verification_pipeline.add_verifier(AlationSQLGuardVerifier(), priority=20)
```

It parses the SQL with sqlglot and stamps three parameters:

| Parameter | Values | Comes from |
|-----------|--------|------------|
| `stmt_type` | select, update, insert, delete, merge, create, drop, truncate, other, nl_only, denied | the AST root node |
| `touches_salary` | true / false | any identifier containing salary (SENSITIVE_TOKENS) |
| `touches_eng_comp` | true / false | any table in SENSITIVE_TABLES = ("eng_comp",) |

| What it does | Why |
|--------------|-----|
| Looks at what the statement really is, not the words in it | INSERT … SELECT has the word SELECT in it, but it writes |
| Only the types it recognises get through | anything else is marked other, and no policy allows other |
| If it cannot read the SQL, it says no | empty, two statements at once, or unparseable → denied |
| A SQL tool called with no SQL is refused | otherwise Alation writes the SQL itself, where we cannot see it |
| Matches the table name however it is written | workspace.macaw_demo.eng_comp matches, eng_comp_archive does not |
| Checks every SQL field and keeps the worst answer | a safe sql cannot hide a dangerous query |

## What the Tutorial Shows

1. **Object Resolution**: MACAW resolves `alation:{params.data_product_id}` to the policy for the
   named catalog object
2. **Inheritance**: an existing data product policy extends the data source policy `alation:databricks`
3. **Fallback**: a data product with no policy resolves to `alation:base` and requires an admin attestation

### Expected Output

| # | Case | Request | Result | What MACAW said |
|---|---|---|---|---|
| 1 | Data product **with** a policy | query a data product whose `alation:<id>` policy exists | 🟢 RESOLVED | resolves to `alation:<data_product_id>`, which extends `alation:databricks` |
| 2 | Data product **without** a policy | query a data product with no `alation:<id>` policy | 🟡 ATTESTATION | falls back to `alation:base` → `Missing or invalid attestation: admin_approval_required` |
| 3 | Sensitive table in a covered data product | query `eng_comp` in a data product whose policy exists | 🔴 BLOCKED | the data product policy denies `eng_comp` |
