# Google Drive policies

`app-claude_ai_Google_Drive.json` (`app:claude_ai_Google_Drive`) holds the approvals; each tool policy
extends it. Load the app policy first, then the 11 tool policies.

| Approval | Asked when the agent |
|---|---|
| `drive_write_approved` | creates, copies, updates or moves a file |
| `drive_share_approved` | shares a file |
| `drive_destructive_approved` | trashes a file |

| Tool | Control |
|---|---|
| search_files, list_recent_files, read_file_content, download_file_content, get_file_metadata, get_file_permissions | allowed |
| create_file, copy_file, update_file | `drive_write_approved` |
| share_file | `drive_share_approved` |
| trash_file | `drive_destructive_approved` |
