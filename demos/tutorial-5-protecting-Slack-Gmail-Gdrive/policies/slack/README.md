# Slack policies

`app-claude_ai_Slack.json` (`app:claude_ai_Slack`) holds the approvals; each tool policy extends it.
Load the app policy first, then the 27 tool policies.

| Approval | Asked when the agent |
|---|---|
| `slack_send_approved` | posts a message, saves a message draft or shares a file |
| `slack_schedule_approved` | schedules a message |
| `slack_create_approved` | creates a channel or DM, a canvas or a list |
| `slack_search_private_approved` | searches private channels and DMs, or lists the user's channels and DMs |

| Tool | Control |
|---|---|
| slack_read_channel, slack_read_thread, slack_read_user_profile, slack_read_canvas, slack_read_list, slack_read_file, slack_get_reactions, slack_search_public, slack_search_channels, slack_search_users, slack_search_emojis, slack_list_channel_members, slack_add_reaction, slack_get_file_upload_url, slack_update_canvas, slack_update_list, slack_add_list_record, slack_update_list_record | allowed |
| slack_send_message, slack_send_message_draft, slack_complete_file_upload | `slack_send_approved` |
| slack_schedule_message | `slack_schedule_approved` |
| slack_create_conversation, slack_create_canvas, slack_create_list | `slack_create_approved` |
| slack_search_public_and_private, slack_list_user_channels | `slack_search_private_approved` |
