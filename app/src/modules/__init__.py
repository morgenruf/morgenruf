"""Module registry.

Adding a module is one directory here plus one line in REGISTRY. Core never
imports a module by name, so removing a line is enough to remove a feature.

Order matters: the DM router offers each catch-all message to modules in this
order, so the module most likely to be mid-conversation with a user comes
first.
"""

from __future__ import annotations

from src.modules.standup import MODULE as STANDUP

REGISTRY = (STANDUP,)
