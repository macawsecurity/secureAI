# Tutorial 5: Secure Claude Code (secCC)

secCC puts a MACAW policy checkpoint on every tool Claude Code runs, including your connected MCP servers, so reads run free while writes, deletes, and network calls need approval.

## Why This Matters

| Problem | How secCC handles it |
|---------|----------------------|
| A connected MCP server (Gmail, Drive, Slack) lets the agent send mail, share files, or trash data with nothing between intent and action. | secCC intercepts every  tool call in Claude Code and evaluates it against a MAPL policy before it runs. |
| A blanket allow or deny on a connector is too coarse; reading a file is not the same as deleting one. | Policies gate by action type: reads run free, while create, write, delete, and share require an attestation (a logged approval). |
| Shell and network access are ungoverned; a stray `curl` can exfiltrate data. | secCC gates bash and network out of the box; an outbound call pauses for a network approval. |
| No record of what the agent did, or why it was allowed. | Every decision and tool call is written to a signed audit trail in the Console. |

## Overview

secCC installs into Claude Code as hooks. Once the connector policies are loaded, the Drive, Gmail, and Slack MCP tools are gated by what the action does:

| Action | Example tools | Control |
|--------|---------------|---------|
| Read | search_files, read_file_content, get_message, slack_read_channel | allowed |
| Write / Create | create_file, update_file, create_label, slack_create_canvas | attestation |
| Share / Send | share_file, send_message, forward | attestation |
| Delete / Destructive | trash_file, trash_message, delete_label | attestation |

## Directory Structure

```
tutorial-5-secure-claude-code/
├── policies/
│   ├── gdrive/   # app:claude_ai_Google_Drive + 11 per-tool policies
│   ├── gmail/    # app:claude_ai_Gmail + 29 per-tool policies
│   └── slack/    # app:claude_ai_Slack + 27 per-tool policies
└── README.md
```

Each connector has one app policy that holds the attestation definitions, and one policy per tool that `extends` it and declares which action needs approval. Reads carry no attestation, so they run free.

## Quick Start

### 1. Prerequisites

- Claude Code
- A MACAW Console account (secCC.ai)
- One or more MCP connectors added to Claude Code (Gmail, Drive, Slack)

### 2. Install secCC

Follow the onboarding at `https://seccc.ai` to install Secure Claude Code. It wires MACAW into Claude Code as PreToolUse hooks, so every tool call is checked against policy before it runs. Your MCP servers are untouched.

### 3. Confirm secCC is enforcing

Ask Claude Code to make an outbound request:

```
curl https://example.com
```

secCC intercepts the bash call and pauses for a network approval before it runs. Approve it and the request proceeds. That confirms the hooks are live.

### 4. Load the connector policies

Import the policies under `policies/` into your MACAW workspace (Console: Policies → Add Policy → Code Editor → paste JSON → Validate → Save). For each connector, load the app policy FIRST, then its per-tool policies:

| # | App policy | Then |
|---|-----------|------|
| 1 | `policies/gdrive/app-claude_ai_Google_Drive.json` | the 11 files in `gdrive/` |
| 2 | `policies/gmail/app-claude_ai_Gmail.json` | the 29 files in `gmail/` |
| 3 | `policies/slack/app-claude_ai_Slack.json` | the 27 files in `slack/` |

### 5. Test the connector controls

Ask Claude Code to use the connectors and watch the difference by action:

- Read (allowed): "search my Drive for the Q3 report" runs with no prompt.
- Write (attested): "create a file named notes.txt in my Drive" pauses for `drive_write_approved`.
- Delete (attested): "trash that file" pauses for `drive_destructive_approved`.
- Send (attested): "email the report to a teammate" pauses for `gmail_send_approved`.

Approve or deny each from the Console.

### 6. Verify in the Console

Open the Console audit log. Every tool call, its policy decision, and each attestation appears as a signed event.

## What the Demo Shows

1. **One checkpoint for everything**: secCC gates every Claude Code tool call, bash and MCP alike, with no change to the tools.
2. **Action-type policy**: reads run free; create, write, delete, and share require a logged approval.
3. **Signed audit**: every decision and tool call is recorded.

### Expected Output

| Action | Tool | Result | What secCC said |
|--------|------|--------|-----------------|
| Read | search_files | 🟢 ALLOWED | runs, no prompt |
| Write | create_file | 🟡 ATTESTATION | `Missing attestation: drive_write_approved` |
| Delete | trash_file | 🟡 ATTESTATION | `Missing attestation: drive_destructive_approved` |
| Send | send_message | 🟡 ATTESTATION | `Missing attestation: gmail_send_approved` |
