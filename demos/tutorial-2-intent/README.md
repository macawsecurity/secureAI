# Tutorial 2: Intent-Based Access Control

This tutorial demonstrates intent-based access controls, policy enforcement, model restrictions and
action-tracking for a fictional XYZ Corp. Controls are specified through MAPL policies enforced by
the MACAW runtime invisbly. We use Alation as the contextual data layer, Databricks as the backend
lakehouse, and OpenAI as the LLM of choice. All these components are replaceable modularly.

## Why This Matters

| Problem | How MACAW handles it |
|---------|----------------------|
| Different roles should not get the same AI power, but the app code is identical for everyone. | Policy resolves from the caller's role (`company` → `BU` → `user`); each layer only narrows model, tokens, and SQL. |
| Access should track real org identity, not hard-coded user checks. | Identity comes from the IdP's JWT claims, mapped to policy ids, so the same policies work with any OIDC provider. |
| The same tool call is safe or dangerous by intent; a grant cannot tell `SELECT` from `DELETE`. | A verifier reads the SQL and stamps what it does; the policy allows `select`/`update` and blocks the rest. |
| Some requests need a person's sign-off, not a binary allow or deny. | Human in the loop: the policy holds the query for a manager's attestation before it runs. |

## Overview

| User | Role | Tool available | Model available | Max Token | SQL allowed | Needs approval when |
|------|------|----------------|-----------------|-----------|-------------|---------------------|
| alice | Financial Analyst | `<your-custom-agent-tool-name>` | `gpt-4o-mini` | 100 | select, update | any statement touching `eng_comp` |
| bob | manager | `<your-custom-agent-tool-name>` | `gpt-4o-mini`, `gpt-4o` | 2000 | select, update | an UPDATE touching `eng_comp` |



## Directory Structure

```
demo-alation/
├── script.py                       # Main demo
├── Policies/
│   ├── company.json                # company:alation-MACAW
│   ├── bu.json                     # bu:analytics
│   ├── user_alice.json             # user:alice
│   ├── user_bob.json               # user:bob
│   └──  app_alation.json          # app:alation-remote-proxy
├── setup/
│   ├── alation_verifier.py         # AlationSQLGuardVerifier
│   └── get_alation_user_token.py   # Alation OAuth + PKCE token
└── README.md
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

- **Databricks tables**: create a `macaw_demo` schema in your `workspace` catalog with the tables
  the demo gates on: `workspace.macaw_demo.eng_comp` (the sensitive table that needs a manager's
  attestation) plus a few tables whose names match the allowed set, `customer`, `finance`,
  `engineering`, or `sales_`.
- **Data source**: attach that Databricks workspace to Alation as a data source.
- **Data product**: create a data product on top of that data source. Use its id for
  `DATA_PRODUCT` in `script.py`.
- **Custom agent tool**: in Alation, create a custom agent / tool that accepts `sql`, `message`, and
  `data_product_id` parameters (the demo calls it with all three, see `script.py`). Use its name for
  `SQL_TOOL` in `script.py`; it ships as the placeholder `<your-custom-agent-tool-name>`, replace it
  with yours.

```bash
export ALATION_BASE_URL="https://<tenant>.alationcloud.com"
export ALATION_CLIENT_ID="<oauth client id>"
export ALATION_CLIENT_SECRET="<oauth client secret>"
export ALATION_MCP_URL="https://<tenant>.alationcloud.com/ai/mcp/<uuid>"
export OPENAI_API_KEY="<key>"
```

### 2. Install Dependencies

```bash
pip install "$MACAW_HOME"/macaw_client-*.whl "$MACAW_HOME/secureAI[all]"
```

### 3. Set Up Identity Provider

Console → Tutorials → Make it Real → Connect Identity Provider → Option B.

While setting up the IdP, add two users, `alice` and `bob`, a shared password is fine. Put that
password in `script.py` (each user's `password` field in `USER_TESTS`); that is how the demo logs them in.

When done with the setup follow this claims mapping:

```yaml
name:
domain:
client_id:
client_secret:
api_audience:

mappings:
  subject_path:        sub
  email_path:          email
  name_path:           https://macaw.local/username
  organization_path:   https://macaw.local/organization
  roles_path:          https://macaw.local/roles
  team_path:           https://macaw.local/team
  business_unit_path:  https://macaw.local/business_unit
