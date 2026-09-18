"""The scopes this app asks for, in one place.

The manifest and the install URL disagreed twice: once when coffee chats
shipped and the three mpim scopes were never added to the install URL, so the
feature installed and stayed dark, and again when reactions:write and
channels:history sat in the manifest without a single caller.

Both now come from here, and a test fails if the manifest drifts. Each scope
carries the reason it exists, because Slack's reviewers ask for exactly that
and because a scope nobody can justify is a scope to delete.
"""

from __future__ import annotations

# scope: why the app cannot work without it
BOT_SCOPES: dict[str, str] = {
    "commands": "The slash commands the app registers.",
    "app_mentions:read": "Delivering the app_mention event, which is how the bot answers when somebody @-mentions it in a channel.",
    "chat:write": "Posting the standup summary, coffee chat introductions and kudos.",
    "channels:read": "Reading who is in a public channel, to build the standup participant "
    "list and the coffee chat pool.",
    "groups:read": "The same, for private channels the bot has been invited to.",
    "im:write": "Opening a direct message to ask each person their standup questions.",
    "im:history": "Reading replies to the app's own direct messages, which is how answers arrive.",
    "im:read": "Listing the app's own direct message conversations.",
    "mpim:write": "Opening the group direct message a coffee chat introduction happens in.",
    "mpim:history": "Reading that group message, so a pair who are already talking is not nudged.",
    "users:read": "Names and timezones, so nobody is asked at midnight.",
    "users:read.email": "The address a per-standup digest email is sent to.",
    "users.profile:read": "Working hours, for suggesting a time both people in a pairing can make.",
    "emoji:read": "Checking a workspace's custom emoji, so kudos can use your own token.",
    "team:read": "The workspace name, shown in the dashboard and the digest.",
}

# Slack scrutinises history scopes hardest, so the two here are worth stating
# plainly: both are the app's own conversations. There is no scope for reading
# a channel the app was not invited to, and none for channel history at all.
SCOPE_STRING = ",".join(BOT_SCOPES)


def missing_from(granted) -> list[str]:
    """Scopes the app needs that a workspace has not granted."""
    have = set(granted or ())
    return [s for s in BOT_SCOPES if s not in have]
