"""Which question a channel gets next. No I/O, so it is tested with plain lists.

A question is referred to as `b:<key>` (built-in) or `c:<id>` (the
workspace's own). The pool is what the channel may draw from today; the
history is what it posted, newest first.

Nothing about a cycle is stored. "Used in this cycle" is the run of posts,
newest first, whose questions are still in the pool, up to the first repeat
or until every pool question is covered. Editing the pool (hiding, archiving,
adding) therefore never needs a reset.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Sequence

from src.modules.watercooler import bank

SOURCES = ("builtin", "custom", "both")


def builtin_ref(key: str) -> str:
    return f"b:{key}"


def custom_ref(question_id: int) -> str:
    return f"c:{question_id}"


def pool(
    source: str,
    categories: Iterable[str],
    hidden: Iterable[str],
    custom_ids: Iterable[int],
) -> list[str]:
    """Every ref this channel may draw from, in a stable order."""
    refs: list[str] = []
    if source in ("builtin", "both"):
        hidden_keys = set(hidden)
        refs += [builtin_ref(q.key) for q in bank.in_categories(set(categories)) if q.key not in hidden_keys]
    if source in ("custom", "both"):
        refs += [custom_ref(i) for i in custom_ids]
    return refs


def used_this_cycle(history_newest_first: Sequence[str], pool_refs: Sequence[str]) -> set[str]:
    in_pool = set(pool_refs)
    used: list[str] = []
    seen: set[str] = set()
    for ref in history_newest_first:
        if ref not in in_pool:
            continue
        if ref in seen:
            break
        seen.add(ref)
        used.append(ref)
        if len(seen) == len(in_pool):
            break
    return set(used)


def pick(
    pool_refs: Sequence[str],
    history_newest_first: Sequence[str],
    choose: Callable[[list[str]], str] = random.choice,
) -> str | None:
    """The next ref, or None when the pool is empty.

    A fresh cycle starts once every question has been used; it never opens
    with the question that closed the last one.
    """
    if not pool_refs:
        return None
    used = used_this_cycle(history_newest_first, pool_refs)
    left = [ref for ref in pool_refs if ref not in used]
    if not left:
        last = next((ref for ref in history_newest_first if ref in set(pool_refs)), None)
        left = [ref for ref in pool_refs if ref != last] or list(pool_refs)
    return choose(left)