```

#### Claims Mapping

Each mapped claim becomes the name of a policy to look up:

| Claim | Value | Policy |
|-------|-------|--------|
| `name_path` → username | `alice` | `user:alice` |
| `business_unit_path` | `analytics` | `bu:analytics` |
| `organization_path` | `alation-MACAW` | `company:alation-MACAW` |
| `roles_path` | `["manager"]` | matches `approval_criteria: role:manager` |

This allows the same policies to work with any OIDC-compliant IdP.

### 4. Get the Alation Token

To get alation token run, `setup/get_alation_user_token.py`

This open a browser where you login to get a access token and a refresh token.

```bash
export ALATION_TOKEN="<the access token>"
```

Later you can use the same refresh token to get a new access token without the going through the
browser again.

```bash
python setup/get_alation_user_token.py --refresh <REFRESH_TOKEN>
```

### 5. Load Policies

Import the policies from the `Policies/` directory into your MACAW workspace via the Console.
Load each one: Policies → Add Policy → Code Editor → paste JSON → Validate → Save.

Before loading, replace the placeholder with your own tool. The policies guard a single Alation
agent tool that takes a `sql` parameter, shipped as the placeholder
`tool:alation-remote-proxy/<your-custom-agent-tool-name>`. In `user_alice.json`, `user_bob.json`, and
`app_alation.json`, replace `<your-custom-agent-tool-name>` with the name of the custom agent tool you
created in Alation (the same value you set as `SQL_TOOL` in `script.py`). The verifier stamps
`stmt_type` on that tool, and the policies gate on it.

| # | File | Policy id |
|---|---|---|
| 1 | `Policies/company.json` | `company:alation-MACAW` |
| 2 | `Policies/bu.json` | `bu:analytics` |
| 3 | `Policies/user_alice.json` | `user:alice` |
| 4 | `Policies/user_bob.json` | `user:bob` |
| 5 | `Policies/app_alation.json` | `app:alation-remote-proxy` |

#### Policy Hierarchy

The policies demonstrate MACAW's hierarchical policy model:

```
company:alation-MACAW (base restrictions)
    └── bu:analytics (business unit)
              └── user:bob (individual user)
              └── user:alice (individual user)

app:alation-remote-proxy
```



### 6. Run the Demo

```bash
export MACAW_HOME="<path to macaw-client-0.9.9.6-Linux-x86_64-py3.12>"
export ALATION_MCP_URL="https://<tenant>.alationcloud.com/ai/mcp/<uuid>"
export ALATION_TOKEN="<fresh 72h bearer>"    # from setup/get_alation_user_token.py
export OPENAI_API_KEY="<key>"

python script.py
```



## Custom Verifier

Custom verifiers run inside the verification pipeline before the policy decision, compute facts
about the request, and stamp them onto the parameters so MAPL can gate on them.

`setup/alation_verifier.py`: AlationSQLGuardVerifier

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

1. **Authentication**: Each user authenticates with the IdP (Keycloak/Auth0)
2. **Policy Resolution**: MACAW resolves the user's effective policy from the hierarchy
3. **Enforcement**: Requests are allowed or blocked based on policy rules

### Expected Output

**Bob**

| # | Call | Request | Result | What MACAW said |
|---|---|---|---|---|
| 1 | LLM | `gpt-4-turbo`, 80 tokens | 🔴 BLOCKED | `Parameter 'model'=gpt-4-turbo not in allowed values: ['gpt-4o-mini', 'gpt-4o']` |
| 2 | LLM | `gpt-4o`, 3000 tokens | 🔴 BLOCKED | `Parameter 'max_tokens'=3000 exceeds maximum: 2000` |
| 3 | LLM | `gpt-4o`, 500 tokens | 🟢 ALLOWED | *"Compound interest is the process where interest is added to the principal…"* |
| 4 | SQL | `SELECT name, base_salary FROM workspace.macaw_demo.eng_comp LIMIT 3` | 🟢 ALLOWED | rows returned |
| 5 | SQL | `SELECT COUNT(*) FROM workspace.macaw_demo.eng_comp` | 🟢 ALLOWED | `COUNT(*) = 4` |

**Alice**

| # | Call | Request | Result | What MACAW said |
|---|---|---|---|---|
| 1 | LLM | `gpt-4o`, 80 tokens | 🔴 BLOCKED | `Parameter 'model'=gpt-4o not in allowed values: ['gpt-4o-mini']` |
| 2 | LLM | `gpt-4o-mini`, 300 tokens | 🔴 BLOCKED | `Parameter 'max_tokens'=300 exceeds maximum: 100` |
| 3 | LLM | `gpt-4o-mini`, 80 tokens | 🟢 ALLOWED | *"Compound interest is the interest calculated on the initial principal…"* |
| 4 | SQL | `DELETE FROM workspace.macaw_demo.eng_comp WHERE name = 'nobody'` | 🔴 BLOCKED | `Parameter 'stmt_type'=delete not in allowed values: ['select', 'update']` |
| 5 | SQL | `SELECT name, base_salary FROM workspace.macaw_demo.eng_comp LIMIT 3` | 🟡 ATTESTATION | `Missing or invalid attestation: eng_comp_attestation` |

