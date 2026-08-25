#!/bin/bash
#
# Complete Keycloak Setup - Creates realm, client, and users
#
# Prerequisites:
# 1. Docker installed
# 2. Run Keycloak: docker run -d -p 8080:8080 -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin123 quay.io/keycloak/keycloak:23.0 start-dev
#

set -e

# Configuration - customize these as needed
KEYCLOAK_PORT="${KEYCLOAK_PORT:-8080}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin123}"
REALM_NAME="fintech"
CLIENT_ID="financial-analyzer"
CLIENT_SECRET="change-me-in-production"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "Complete Keycloak Configuration"
echo "=========================================="

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo -e "${RED}jq is required but not installed.${NC}"
    echo "Install with: brew install jq (macOS) or apt install jq (Linux)"
    exit 1
fi

# Function to get/refresh admin token
get_admin_token() {
    local token=$(curl -s -X POST "http://localhost:${KEYCLOAK_PORT}/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=${KEYCLOAK_ADMIN}" \
        -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
        -d "grant_type=password" \
        -d "client_id=admin-cli" | jq -r '.access_token')

    if [ -z "$token" ] || [ "$token" = "null" ]; then
        echo -e "${RED}Failed to authenticate. Is Keycloak running?${NC}"
        exit 1
    fi

    echo "$token"
}

# Get admin token
echo -e "${YELLOW}Step 1: Authenticating as admin...${NC}"
ADMIN_TOKEN=$(get_admin_token)
echo -e "${GREEN}OK Admin authenticated${NC}"

# Create or update FinTech realm
echo -e "${YELLOW}Step 2: Creating/updating FinTech realm...${NC}"

# Delete existing realm completely (to start fresh)
echo "  Deleting existing realm (if it exists)..."
DELETE_RESULT=$(curl -s -w "%{http_code}" -X DELETE "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}")

DELETE_CODE="${DELETE_RESULT: -3}"
if [ "$DELETE_CODE" = "204" ]; then
    echo "  OK Existing realm deleted"
elif [ "$DELETE_CODE" = "404" ]; then
    echo "  OK No existing realm to delete"
fi

# Wait a moment for cleanup
sleep 2

# Create new realm
curl -s -X POST "http://localhost:${KEYCLOAK_PORT}/admin/realms" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
        "realm": "'${REALM_NAME}'",
        "enabled": true,
        "displayName": "FinTech Corporation",
        "loginWithEmailAllowed": true,
        "duplicateEmailsAllowed": false,
        "resetPasswordAllowed": true,
        "editUsernameAllowed": false,
        "bruteForceProtected": false
    }'

echo -e "${GREEN}OK FinTech realm created${NC}"

# Create the OAuth client
echo -e "${YELLOW}Step 3: Creating financial-analyzer client...${NC}"

curl -s -X POST "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/clients" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
        "clientId": "'${CLIENT_ID}'",
        "name": "Financial Analyzer Application",
        "enabled": true,
        "protocol": "openid-connect",
        "publicClient": false,
        "secret": "'${CLIENT_SECRET}'",
        "directAccessGrantsEnabled": true,
        "standardFlowEnabled": true,
        "implicitFlowEnabled": false,
        "serviceAccountsEnabled": false,
        "authorizationServicesEnabled": false,
        "redirectUris": ["http://localhost:3000/*", "http://localhost:8000/*"],
        "webOrigins": ["http://localhost:3000", "http://localhost:8000"],
        "attributes": {
            "use.refresh.tokens": "true"
        }
    }'

echo -e "${GREEN}OK Client created${NC}"

# Get the client UUID for mapper configuration
CLIENT_UUID=$(curl -s "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/clients?clientId=${CLIENT_ID}" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[0].id')

# Create custom attribute mappers
echo -e "${YELLOW}Step 4: Creating attribute mappers...${NC}"

create_mapper() {
    local name=$1
    local attribute=$2

    curl -s -X POST "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/clients/${CLIENT_UUID}/protocol-mappers/models" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "'$name'",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "consentRequired": false,
            "config": {
                "userinfo.token.claim": "true",
                "user.attribute": "'$attribute'",
                "id.token.claim": "true",
                "access.token.claim": "true",
                "claim.name": "'$attribute'",
                "jsonType.label": "String"
            }
        }' 2>/dev/null || echo "  (Mapper $name may already exist)"
}

create_mapper "organization-mapper" "organization"
create_mapper "business_unit-mapper" "business_unit"
create_mapper "team-mapper" "team"
create_mapper "clearance_level-mapper" "clearance_level"

echo -e "${GREEN}OK Mappers created${NC}"

# Create realm roles
echo -e "${YELLOW}Step 5: Creating realm roles...${NC}"
ADMIN_TOKEN=$(get_admin_token)

create_role() {
    local role=$1
    local desc=$2

    local existing_role=$(curl -s "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/roles/${role}" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}")

    if echo "$existing_role" | jq -e 'has("name")' > /dev/null 2>&1; then
        echo "  OK Role $role already exists"
        return 0
    fi

    local result=$(curl -s -w "%{http_code}" -X POST "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/roles" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"name": "'"$role"'", "description": "'"$desc"'"}')

    local http_code="${result: -3}"
    if [ "$http_code" = "201" ] || [ "$http_code" = "409" ]; then
        echo "  OK Role $role created/exists"
    else
        echo "  FAIL Failed to create role $role (HTTP $http_code)"
    fi
}

