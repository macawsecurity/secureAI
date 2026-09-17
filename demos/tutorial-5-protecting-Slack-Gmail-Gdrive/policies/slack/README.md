# Anthropic Slack connector -- per-tool MAPL policies

Resource namespace: `mcp:claude_ai_Slack/<tool>`. One policy file per tool, version 2.5.0, scope `mcp`.
27 real tools loaded from the live connector schema.

Structure: `app-claude_ai_Slack.json` (policy id `app:claude_ai_Slack`) is the app policy; it holds the four
attestation DEFINITIONS (`slack_send_approved`, `slack_schedule_approved`, `slack_create_approved`,
`slack_search_private_approved`) plus the tool-level param specimens, and scopes to `mcp:claude_ai_Slack/**`.
Every per-tool policy carries `"extends": "app:claude_ai_Slack"` and references the attestations by name in its
top-level `attestations` array. Load the app policy FIRST, then the 27 per-tool policies.

One control per tool: attested tools use the attestation; allow tools carry param guardrails in the app policy's
`constraints.parameters` / `constraints.denied_parameters`. These guardrails are TEST SPECIMENS: param constraints
are the class secCC never applies to `mcp:` resources, so they are unverified and likely inert on this connector
path. Run a denied call for each before trusting it. Specimens (allow tools only, every param confirmed against the
live scraped schema):

| Tool | Param restriction | Test (should be DENIED) |
|------|-------------------|-------------------------|
| slack_search_channels | `channel_types` allowed_values [public_channel] | search with `channel_types:"public_channel,private_channel"` |
| slack_read_thread | `limit` max 100 (tool allows up to 1000) | read with `limit:500` |
| slack_list_channel_members | `response_format` denies `ids_only` | list with `response_format:"ids_only"` |

Note: the private-search tools (`slack_search_public_and_private`, `slack_list_user_channels`) are gated by the
`slack_search_private_approved` attestation, NOT by a `channel_types` restriction; forcing them public would negate
the attestation, so no param is placed on them.

Caveats: `allowed_values` fires only when the param is PRESENT (an omitted `channel_types` falls to the tool default
and slips through); `channel_types` is a comma-separated free string, so `allowed_values [public_channel]` matches
only the exact literal and rejects any multi-type string rather than parsing it. Slack ids (channel_id, user_id,
canvas_id, list_id, file_id) are opaque and message/query are free text, so none are restrictable; MAPL has no
blob-size cap, so message length is not limited.

Design line: Slack ids (channel_id, user_id, canvas_id, list_id, file_id) are OPAQUE, and message/query are FREE
TEXT. Neither is confinable with `allowed_values` (literal only), `pattern`, or a `denied_parameters` glob in a
reusable policy, so no policy pretends to. Risk is gated at the ACTION level with an attestation, or left to the
caller allow-list. True content confinement (e.g. secret scanning, private-scope limits) needs a custom verifier.

## Attestations (defined in app-claude_ai_Slack.json under constraints.attestations)
- `slack_send_approved` -- approve posting a message or sharing a file to a channel or DM.
- `slack_schedule_approved` -- approve scheduling a message that fires after the session ends.
- `slack_create_approved` -- approve creating a persistent object (channel, DM, canvas, list).
- `slack_search_private_approved` -- approve sweeping private channels/DMs or enumerating the user's DMs.

## Decisions

| Tool | Decision | Reason |
|------|----------|--------|
| slack_send_message | attest (send) | Posts to a channel/DM; opaque id ungateable, so gate the send. |
| slack_send_message_draft | attest (send) | Drafts content for a target; grouped with send. |
| slack_complete_file_upload | attest (send) | Irreversibly shares a file to a channel; disclosure. |
| slack_schedule_message | attest (schedule) | Fires after the session ends, not editable via API. |
| slack_search_public_and_private | attest (private search) | Defaults to sweeping private channels + DMs. |
| slack_list_user_channels | attest (private search) | Enumerates the user's private channels and DMs. |
| slack_create_conversation | attest (create) | Creates a persistent channel/DM. |
| slack_create_canvas | attest (create) | Creates a persistent canvas. |
| slack_create_list | attest (create) | Creates a persistent list. |
| slack_read_channel | allow | Read-only; opaque channel_id unconfinable. |
| slack_read_thread | allow | Read-only; opaque ids unconfinable. |
| slack_read_user_profile | allow | Read-only profile lookup. |
| slack_read_canvas | allow | Read-only; opaque canvas_id. |
| slack_read_list | allow | Read-only; opaque ids. |
| slack_read_file | allow | Read-only; opaque file_id. |
| slack_get_reactions | allow | Read-only reaction lookup. |
| slack_search_public | allow | Public-only search, needs no consent; free-text query. |
| slack_search_channels | allow | Read-only directory search; free-text query. |
| slack_search_users | allow | Read-only directory search; free-text query. |
| slack_search_emojis | allow | Read-only emoji lookup; free-text query. |
| slack_list_channel_members | allow | Read-only member listing; opaque channel_id. |
| slack_add_reaction | allow | Trivial write (emoji), no disclosure or persistence. |
| slack_get_file_upload_url | allow | Only mints an upload URL; the disclosing step (complete_file_upload) is gated. |
| slack_update_canvas | allow | Edits an already-referenced canvas; opaque id ungateable, content confinement needs a verifier. |
| slack_update_list | allow | Edits an already-referenced list schema; opaque id ungateable. |
| slack_add_list_record | allow | Adds a row to an already-referenced list; opaque id ungateable. |
| slack_update_list_record | allow | Edits a row in an already-referenced list; opaque id ungateable. |

18 allow, 9 attest, 0 deny. No `denied_parameters`/`allowed_values`/`pattern`/`min`/`max` used anywhere: no Slack
param is a filesystem path, a bounded number, or a confinable enum, so every such constraint would be inert or a
leaky blocklist.
