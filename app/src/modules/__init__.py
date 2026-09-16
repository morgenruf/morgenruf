"""Module registry.

Adding a module is one directory here plus one line in REGISTRY. Core never
imports a module by name, so removing a line is enough to remove a feature.

Order matters: the DM router offers each catch-all message to modules in this
order, so the module most likely to be mid-conversation with a user comes
first.
"""

from __future__ import annotations

from src.modules.connect import MODULE as CONNECT
from src.modules.google_chat import MODULE as GOOGLE_CHAT
from src.modules.insights import MODULE as INSIGHTS
from src.modules.kudos import MODULE as KUDOS
from src.modules.mcp import MODULE as MCP
from src.modules.standup import MODULE as STANDUP

REGISTRY = (STANDUP, KUDOS, CONNECT, INSIGHTS, MCP, GOOGLE_CHAT)
