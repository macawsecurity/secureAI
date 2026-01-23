#!/bin/bash
#
# Complete Auth0 Setup - Creates application, API, users, and custom claims action
#
# PREREQUISITES:
# 1. Create an Auth0 account at https://auth0.com
# 2. Create a Machine-to-Machine application for this script:
#    - Go to Applications -> Create Application -> Machine to Machine
#    - Name it: "MACAW Setup Script"
#    - Select the "Auth0 Management API"
#    - Grant these permissions:
#      * create:users, read:users, update:users, delete:users
#      * create:clients, read:clients, update:clients
#      * create:resource_servers, read:resource_servers
#      * create:actions, read:actions, update:actions
#      * read:client_grants, create:client_grants, update:client_grants
# 3. Set the environment variables below with your M2M app credentials
#

set -e

# ============================================================
# CONFIGURATION - Set these before running!
# ============================================================
AUTH0_DOMAIN="${AUTH0_DOMAIN:-your-tenant.auth0.com}"
AUTH0_M2M_CLIENT_ID="${AUTH0_M2M_CLIENT_ID:-}"
AUTH0_M2M_CLIENT_SECRET="${AUTH0_M2M_CLIENT_SECRET:-}"

# Application settings (these will be created)
APP_NAME="financial-analyzer"
APP_CLIENT_SECRET="macaw-secret-$(openssl rand -hex 8)"
API_IDENTIFIER="https://api.macaw.local"
API_NAME="MACAW API"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo "Complete Auth0 Configuration for MACAW"
echo "=========================================="

# ============================================================
# Validation
# ============================================================
if [ -z "$AUTH0_DOMAIN" ] || [ "$AUTH0_DOMAIN" = "your-tenant.auth0.com" ]; then
    echo -e "${RED}Error: AUTH0_DOMAIN not set${NC}"
    echo "Usage: AUTH0_DOMAIN=your-tenant.auth0.com AUTH0_M2M_CLIENT_ID=xxx AUTH0_M2M_CLIENT_SECRET=yyy ./auth0_complete_setup.sh"
    exit 1
fi

if [ -z "$AUTH0_M2M_CLIENT_ID" ] || [ -z "$AUTH0_M2M_CLIENT_SECRET" ]; then
    echo -e "${RED}Error: AUTH0_M2M_CLIENT_ID and AUTH0_M2M_CLIENT_SECRET must be set${NC}"
    echo ""
    echo "To get these credentials:"
    echo "1. Go to Auth0 Dashboard -> Applications -> Create Application"
    echo "2. Choose 'Machine to Machine Applications'"
    echo "3. Select 'Auth0 Management API'"
    echo "4. Grant permissions: create:users, read:users, create:clients, etc."
    echo "5. Copy the Client ID and Client Secret"
    exit 1
fi

# Check dependencies
if ! command -v jq &> /dev/null; then
    echo -e "${RED}jq is required but not installed.${NC}"
    echo "Install with: brew install jq (macOS) or apt install jq (Linux)"
    exit 1
fi

# ============================================================
# Step 1: Get Management API Token
# ============================================================
echo -e "${YELLOW}Step 1: Obtaining Management API token...${NC}"

MGMT_TOKEN_RESPONSE=$(curl -s -X POST "https://${AUTH0_DOMAIN}/oauth/token" \
    -H "Content-Type: application/json" \
    -d '{
        "client_id": "'"${AUTH0_M2M_CLIENT_ID}"'",
        "client_secret": "'"${AUTH0_M2M_CLIENT_SECRET}"'",
        "audience": "https://'"${AUTH0_DOMAIN}"'/api/v2/",
        "grant_type": "client_credentials"
    }')

MGMT_TOKEN=$(echo "$MGMT_TOKEN_RESPONSE" | jq -r '.access_token')

if [ -z "$MGMT_TOKEN" ] || [ "$MGMT_TOKEN" = "null" ]; then
    echo -e "${RED}Failed to get Management API token${NC}"
    echo "Make sure your M2M application has the correct permissions"
    exit 1
fi

echo -e "${GREEN}OK Management API token obtained${NC}"

# ============================================================
# Step 2: Create API (Resource Server)
# ============================================================
echo -e "${YELLOW}Step 2: Creating API (Resource Server)...${NC}"

