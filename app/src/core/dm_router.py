"""Single catch-all message listener, shared by every module.

Bolt runs only the first listener that matches an event, and core registers
this one before any module. Every message event therefore ends here, and a
module's own @app.message listener never sees a DM. (Standup's keyword
listeners, `@app.message("standup")` and friends, are shadowed the same way;
changing that would change how standup answers are collected, so it is left
as it is.)

So modules expose hooks instead of listeners, and core offers each DM to them
in registry order. First claim wins. claim_dm_command is for explicit
commands such as `kudos @sam thanks` and is offered to every module before any
claim_dm, so a command still works while standup is waiting for an answer.
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

    Explicit commands (claim_dm_command) are offered first, then the
    conversational claim_dm. A module that raises is logged and skipped, so one
    broken module cannot stop the others from seeing their own messages.
    """
    modules = list(modules)
    for attr in ("claim_dm_command", "claim_dm"):
        for spec in modules:
            claim = getattr(spec, attr)
            if claim is None:
                continue
            try:
                claimed = claim(ctx)
            except Exception:
                logger.exception("module %s raised while claiming a DM", spec.name)
                continue
            if claimed:
                return spec.name
    if fallback is not None:
        fallback(ctx)
    return None
