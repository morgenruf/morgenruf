"""Guards against two modules colliding on Slack identifiers.

Standup's existing action ids stay bare on purpose: changing them would break
buttons in Slack messages already delivered to users. Everything added after
the module contract must carry a `<module>:` prefix, so two modules cannot
collide on the same action id.
"""

from __future__ import annotations

import ast
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
GRANDFATHERED = {"standup"}

# Two forms appear in this codebase: the Block Kit dict key
# ("action_id": "edit_standup") and the Bolt decorator kwarg
# (@app.action(action_id="...")). Match both.
ACTION_RE = re.compile(r'["\']?action_id["\']?\s*[=:]\s*["\']([^"\']+)["\']')


def bare_message_patterns(path: pathlib.Path) -> set[str]:
    """Plain-string @app.message patterns, read from the syntax tree.

    A regex cannot tell a decorator from prose: the first version of this
    matched the phrase @app.message("skip") inside a docstring explaining why
    a module avoids that very pattern, and reported it as a collision. Parsing
    means only real decorators count.

    Regex patterns (re.compile(...)) are excluded deliberately; they anchor,
    so they do not substring-match another module's command.
    """
    found: set[str] = set()
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not dec.args:
                continue
            fn = dec.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "message"):
                continue
            arg = dec.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.add(arg.value)
    return found


def module_dirs():
    return [p for p in (SRC / "modules").iterdir() if p.is_dir() and not p.name.startswith("_")]


def test_new_module_action_ids_are_namespaced():
    offenders = []
    for d in module_dirs():
        if d.name in GRANDFATHERED:
            continue
        for py in d.rglob("*.py"):
            for action_id in ACTION_RE.findall(py.read_text()):
                if not action_id.startswith(f"{d.name}:"):
                    offenders.append(f"{py}: {action_id}")
    assert offenders == [], "action ids missing a module prefix:\n" + "\n".join(offenders)


def test_the_guard_actually_finds_action_ids():
    """Fails loudly if the regex stops matching, rather than passing vacuously."""
    found = [a for py in SRC.rglob("*.py") for a in ACTION_RE.findall(py.read_text())]
    assert found, "the action_id regex matched nothing, so the guard is not testing anything"


def test_no_two_modules_share_a_bare_string_message_pattern():
    """Bolt's @app.message with a plain string does a SUBSTRING match.

    Standup used to register @app.message("skip"), so any other module whose
    command contained the word skip, including "connect skip", would also
    have fired standup's handler. Standup's keywords now go through the DM
    router as whole-message matches, and core's catch-all shadows every
    @app.message listener anyway, but a module adding one must still not
    collide. This guard makes a future violation fail loudly rather than
    silently stealing another module's messages.
    """
    by_module = {}
    for d in module_dirs():
        pats = set()
        for py in d.rglob("*.py"):
            pats.update(bare_message_patterns(py))
        by_module[d.name] = pats

    collisions = []
    for a, pats_a in by_module.items():
        for b, pats_b in by_module.items():
            if a >= b:
                continue
            for pa in pats_a:
                for pb in pats_b:
                    if pa in pb or pb in pa:
                        collisions.append(f"{a}:{pa!r} overlaps {b}:{pb!r}")
    assert collisions == [], "substring-matching message patterns collide:\n" + "\n".join(collisions)


def test_standups_reserved_words_are_recorded():
    """Pins the words Connect must avoid, so the constraint cannot be forgotten.

    Standup no longer has any @app.message listener (core's catch-all would
    shadow it). Its keywords are whole-message matches in claim_dm_command,
    so a Connect DM must not be exactly one of these.
    """
    from src.modules.standup.handlers import match_dm_command

    standup = SRC / "modules" / "standup"
    pats = set()
    for py in standup.rglob("*.py"):
        pats.update(bare_message_patterns(py))
    assert pats == set(), f"standup registers message listeners again: {sorted(pats)}"
    reserved = {w for w in ("help", "standup", "skip", "i'm away", "i'm back") if match_dm_command(w)}
    assert reserved == {"help", "standup", "skip", "i'm away", "i'm back"}
    assert match_dm_command("connect skip") is None
