"""The "Start a standup" button, for messages core sends.

The welcome DM and the day-2 nudge are core's, and core does not import
feature modules (see test_main_wiring's ratchet), so the button lives here.
The standup module's quickstart handles the press and re-exports both names.
"""

from __future__ import annotations

OPEN_ACTION = "quickstart:open"
BLOCK_ID = "quickstart"


def button_block() -> dict:
    """The quick start button. It has its own block_id, so a message can drop
    other action blocks (the email offer) and keep this one."""
    return {
        "type": "actions",
        "block_id": BLOCK_ID,
        "elements": [
            {
                "type": "button",
                "style": "primary",
                "action_id": OPEN_ACTION,
                "text": {"type": "plain_text", "text": "Start a standup"},
            }
        ],
    }