create_role "analyst" "Financial Analyst role"
create_role "manager" "Manager role"
create_role "admin" "Administrator role"

echo -e "${GREEN}OK Roles created${NC}"

# Create users
echo -e "${YELLOW}Step 6: Creating users...${NC}"
ADMIN_TOKEN=$(get_admin_token)

create_user_with_password() {
    local username=$1
    local email=$2
    local firstname=$3
    local lastname=$4
    local password=$5
    local org=$6
    local bu=$7
    local team=$8
    local clearance=$9

    local json_data=$(cat <<EOF
{"username": "$username", "email": "$email", "firstName": "$firstname", "lastName": "$lastname", "enabled": true, "emailVerified": true, "attributes": {"organization": ["$org"], "business_unit": ["$bu"], "team": ["$team"], "clearance_level": ["$clearance"]}}
EOF
)
    local create_result=$(curl -s -w "%{http_code}" -X POST "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/users" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$json_data")

    local create_code="${create_result: -3}"

    if [ "$create_code" = "201" ] || [ "$create_code" = "409" ]; then
        echo "  OK User $username created/exists"

        local user_id=$(curl -s "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/users?username=${username}" \
            -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[0].id')

        if [ ! -z "$user_id" ] && [ "$user_id" != "null" ]; then
            local pwd_result=$(curl -s -w "%{http_code}" -X PUT "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/users/${user_id}/reset-password" \
                -H "Authorization: Bearer ${ADMIN_TOKEN}" \
                -H "Content-Type: application/json" \
                -d '{"type": "password", "value": "'"$password"'", "temporary": false}')

            local pwd_code="${pwd_result: -3}"
            if [ "$pwd_code" = "204" ]; then
                echo "  OK Password set for $username"
            else
                echo "  FAIL Failed to set password for $username"
            fi
        fi
    else
        echo "  FAIL Failed to create user $username (HTTP $create_code)"
    fi
}

# Demo users with their organizational attributes
create_user_with_password "alice" "alice@example.com" "Alice" "Johnson" "Alice123!" "FinTech Corp" "Analytics" "Reporting" "standard"
create_user_with_password "bob" "bob@example.com" "Bob" "Smith" "Bob@123!" "FinTech Corp" "Analytics" "Management" "elevated"
create_user_with_password "carol" "carol@example.com" "Carol" "Davis" "Carol123!" "FinTech Corp" "Technology" "Infrastructure" "full"

echo -e "${GREEN}OK Users created${NC}"

# Assign roles to users
echo -e "${YELLOW}Step 7: Assigning roles to users...${NC}"
ADMIN_TOKEN=$(get_admin_token)

ALICE_ID=$(curl -s "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/users?username=alice" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[0].id')
BOB_ID=$(curl -s "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/users?username=bob" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[0].id')
CAROL_ID=$(curl -s "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/users?username=carol" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq -r '.[0].id')

get_role() {
    local role_name=$1
    local role_data=$(curl -s "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/roles/${role_name}" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}")

    if echo "$role_data" | jq -e 'has("name")' > /dev/null 2>&1; then
        echo "$role_data"
    else
        echo "null"
    fi
}

ANALYST_ROLE=$(get_role "analyst")
MANAGER_ROLE=$(get_role "manager")
ADMIN_ROLE=$(get_role "admin")

assign_role() {
    local user_id=$1
    local user_name=$2
    local role_data=$3
    local role_name=$4

    if [ ! -z "$user_id" ] && [ "$user_id" != "null" ] && [ "$role_data" != "null" ]; then
        curl -s -X POST "http://localhost:${KEYCLOAK_PORT}/admin/realms/${REALM_NAME}/users/${user_id}/role-mappings/realm" \
            -H "Authorization: Bearer ${ADMIN_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "[$role_data]" 2>/dev/null
        echo "  OK $user_name assigned $role_name role"
    fi
}

assign_role "$ALICE_ID" "Alice" "$ANALYST_ROLE" "analyst"
assign_role "$BOB_ID" "Bob" "$MANAGER_ROLE" "manager"
assign_role "$CAROL_ID" "Carol" "$ADMIN_ROLE" "admin"

echo -e "${GREEN}OK Roles assigned${NC}"

echo ""
echo "=========================================="
echo "KEYCLOAK SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "Keycloak Admin Console:"
echo "  http://localhost:8080/admin"
echo "  Username: admin"
echo "  Password: admin123"
echo ""
echo "FinTech Realm:"
echo "  Realm: fintech"
echo "  Client ID: financial-analyzer"
echo "  Client Secret: change-me-in-production"
echo ""
echo "Test Users:"
echo "  alice / Alice123! (Analyst)"
echo "  bob / Bob@123! (Manager)"
echo "  carol / Carol123! (Admin)"
echo ""
echo "Next step:"
echo "  export OPENAI_API_KEY=sk-your-key"
echo "  python3 app.py"
