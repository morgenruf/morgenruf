"""Single catch-all message.im listener, shared by every module.

Bolt fires every listener that matches an event. Standup's keyword listeners
(`@app.message("standup")` and friends) self-filter by pattern, so they do not
need arbitration. The catch-all is different: a second module registering its
own catch-all would process the same DM standup is already handling, and
standup would treat another module's command as a standup answer.

So modules expose claim_dm instead of registering their own catch-all, and
core offers each message to them in registry order. First claim wins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from src.core.modules import ModuleSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DMContext:
    team_id: str
    user_id: str
    channel_id: str
    text: str
    event: dict[str, Any]
    client: Any


def route_dm(
    modules: Iterable[ModuleSpec],
    ctx: DMContext,
    fallback: Optional[Callable[[DMContext], None]],
) -> Optional[str]:
    """Offer a DM to each module in order. Returns the claiming module's name.

    A module that raises is logged and skipped, so one broken module cannot
    stop the others from seeing their own messages.
    """
    for spec in modules:
        if spec.claim_dm is None:
            continue
        try:
            claimed = spec.claim_dm(ctx)
        except Exception:
            logger.exception("module %s raised while claiming a DM", spec.name)
            continue
        if claimed:
            return spec.name
    if fallback is not None:
        fallback(ctx)
    return None
