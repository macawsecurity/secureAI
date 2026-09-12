# gmail per-tool policies

Structure: `app-claude_ai_Gmail.json` (policy id `app:claude_ai_Gmail`) is the app policy; it holds
the two attestation definitions (`gmail_send_approved`, `gmail_destructive_approved`) and scopes to
`mcp:claude_ai_Gmail/**`. Every per-tool policy `extends` it. Load the app policy first, then the 29
per-tool policies.

One control per tool: attested tools (send/reply/forward, trash/spam/sensitive-label/delete) use the
attestation; allow tools carry param guardrails in `constraints.parameters`. These guardrails are TEST
SPECIMENS: param constraints are the class secCC never applies to `mcp:` resources, so they are unverified
on this connector path. Only restrictions on SCALARS and on array COUNT (`max_items`) are used, because
MAPL does not iterate array elements (item validation is roadmap). The recipient count caps sit on the two
allow draft tools (create_draft, update_draft); the actual send tools are gated by the send attestation.

| Tool | Param restriction | Test (should be DENIED) |
|------|-------------------|-------------------------|
| create_draft, update_draft | `bcc` max_items 0 (no hidden recipients); `to`/`cc` max_items 25 | create_draft / update_draft with `bcc:["x@corp.com"]`, or 26+ in `to` |
| get_message | `messageFormat` allowed excludes RAW | get_message with `messageFormat:"RAW"` |
| create_label | `labelListVisibility` allowed [LABEL_SHOW, LABEL_SHOW_IF_UNREAD]; `messageListVisibility` allowed [SHOW] | create_label with `labelListVisibility:"LABEL_HIDE"` or `messageListVisibility:"HIDE"` |
| update_label | `labelListVisibility` allowed [LABEL_SHOW, LABEL_SHOW_IF_UNREAD]; `messageListVisibility` allowed [SHOW] | update_label with `labelListVisibility:"LABEL_HIDE"` or `messageListVisibility:"HIDE"` |

NOT expressible in static MAPL (removed, need a verifier that stamps a scalar the policy gates on):
recipient DOMAIN confinement (scan `to`/`cc`/`bcc` domains, stamp `has_external_recipient`) and
system-label denial (scan `labelIds`/`addLabelIds` for TRASH/SPAM/INBOX, stamp `adds_system_label`).
Both are array-element rules, and MAPL does not match array elements.

Caveats: `allowed_values`/`max_items` fire only when the param is PRESENT (an omitted `bcc`/`messageFormat`
defaults server-side and may slip through, per the guide this is unspecified); `allowed_values` on a
boolean is untested; Gmail ids (messageId/threadId/labelId/draftId) are opaque and `query` is free text,
so no constraint is placed on them; MAPL has no blob-size cap, so body and attachment content are not
limited.

19 allow, 10 attest, 29 total (plus the app policy, which also holds the param specimens).

| Tool | Decision | Reason |
|------|----------|--------|
| apply_sensitive_message_label | attest (gmail_destructive_approved) | a second TRASH/SPAM path, so approval gates it |
| apply_sensitive_thread_label | attest (gmail_destructive_approved) | TRASH/SPAM across a thread, so approval gates it |
| create_draft | allow | staging only, not delivered until a send verb runs |
| create_label | allow | organizational, no disclosure |
| delete_label | attest (gmail_destructive_approved) | permanent, so approval gates the deletion |
| forward | attest (gmail_send_approved) | forwards existing mail to external recipients, so approval gates the send |
| get_draft | allow | draftId is opaque |
| get_message | allow | messageId is opaque |
| get_thread | allow | threadId is opaque |
| label_message | allow | organizational label add |
| label_thread | allow | organizational label add |
| list_drafts | allow | Gmail list_drafts via connector, read-only lookup |
| list_labels | allow | Gmail list_labels via connector, read-only lookup |
| mark_message_spam | attest (gmail_destructive_approved) | suppresses and trains the filter, so approval gates it |
| mark_thread_spam | attest (gmail_destructive_approved) | suppresses a thread, so approval gates it |
| reply | attest (gmail_send_approved) | replyAll fans out and recipients are unconfinable, so approval gates the send |
| search_threads | allow | query is free text, ungateable by grammar |
| send_message | attest (gmail_send_approved) | recipients have no domain constraint and bcc is hidden, so approval gates the send |
| trash_message | attest (gmail_destructive_approved) | destructive, so approval gates the removal |
| trash_thread | attest (gmail_destructive_approved) | destructive across a thread, so approval gates the removal |
| unlabel_message | allow | organizational label remove |
| unlabel_thread | allow | organizational label remove |
| unmark_message_spam | allow | non-destructive reversal |
| unmark_thread_spam | allow | non-destructive reversal |
| untrash_message | allow | restore, non-destructive reversal |
| untrash_thread | allow | restore, non-destructive reversal |
| update_draft | allow | staging only, not delivered until a send verb runs |
| update_label | allow | organizational, no disclosure |
| update_message_labels | allow | atomic label add/remove |