EXISTING_API=$(curl -s "https://${AUTH0_DOMAIN}/api/v2/resource-servers" \
    -H "Authorization: Bearer ${MGMT_TOKEN}" | jq -r '.[] | select(.identifier == "'"${API_IDENTIFIER}"'") | .id')

if [ -n "$EXISTING_API" ] && [ "$EXISTING_API" != "null" ]; then
    echo -e "${BLUE}  API already exists, updating...${NC}"
    curl -s -X PATCH "https://${AUTH0_DOMAIN}/api/v2/resource-servers/${EXISTING_API}" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "'"${API_NAME}"'",
            "signing_alg": "RS256",
            "allow_offline_access": true,
            "token_lifetime": 86400
        }' > /dev/null
else
    curl -s -X POST "https://${AUTH0_DOMAIN}/api/v2/resource-servers" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "'"${API_NAME}"'",
            "identifier": "'"${API_IDENTIFIER}"'",
            "signing_alg": "RS256",
            "allow_offline_access": true,
            "token_lifetime": 86400
        }' > /dev/null
fi

echo -e "${GREEN}OK API created: ${API_IDENTIFIER}${NC}"

# ============================================================
# Step 3: Create Application (Client)
# ============================================================
echo -e "${YELLOW}Step 3: Creating application...${NC}"

EXISTING_APP=$(curl -s "https://${AUTH0_DOMAIN}/api/v2/clients" \
    -H "Authorization: Bearer ${MGMT_TOKEN}" | jq -r '.[] | select(.name == "'"${APP_NAME}"'") | .client_id')

if [ -n "$EXISTING_APP" ] && [ "$EXISTING_APP" != "null" ]; then
    echo -e "${BLUE}  Application already exists, updating...${NC}"
    APP_CLIENT_ID="$EXISTING_APP"

    curl -s -X PATCH "https://${AUTH0_DOMAIN}/api/v2/clients/${APP_CLIENT_ID}" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "app_type": "regular_web",
            "grant_types": ["password", "authorization_code", "refresh_token", "client_credentials"],
            "callbacks": ["http://localhost:3000/callback", "http://localhost:8000/callback"],
            "allowed_origins": ["http://localhost:3000", "http://localhost:8000"],
            "web_origins": ["http://localhost:3000", "http://localhost:8000"],
            "token_endpoint_auth_method": "client_secret_post"
        }' > /dev/null

    APP_CLIENT_SECRET=$(curl -s "https://${AUTH0_DOMAIN}/api/v2/clients/${APP_CLIENT_ID}" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" | jq -r '.client_secret')
else
    APP_RESPONSE=$(curl -s -X POST "https://${AUTH0_DOMAIN}/api/v2/clients" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "'"${APP_NAME}"'",
            "app_type": "regular_web",
            "grant_types": ["password", "authorization_code", "refresh_token", "client_credentials"],
            "callbacks": ["http://localhost:3000/callback", "http://localhost:8000/callback"],
            "allowed_origins": ["http://localhost:3000", "http://localhost:8000"],
            "web_origins": ["http://localhost:3000", "http://localhost:8000"],
            "token_endpoint_auth_method": "client_secret_post"
        }')

    APP_CLIENT_ID=$(echo "$APP_RESPONSE" | jq -r '.client_id')
    APP_CLIENT_SECRET=$(echo "$APP_RESPONSE" | jq -r '.client_secret')

    if [ -z "$APP_CLIENT_ID" ] || [ "$APP_CLIENT_ID" = "null" ]; then
        echo -e "${RED}Failed to create application${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}OK Application created: ${APP_NAME}${NC}"

# ============================================================
# Step 4: Enable ROPC (Password Grant)
# ============================================================
echo -e "${YELLOW}Step 4: Enabling Password Grant (ROPC)...${NC}"

TENANT_SETTINGS=$(curl -s "https://${AUTH0_DOMAIN}/api/v2/tenants/settings" \
    -H "Authorization: Bearer ${MGMT_TOKEN}")

if echo "$TENANT_SETTINGS" | jq -e '.default_directory' > /dev/null 2>&1; then
    curl -s -X PATCH "https://${AUTH0_DOMAIN}/api/v2/tenants/settings" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "default_directory": "Username-Password-Authentication"
        }' > /dev/null
    echo -e "${GREEN}OK Password Grant enabled${NC}"
