# Tutorial 3: Object-Based Access Control


This tutorial attaches the rules to the data. An **object policy** on each data product sets which tables it exposes; a **content verifier** holds every query to read-only, no destructive SQL.
An object policy attaches rules to a data object, dataset, table etc.

## Why This Matters

| Problem | How MACAW handles it |
|---------|----------------------|
| One tool reaches many data products, and each needs its own rules. | Attach a separate object policy per data product; MACAW resolves the right one at runtime from `data_product_id`. |
| A sensitive object needs tighter limits than the rest. | Write a restrictive policy for just that object. It narrows what the data source allows and leaves the others untouched. |
| A new or unpoliced object has no rule yet. | It falls back to `alation:base`, which requires admin approval, so it is safe by default. |

## Attaching a Policy to a Thing

Here the object is a **data product**, a curated set of tables drawn from a data source.
The app policy carries the reference `alation:{params.data_product_id}`, and MACAW resolves it per request:

- **Policy exists** → it extends the data source policy `alation:databricks` and can only narrow it:
  fewer tables, never more.
- **No policy** → falls back to `alation:base`, which requires an admin attestation before anything runs.

| Object | Policy | Effect |
|--------|--------|--------|
| Data source (Databricks) | `alation:databricks` | which SQL tools may run against the data source |
| Data product | `alation:<your-data_product_id>` | extends `alation:databricks`, allows a set of tables, denies `eng_comp` |
| no data product policy | `alation:base` (fallback) | `admin_approval_required` |

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
└── README.md
```

## Quick Start

### 1. Prerequisites

- Python 3.12+
- MACAW console account
- macaw client installed and configured
- An Alation tenant
- A Databricks workspace

### 2. Install Dependencies

```bash
pip install "$MACAW_HOME"/macaw_client-*.whl "$MACAW_HOME/secureAI[all]"
pip install sqlglot
```

### 3. Platform Setup

Before the policies mean anything, the catalog objects they name have to exist. Set these up once:

- **Databricks tables**: create a `macaw_demo` schema in your `workspace` catalog with the tables
  the demo gates on: `workspace.macaw_demo.eng_comp` (the sensitive table the data product policy
  denies) plus a few tables whose names match the allowed set, `customer`, `finance`,
  `engineering`, or `sales_`.
- **Data source**: attach that Databricks workspace to Alation as a data source. Its policy is
  `alation:databricks`.
- **Data product**: create a data product on top of that data source. Its id becomes the policy id
  `alation:<your-data_product_id>`.
- **Custom agent tool**: in Alation, create a custom agent / tool that exposes a `sql` parameter, so
  it is called with SQL the verifier can see. Use its name for `<your-custom-agent-tool-name>`.

```bash
export ALATION_BASE_URL="https://<tenant>.alationcloud.com"
export ALATION_CLIENT_ID="<oauth client id>"
export ALATION_CLIENT_SECRET="<oauth client secret>"
export ALATION_MCP_URL="https://<tenant>.alationcloud.com/ai/mcp/<uuid>"
```

### 4. Get the Alation Token

Run `utility/get_token.py`. It opens a browser where you log in and returns an access token and a
refresh token.

```bash
export ALATION_TOKEN="<the access token>"
```

Later, reuse the refresh token to get a new access token without the browser:

```bash
python utility/get_token.py --refresh <REFRESH_TOKEN>
```

### 5. Load Policies

Import the policies from `Policy/` into your MACAW workspace via the Console: Policies → Add Policy →
Code Editor → paste JSON → Validate → Save.

Before loading, replace the placeholders with your own values:

- `<your-custom-agent-tool-name>` → your Alation tool name. Replace it in `databricks_datasource.json`
  and `dataproduct.json`, **and** add it to `resource_patterns` in `utility/alation_verifier.py` so the
  verifier fires on it, otherwise the statement-type check silently skips your tool.
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

### 6. Register the Proxy

`script.py` fronts the Alation MCP with a `SecureMCPProxy` and adds the verifier. Register it as a
stdio MCP server:

```bash
claude mcp add alation-databricks --scope user \
  -- bash -lc 'source <path to venv>/bin/activate && \
     export MACAW_HOME="<path to macaw-client>" && \
     export ALATION_MCP_URL="https://<tenant>.alationcloud.com/ai/mcp/<uuid>" && \
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

The verifier is the content half. A SQL tool exposes free-form SQL, but MAPL can only match parameter
values, not read a query. So the verifier parses the SQL with sqlglot before the policy decision and
stamps one parameter the policy gates on:

`utility/alation_verifier.py`: AlationSQLGuardVerifier

```python
proxy.macaw_client.agent.verification_pipeline.add_verifier(AlationSQLGuardVerifier(), priority=20)
```

| Parameter | Values | Comes from |
|-----------|--------|------------|
| `stmt_type` | select, update, insert, delete, merge, create, drop, truncate, other, nl_only, denied | the AST root node |

The data source floor (`alation:databricks`) allows `stmt_type` = `select` only, so every write or
DDL is blocked.

| What it does | The problem it solves |
|--------------|-----------------------|
| Classifies by the statement's real root node, not by keywords | `INSERT … SELECT` contains the word SELECT but writes |
| Allow-list: anything unrecognized becomes `other` | DROP / TRUNCATE / MERGE / CTAS destroy data without the word DELETE |
| Fails closed, empty, multi-statement, or unparseable → `denied` | a query it cannot read is a query it cannot trust |
| A SQL tool called with no SQL is `nl_only` | otherwise Alation writes the SQL server-side, where the verifier can never see it |

The verifier only fires on tools listed in its `resource_patterns`, add your tool name there (step 5).

## What the Demo Shows

1. **Object Resolution**: MACAW resolves `alation:{params.data_product_id}` to the policy for the
   named catalog object
2. **Inheritance**: an existing data product policy extends the data source policy `alation:databricks`
3. **Fallback**: a data product with no policy resolves to `alation:base` and requires an admin attestation
4. **Content control**: the verifier stamps `stmt_type`, and the data source floor allows `select` only

### Expected Output

| # | Case | Request | Result | What MACAW said |
|---|---|---|---|---|
| 1 | Data product **with** a policy | query a data product whose `alation:<id>` policy exists | 🟢 RESOLVED | resolves to `alation:<data_product_id>`, which extends `alation:databricks` |
| 2 | Data product **without** a policy | query a data product with no `alation:<id>` policy | 🟡 ATTESTATION | falls back to `alation:base` → `Missing or invalid attestation: admin_approval_required` |
| 3 | Sensitive table in a covered data product | query `eng_comp` in a data product whose policy exists | 🔴 BLOCKED | the data product policy denies `eng_comp` |
