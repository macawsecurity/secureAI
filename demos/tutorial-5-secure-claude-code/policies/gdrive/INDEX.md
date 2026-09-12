# gdrive per-tool policies

Structure: `app-claude_ai_Google_Drive.json` (policy id `app:claude_ai_Google_Drive`) is the app
policy; it holds the three attestation definitions (`drive_write_approved`, `drive_share_approved`,
`drive_destructive_approved`) and scopes to `mcp:claude_ai_Google_Drive/**`. Every per-tool policy
`extends` it. Load the app policy first, then the 11 per-tool policies.

One control per tool: attested tools (create/copy/update/share/trash) use the attestation; allow tools
carry param guardrails in the app policy's `constraints.parameters`. These guardrails are TEST SPECIMENS:
param constraints are the class secCC never applies to `mcp:` resources, so they are unverified on this
connector path. Run a denied call for each before trusting it. Specimens (allow tools only):

| Tool | Param restriction | Test (should be DENIED) |
|------|-------------------|-------------------------|
| search_files | `excludeContentSnippets` = true, `snippetVerbosity` = BRIEF, `pageSize` max 20 | search with `excludeContentSnippets:false` or `pageSize:100` |
| list_recent_files | `pageSize` max 20 | list with `pageSize:100` |
| read_file_content | `includeComments` = false | read with `includeComments:true` |

Caveats: `allowed_values` fires only when the param is PRESENT (an omitted `excludeContentSnippets` defaults
to false and may slip through); `allowed_values` on a boolean is untested per the guide. Drive has no array
params, so no `max_items`; MAPL has no blob-size cap, so upload content size is not limited. Role, recipient,
and mime confinement on the attested tools (share_file, create_file) is handled by their attestation, not by
params.

6 allow, 5 attest, 11 total (plus the app policy, which now also holds the param specimens).

| Tool | Decision | Reason |
|------|----------|--------|
| copy_file | attest (drive_write_approved) | duplicating into a chosen parentId is ungateable, so approval gates the write |
| create_file | attest (drive_write_approved) | parentId cannot be confined by grammar, so approval gates the write |
| download_file_content | allow | fileId is opaque |
| get_file_metadata | allow | fileId is opaque |
| get_file_permissions | allow | fileId is opaque |
| list_recent_files | allow | no folder param to confine |
| read_file_content | allow | fileId is opaque, ungateable by grammar |
| search_files | allow | query is free text and ids opaque, ungateable by grammar |
| share_file | attest (drive_share_approved) | emailAddress has no domain constraint, so approval gates the external grant |
| trash_file | attest (drive_destructive_approved) | destructive and keyed off one opaque id, so approval gates the removal |
| update_file | attest (drive_write_approved) | parentId here is a hidden move, so approval gates the edit or move |