else
    echo -e "${YELLOW}WARNING: Could not auto-enable ROPC. Please manually set:${NC}"
    echo "   Dashboard -> Settings -> API Authorization Settings -> Default Directory"
fi

# ============================================================
# Step 5: Create Users
# ============================================================
echo -e "${YELLOW}Step 5: Creating users...${NC}"

create_user() {
    local username=$1
    local email=$2
    local password=$3
    local tier=$4
    local max_tokens=$5
    local allowed_models=$6
    local org=$7
    local bu=$8
    local team=$9
    local roles=${10}

    EXISTING_USER=$(curl -s "https://${AUTH0_DOMAIN}/api/v2/users-by-email?email=${email}" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" | jq -r '.[0].user_id')

    if [ -n "$EXISTING_USER" ] && [ "$EXISTING_USER" != "null" ]; then
        echo -e "${BLUE}  User ${username} already exists, updating...${NC}"

        curl -s -X PATCH "https://${AUTH0_DOMAIN}/api/v2/users/${EXISTING_USER}" \
            -H "Authorization: Bearer ${MGMT_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{
                "app_metadata": {
                    "tier": "'"${tier}"'",
                    "max_tokens": '"${max_tokens}"',
                    "allowed_models": '"${allowed_models}"',
                    "organization": "'"${org}"'",
                    "business_unit": "'"${bu}"'",
                    "team": "'"${team}"'",
                    "roles": '"${roles}"'
                }
            }' > /dev/null
    else
        USER_RESPONSE=$(curl -s -X POST "https://${AUTH0_DOMAIN}/api/v2/users" \
            -H "Authorization: Bearer ${MGMT_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{
                "connection": "Username-Password-Authentication",
                "email": "'"${email}"'",
                "username": "'"${username}"'",
                "password": "'"${password}"'",
                "email_verified": true,
                "app_metadata": {
                    "tier": "'"${tier}"'",
                    "max_tokens": '"${max_tokens}"',
                    "allowed_models": '"${allowed_models}"',
                    "organization": "'"${org}"'",
                    "business_unit": "'"${bu}"'",
                    "team": "'"${team}"'",
                    "roles": '"${roles}"'
                }
            }')

        if echo "$USER_RESPONSE" | jq -e '.user_id' > /dev/null 2>&1; then
            echo -e "${GREEN}  OK User ${username} created${NC}"
        else
            echo -e "${RED}  FAIL Failed to create ${username}${NC}"
        fi
    fi
}

# Demo users
create_user "alice" "alice@example.com" "Alice123!" \
    "basic" 500 '["gpt-3.5-turbo"]' \
    "FinTech Corp" "Analytics" "Reporting" '["analyst"]'

create_user "bob" "bob@example.com" "Bob@123!" \
    "standard" 2000 '["gpt-3.5-turbo", "gpt-4"]' \
    "FinTech Corp" "Analytics" "Management" '["analyst", "manager"]'

create_user "carol" "carol@example.com" "Carol123!" \
    "premium" 4000 '["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"]' \
    "FinTech Corp" "Technology" "Infrastructure" '["analyst", "manager", "admin"]'

echo -e "${GREEN}OK Users created${NC}"

# ============================================================
# Step 6: Create Action for Custom Claims
# ============================================================
echo -e "${YELLOW}Step 6: Creating Action for custom claims...${NC}"

ACTION_NAME="Add MACAW Custom Claims"

EXISTING_ACTION=$(curl -s "https://${AUTH0_DOMAIN}/api/v2/actions/actions?actionName=${ACTION_NAME}" \
    -H "Authorization: Bearer ${MGMT_TOKEN}" | jq -r '.actions[0].id // empty')

