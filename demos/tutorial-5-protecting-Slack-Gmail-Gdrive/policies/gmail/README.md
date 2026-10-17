# Gmail policies

`app-claude_ai_Gmail.json` (`app:claude_ai_Gmail`) holds the approvals; each tool policy extends it.
Load the app policy first, then the 29 tool policies.

| Approval | Asked when the agent |
|---|---|
| `gmail_send_approved` | sends, replies to or forwards mail |
| `gmail_destructive_approved` | trashes mail, marks it as spam, applies a sensitive label or deletes a label |

| Tool | Control |
|---|---|
| search_threads, get_message, get_thread, get_draft, list_drafts, list_labels, create_draft, update_draft, create_label, update_label, label_message, label_thread, unlabel_message, unlabel_thread, update_message_labels, untrash_message, untrash_thread, unmark_message_spam, unmark_thread_spam | allowed |
| send_message, reply, forward | `gmail_send_approved` |
| trash_message, trash_thread, mark_message_spam, mark_thread_spam, apply_sensitive_message_label, apply_sensitive_thread_label, delete_label | `gmail_destructive_approved` |
