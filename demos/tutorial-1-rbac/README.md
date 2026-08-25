# Tutorial 1: Role-Based AI Access Control

This tutorial demonstrates MACAW's policy enforcement for a fictional FinTech Corp with hierarchical policies.

## Overview

The demo shows how different users get different AI capabilities based on their organizational role:

| User | Role | Models | Max Tokens |
|------|------|--------|------------|
| alice | Financial Analyst | GPT-3.5 only | 500 |
| bob | Finance Manager | GPT-3.5, GPT-4 | 2000 |
| carol | IT Administrator | All models | 4000 |

## Directory Structure

```
tutorial-1/
├── app.py                    # Main demo (recommended starting point)
├── authprompts_demo.py       # Advanced: authenticated prompts demo
├── demo_secureopenai_with_policies.py  # Advanced: invoke_tool patterns
├── config/
│   └── claims-config.yaml    # Universal JWT claims mapper
├── policies/
│   ├── company_FinTech_Corp.json
│   ├── bu_Analytics.json
│   ├── team_Reporting.json
│   ├── user_alice.json
│   ├── user_bob.json
│   ├── user_carol.json
│   └── llm-base.json
├── setup/
│   ├── keycloak_complete_setup.sh  # For Keycloak IdP
│   └── auth0_complete_setup.sh     # For Auth0 IdP
└── README.md
```

## Quick Start

### 1. Prerequisites

- Python 3.9+
- MACAW Console account ([console.macawsecurity.ai](https://console.macawsecurity.ai))
- macaw_client installed and configured
- OpenAI API key

### 2. Install Dependencies

```bash
pip install macaw-adapters[openai]
```

### 3. Set Up Identity Provider

Choose one:

**Option A: Keycloak (Local)**
```bash
# Start Keycloak
docker run -d -p 8080:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin123 \
  quay.io/keycloak/keycloak:23.0 start-dev

# Wait for startup, then run setup
cd setup
./keycloak_complete_setup.sh
```

**Option B: Auth0 (Cloud)**
```bash
# Set your Auth0 credentials
export AUTH0_DOMAIN=your-tenant.auth0.com
export AUTH0_M2M_CLIENT_ID=your-m2m-client-id
export AUTH0_M2M_CLIENT_SECRET=your-m2m-secret

cd setup
./auth0_complete_setup.sh
```

### 4. Configure MACAW

Update `~/.macaw/config.json` with your IdP settings. The setup scripts will provide the exact values.

### 5. Load Policies

Import the policies from the `policies/` directory into your MACAW workspace via the Console.

### 6. Run the Demo

```bash
export OPENAI_API_KEY=sk-your-key
python3 app.py
```

## What the Demo Shows

1. **Authentication**: Each user authenticates with the IdP (Keycloak/Auth0)
2. **Policy Resolution**: MACAW resolves the user's effective policy from the hierarchy
3. **Enforcement**: Requests are allowed or blocked based on policy rules

### Expected Output

```
Testing alice (Financial Analyst)
  Test 1: GPT-3.5 with 400 tokens
    [PASS] Response received: ...
  Test 2: GPT-4 with 400 tokens
    [PASS] Correctly blocked: model not allowed
  Test 3: GPT-3.5 with 1000 tokens (exceeds limit)
    [PASS] Correctly blocked: exceeds max_tokens
```

## Policy Hierarchy

The policies demonstrate MACAW's hierarchical policy model:

```
company_FinTech_Corp (base restrictions)
    └── bu_Analytics (business unit)
        └── team_Reporting (team level)
            └── user_alice (individual user)
```

Lower levels can only restrict, never expand permissions from parent policies.

## Claims Mapping

The `config/claims-config.yaml` shows how MACAW maps JWT claims from different IdPs to a common format:

- Keycloak: `realm_access.roles` → `macaw.roles`
- Auth0: `https://macaw.local/roles` → `macaw.roles`
- Azure AD: `roles` → `macaw.roles`
- etc.

This allows the same policies to work with any OIDC-compliant IdP.

## Next Steps

- Explore the full policies in `policies/`
- Try modifying user policies and re-running
- Check the MACAW Console Logs tab to see policy decisions
- Read about [Authenticated Prompts](https://docs.macawsecurity.ai/concepts/authenticated-prompts) for the advanced demos