ACTION_CODE='exports.onExecutePostLogin = async (event, api) => {
  const namespace = "https://macaw.local/";

  if (event.user.app_metadata) {
    const meta = event.user.app_metadata;

    if (meta.tier) api.accessToken.setCustomClaim(namespace + "tier", meta.tier);
    if (meta.max_tokens) api.accessToken.setCustomClaim(namespace + "max_tokens", meta.max_tokens);
    if (meta.allowed_models) api.accessToken.setCustomClaim(namespace + "allowed_models", meta.allowed_models);
    if (meta.organization) api.accessToken.setCustomClaim(namespace + "organization", meta.organization);
    if (meta.business_unit) api.accessToken.setCustomClaim(namespace + "business_unit", meta.business_unit);
    if (meta.team) api.accessToken.setCustomClaim(namespace + "team", meta.team);
    if (meta.roles) api.accessToken.setCustomClaim(namespace + "roles", meta.roles);
    api.accessToken.setCustomClaim(namespace + "app_metadata", meta);
  }

  if (event.user.username) {
    api.accessToken.setCustomClaim(namespace + "username", event.user.username);
  }
};'

if [ -n "$EXISTING_ACTION" ]; then
    echo -e "${BLUE}  Action already exists, updating...${NC}"
    curl -s -X PATCH "https://${AUTH0_DOMAIN}/api/v2/actions/actions/${EXISTING_ACTION}" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "code": "'"$(echo "$ACTION_CODE" | sed 's/"/\\"/g' | tr '\n' ' ')"'"
        }' > /dev/null
    ACTION_ID="$EXISTING_ACTION"
else
    ACTION_RESPONSE=$(curl -s -X POST "https://${AUTH0_DOMAIN}/api/v2/actions/actions" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "'"${ACTION_NAME}"'",
            "supported_triggers": [{"id": "post-login", "version": "v3"}],
            "code": "'"$(echo "$ACTION_CODE" | sed 's/"/\\"/g' | tr '\n' ' ')"'",
            "runtime": "node18"
        }')

    ACTION_ID=$(echo "$ACTION_RESPONSE" | jq -r '.id')
fi

if [ -n "$ACTION_ID" ] && [ "$ACTION_ID" != "null" ]; then
    curl -s -X POST "https://${AUTH0_DOMAIN}/api/v2/actions/actions/${ACTION_ID}/deploy" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" > /dev/null

    CURRENT_BINDINGS=$(curl -s "https://${AUTH0_DOMAIN}/api/v2/actions/triggers/post-login/bindings" \
        -H "Authorization: Bearer ${MGMT_TOKEN}" | jq -r '.bindings')

    IS_BOUND=$(echo "$CURRENT_BINDINGS" | jq -r '.[] | select(.action.id == "'"${ACTION_ID}"'") | .id')

    if [ -z "$IS_BOUND" ]; then
        curl -s -X PATCH "https://${AUTH0_DOMAIN}/api/v2/actions/triggers/post-login/bindings" \
            -H "Authorization: Bearer ${MGMT_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{
                "bindings": [{"ref": {"type": "action_id", "value": "'"${ACTION_ID}"'"}}]
            }' > /dev/null
    fi
    echo -e "${GREEN}OK Action deployed and bound${NC}"
fi

# ============================================================
# Summary
# ============================================================
echo ""
echo "=========================================="
echo -e "${GREEN}AUTH0 SETUP COMPLETE!${NC}"
echo "=========================================="
echo ""
echo "Auth0 Domain: ${AUTH0_DOMAIN}"
echo ""
echo "Application:"
echo "  Name: ${APP_NAME}"
echo "  Client ID: ${APP_CLIENT_ID}"
echo "  Client Secret: ${APP_CLIENT_SECRET}"
echo ""
echo "API:"
echo "  Name: ${API_NAME}"
echo "  Identifier: ${API_IDENTIFIER}"
echo ""
echo "Test Users:"
echo "  alice / Alice123! (Analyst)"
echo "  bob / Bob@123! (Manager)"
echo "  carol / Carol123! (Admin)"
echo ""
echo "Next step:"
echo "  Update ~/.macaw/config.json with:"
echo "    iam_provider: \"auth0\""
echo "    iam_config.domain: \"${AUTH0_DOMAIN}\""
echo "    iam_config.client_id: \"${APP_CLIENT_ID}\""
echo "    iam_config.client_secret: \"${APP_CLIENT_SECRET}\""
echo ""
echo "  Then run:"
echo "    export OPENAI_API_KEY=sk-your-key"
echo "    python3 app.py"
