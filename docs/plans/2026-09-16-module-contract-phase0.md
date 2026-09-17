# Module Contract (Phase 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `app/src` into a module contract so that adding, removing, enabling or disabling a feature module is one directory plus one registry line, without changing any standup behavior.

**Architecture:** `src/core/` owns infrastructure (database, Slack client, scheduler, OAuth, dashboard shell, DM routing) and knows nothing about any specific feature. `src/modules/` holds one package per feature, each exposing a single `ModuleSpec`. Core discovers modules through an explicit registry tuple, resolves per-workspace activation, and drives registration of Slack listeners, HTTP routes, scheduled jobs and migrations.

**Tech Stack:** Python 3.14 (image), Flask, slack-bolt, APScheduler, psycopg2, PostgreSQL, pytest, ruff, Helm, Docker.

**Spec:** `docs/design/2026-09-16-connect-pairing-design.md`

## Global Constraints

- Python 3.14-slim in the runtime image. CI lint runs on Python 3.12, so no syntax newer than 3.12.
- ruff: `line-length = 120`, `select = ["E", "F", "W", "I"]`, `ignore = ["E501"]`. `ruff.toml` has per-file-ignores keyed on `app/src/main.py` and `app/src/db.py`; those keys must be updated whenever those files move.
- Never use an em dash or a literal double hyphen in prose, comments, commit messages or docs. Use commas, periods or parentheses.
- Never add `Co-Authored-By` trailers or AI attribution footers to commits.
- Baseline is 530 passing tests. Every commit must leave the full suite green. Run `pytest tests/ -q` from `app/`.
- Migrations are additive only. No column drops, no type changes, no backfills. Rollback must remain a plain image revert.
- `app/src/migrate.py` must stay executable as a script path, because `helm/morgenruf/templates/deployment.yaml:28` hardcodes `python src/migrate.py` and self-hosted users may pin an older chart.
- Standup behavior must not change in any task in this plan. File moves are verified mechanical by the AST checker built in Task 3.
- `schema_migrations.filename` stays a bare basename. The 28 rows already applied in production must never re-run.

## Verification Baseline

Before Task 1, record the baseline so later tasks can prove nothing regressed:

```bash
cd app
python -m pytest tests/ -q | tail -1     # expect: 530 passed
```

---

# Release R1: Test harness and dead code

No user-visible change. No file moves. This release makes the later moves safe.

### Task 1: Shared pytest configuration and module-stub isolation

Every one of the 28 test files currently does its own `sys.path.insert`. One of them documents the consequence: "Earlier test modules leave MagicMock stubs in sys.modules". When a test replaces a real module with a `MagicMock` and does not restore it, later tests import the stub instead of the real module. That is tolerable today and becomes a debugging nightmare once two feature packages share a test run.

**Files:**
- Create: `app/conftest.py`
- Create: `app/tests/test_conftest_isolation.py`
- Modify: all 28 files in `app/tests/` (remove the per-file `sys.path.insert` lines)

**Interfaces:**
- Consumes: nothing
- Produces: an autouse fixture named `_restore_stubbed_modules`, applied to every test in the suite. Test files may assume `app/src` is importable without doing their own path setup.

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_conftest_isolation.py`:

```python
"""Proves the autouse fixture undoes sys.modules stubbing between tests.

These two tests must run in this order. The first stubs a real module the way
several existing test files do; the second asserts the stub did not survive.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


def test_a_stubs_a_real_module():
    import url_guard  # noqa: F401  real module, imported so it is in sys.modules

    sys.modules["url_guard"] = MagicMock()
    assert isinstance(sys.modules["url_guard"], MagicMock)


def test_b_sees_the_real_module_again():
    assert not isinstance(sys.modules.get("url_guard"), MagicMock)
    import url_guard

    assert callable(url_guard.is_safe_url) or hasattr(url_guard, "__file__")
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_conftest_isolation.py -v
```

Expected: `test_b_sees_the_real_module_again` FAILS, because nothing restores the stub. It may also error on import if `app/src` is not on the path, which is the second half of what this task fixes.

- [ ] **Step 3: Write `app/conftest.py`**

```python
"""Shared pytest setup.

Puts app/src on sys.path once, so individual test modules do not have to, and
undoes sys.modules stubbing after each test so a MagicMock installed by one
test cannot be imported by the next.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

_SRC = os.path.join(os.path.dirname(__file__), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


@pytest.fixture(autouse=True)
def _restore_stubbed_modules():
    """Restore any sys.modules entry a test replaced with a MagicMock."""
    before = dict(sys.modules)
    yield
    for name, module in list(sys.modules.items()):
        if not isinstance(module, MagicMock):
            continue
        original = before.get(name)
        if original is not None and not isinstance(original, MagicMock):
            sys.modules[name] = original
        elif name not in before:
            del sys.modules[name]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd app && python -m pytest tests/test_conftest_isolation.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run the full suite before touching the other test files**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 532 passed (530 baseline plus the 2 new tests). If any previously passing test now fails, the fixture is restoring something a test deliberately relied on leaking. Fix the individual test to set up its own stub rather than weakening the fixture.

- [ ] **Step 6: Remove the per-file path setup**

```bash
cd app
grep -rln 'sys.path.insert' tests/
python - <<'PY'
import pathlib, re
removed = 0
for p in pathlib.Path("tests").glob("*.py"):
    text = p.read_text()
    new = re.sub(r'^sys\.path\.insert\([^\n]*\)\n', '', text, flags=re.M)
    if new != text:
        p.write_text(new)
        removed += 1
print("files changed:", removed)
PY
ruff check --fix tests/    # drops the now-unused os and sys imports
ruff format --check tests/ || true
```

- [ ] **Step 7: Run the full suite again**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 532 passed. If a test now fails on an import error, that file needed something other than `src` on the path. Add it to `conftest.py`, not back into the test file.

- [ ] **Step 8: Commit**

```bash
git add app/conftest.py app/tests/
git commit -m "test: add shared conftest with sys.modules isolation

Centralises the sys.path setup that all 28 test files were duplicating and
adds an autouse fixture that restores any module a test replaced with a
MagicMock. Test isolation was already leaking between modules, which would
get materially worse once two feature packages share a test run."
```

### Task 2: Delete dead code

`src/app.py` has no importer and cannot work anyway: it uses `from .handlers import register_handlers`, a relative import that cannot resolve under the current flat `sys.path` scheme. `adapters/slack_adapter.py` defines `SlackAdapter`, which nothing imports; standup calls `WebClient` directly.

**Files:**
- Delete: `app/src/app.py`
- Delete: `app/src/adapters/slack_adapter.py`

**Interfaces:**
- Consumes: nothing
- Produces: nothing. `adapters/base.py` and `adapters/google_chat.py` stay, because `google_chat_handler.py:29` imports `GoogleChatAdapter`.

- [ ] **Step 1: Verify there are no importers**

```bash
cd app
grep -rn "from app import\|import app$\|src\.app" src tests || echo "no importers of app.py"
grep -rn "slack_adapter\|SlackAdapter" src tests || echo "no importers of slack_adapter"
```

Expected: both lines print the "no importers" message. If either prints a match, stop and re-scope this task.

- [ ] **Step 2: Delete the two files**

```bash
cd app && git rm src/app.py src/adapters/slack_adapter.py
```

- [ ] **Step 3: Run the full suite**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 532 passed.

- [ ] **Step 4: Confirm the image still builds**

```bash
cd app && docker build -q -t morgenruf-deadcode-check . && echo BUILD_OK
```

Expected: `BUILD_OK`.

- [ ] **Step 5: Commit**

```bash
git add -A app/src
git commit -m "chore: remove dead app.py and slack_adapter

Neither has an importer. app.py additionally uses a relative import that
cannot resolve under the flat sys.path scheme, so it has never been runnable.
adapters/base.py and adapters/google_chat.py stay, since google_chat_handler
imports GoogleChatAdapter."
```

### Task 3: AST-equivalence checker

`handlers.py` is 29% covered and `blocks.py` is 40%. The test suite alone cannot prove that moving those files changed nothing. This tool makes the proof structural: parse the module before and after, strip import statements, compare the trees.

**Files:**
- Create: `app/tools/__init__.py` (empty)
- Create: `app/tools/check_mechanical_move.py`
- Create: `app/tests/test_check_mechanical_move.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `modules_equivalent(old_source: str, new_source: str) -> bool`
  - `changed_functions(old_source: str, new_source: str, names: list[str]) -> list[str]`
  - CLI: `python tools/check_mechanical_move.py <git_rev> <old_path> <new_path>`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_check_mechanical_move.py`:

```python
"""Tests for the mechanical-move checker used to gate the package split."""

from __future__ import annotations

from tools.check_mechanical_move import changed_functions, modules_equivalent

OLD = """
import os
from db import get_conn

def add(a, b):
    return a + b

def scale(x):
    return x * 2
"""

MOVED_IMPORTS_ONLY = """
import os
from src.core.db import get_conn

def add(a, b):
    return a + b

def scale(x):
    return x * 2
"""

LOGIC_CHANGED = """
import os
from src.core.db import get_conn

def add(a, b):
    return a + b + 1

def scale(x):
    return x * 2
"""


def test_import_only_rewrite_is_equivalent():
    assert modules_equivalent(OLD, MOVED_IMPORTS_ONLY) is True


def test_logic_change_is_not_equivalent():
    assert modules_equivalent(OLD, LOGIC_CHANGED) is False


def test_changed_functions_reports_only_the_edited_one():
    assert changed_functions(OLD, LOGIC_CHANGED, ["add", "scale"]) == ["add"]


def test_changed_functions_is_empty_for_an_import_only_rewrite():
    assert changed_functions(OLD, MOVED_IMPORTS_ONLY, ["add", "scale"]) == []


def test_missing_function_counts_as_changed():
    assert changed_functions(OLD, "def add(a, b):\\n    return a + b\\n", ["scale"]) == ["scale"]
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_check_mechanical_move.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools'`.

- [ ] **Step 3: Write the implementation**

Create `app/tools/__init__.py` as an empty file, then `app/tools/check_mechanical_move.py`:

```python
"""Prove a file move changed nothing except import lines.

Parses both versions, removes every Import and ImportFrom node at any nesting
level, and compares the resulting syntax trees. Used to gate the package split,
where the largest moved files have coverage too low to rely on tests alone.

CLI:
    python tools/check_mechanical_move.py <git_rev> <old_path> <new_path>

Exit code 0 means equivalent, 1 means a difference was found.
"""

from __future__ import annotations

import ast
import subprocess
import sys


class _StripImports(ast.NodeTransformer):
    def visit_Import(self, node: ast.Import):  # noqa: N802
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
        return None


def _normalise_module(source: str) -> str:
    tree = _StripImports().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False)


def modules_equivalent(old_source: str, new_source: str) -> bool:
    """True when the two sources differ only in import statements."""
    return _normalise_module(old_source) == _normalise_module(new_source)


def _function_dump(source: str, name: str) -> str | None:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            stripped = _StripImports().visit(node)
            ast.fix_missing_locations(stripped)
            return ast.dump(stripped, include_attributes=False)
    return None


def changed_functions(old_source: str, new_source: str, names: list[str]) -> list[str]:
    """Names whose bodies differ between the two sources.

    A function missing from either side counts as changed. Used when functions
    are extracted from a large module into a new one, where a whole-file
    comparison does not apply.
    """
    return [n for n in names if _function_dump(old_source, n) != _function_dump(new_source, n)]


def _read_git(rev: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    rev, old_path, new_path = argv[1], argv[2], argv[3]
    old_source = _read_git(rev, old_path)
    with open(new_path) as fh:
        new_source = fh.read()
    if modules_equivalent(old_source, new_source):
        print(f"OK mechanical: {old_path} -> {new_path}")
        return 0
    print(f"DIFFERS beyond imports: {old_path} -> {new_path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_check_mechanical_move.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Smoke-test the CLI against a file that has not moved**

```bash
cd app && python tools/check_mechanical_move.py HEAD app/src/url_guard.py src/url_guard.py
```

Expected: `OK mechanical: app/src/url_guard.py -> src/url_guard.py`.

- [ ] **Step 6: Run the full suite**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 537 passed.

- [ ] **Step 7: Commit**

```bash
git add app/tools app/tests/test_check_mechanical_move.py
git commit -m "test: add AST equivalence checker for the package split

handlers.py sits at 29% coverage and blocks.py at 40%, so the test suite alone
cannot prove a file move changed nothing. This parses both versions, strips
import nodes, and compares the trees, turning the guarantee into a structural
one. changed_functions covers the extraction case, where a whole-file
comparison does not apply."
```

**R1 ships here.** Zero user-visible change. Deploy per the checklist in spec section 9.7, outside standup and report windows.

---

# Release R2: Package split

Mechanical file moves only. Every task in this release is gated by the AST checker from Task 3.

### Task 4: Create the package skeleton and move core infrastructure

**Files:**
- Create: `app/src/__init__.py`, `app/src/core/__init__.py`, `app/src/modules/__init__.py`
- Move: `db.py`, `scheduler.py`, `oauth.py`, `installation_store.py`, `session_store.py`, `state.py`, `config.py`, `url_guard.py`, `slack_users.py`, `dashboard.py` into `app/src/core/`
- Move: `migrate.py` to `app/src/core/migrations_runner.py`
- Move: `app/migrations/*.sql` to `app/src/core/migrations/`
- Modify: every import site in `app/src` and `app/tests`
- Modify: `ruff.toml` per-file-ignores keys

**Interfaces:**
- Consumes: `modules_equivalent` from Task 3
- Produces: modules importable as `src.core.db`, `src.core.scheduler`, `src.core.oauth`, `src.core.dashboard`, `src.core.migrations_runner`. `src.core.migrations_runner.run_migrations()` keeps its existing signature and behavior.

- [ ] **Step 1: Record the pre-move sources for verification**

```bash
cd /path/to/morgenruf && git rev-parse HEAD > /tmp/premove_rev.txt && cat /tmp/premove_rev.txt
```

- [ ] **Step 2: Create the package files and move core modules**

```bash
cd app/src
touch __init__.py
mkdir -p core modules
touch core/__init__.py modules/__init__.py
git mv db.py scheduler.py oauth.py installation_store.py session_store.py \
       state.py config.py url_guard.py slack_users.py dashboard.py core/
git mv migrate.py core/migrations_runner.py
mkdir -p core/migrations
cd .. && git mv migrations/*.sql src/core/migrations/ && rmdir migrations
```

- [ ] **Step 3: Rewrite import sites**

```bash
cd app
python - <<'PY'
import pathlib, re

CORE = ["db", "scheduler", "oauth", "installation_store", "session_store",
        "state", "config", "url_guard", "slack_users", "dashboard"]

pattern_from = re.compile(r'^(\s*)from (' + "|".join(CORE) + r') import ', re.M)
pattern_import = re.compile(r'^(\s*)import (' + "|".join(CORE) + r')\b(?! as)', re.M)
pattern_import_as = re.compile(r'^(\s*)import (' + "|".join(CORE) + r') as ', re.M)

for p in list(pathlib.Path("src").rglob("*.py")) + list(pathlib.Path("tests").rglob("*.py")):
    t = p.read_text()
    o = t
    t = pattern_from.sub(lambda m: f"{m.group(1)}from src.core.{m.group(2)} import ", t)
    t = pattern_import_as.sub(lambda m: f"{m.group(1)}import src.core.{m.group(2)} as ", t)
    t = pattern_import.sub(lambda m: f"{m.group(1)}import src.core.{m.group(2)} as {m.group(2)}", t)
    if t != o:
        p.write_text(t)
        print("rewrote", p)
PY
ruff check --fix src tests
```

Note: the third substitution turns `import db` into `import src.core.db as db`, which preserves every `db.foo(...)` call site unchanged. That is deliberate: it keeps the move mechanical, so the AST checker still passes.

- [ ] **Step 4: Update `ruff.toml`**

Change the per-file-ignores keys so they still match:

```toml
[lint.per-file-ignores]
"app/src/main.py" = ["E402"]
"app/src/core/db.py" = ["E402"]
```

- [ ] **Step 5: Point the migrations runner at its new default directory**

In `app/src/core/migrations_runner.py`, change `get_migrations_dir`:

```python
def get_migrations_dir():
    """Default to the core migrations directory that now ships inside the package.

    MIGRATIONS_DIR still wins when set, because self-hosted deployments may
    point it somewhere else.
    """
    default = os.path.join(os.path.dirname(__file__), "migrations")
    return os.environ.get("MIGRATIONS_DIR", default)
```

- [ ] **Step 6: Verify every moved file is mechanically identical**

```bash
cd app
REV=$(cat /tmp/premove_rev.txt)
FAIL=0
for f in db scheduler oauth installation_store session_store state config url_guard slack_users dashboard; do
  python tools/check_mechanical_move.py "$REV" "app/src/$f.py" "src/core/$f.py" || FAIL=1
done
python tools/check_mechanical_move.py "$REV" app/src/migrate.py src/core/migrations_runner.py || FAIL=1
echo "FAIL=$FAIL"
```

Expected: every line prints `OK mechanical` and `FAIL=0`, except `migrations_runner.py`, which will report a difference because Step 5 changed `get_migrations_dir`. That one difference is intended. Confirm by eye that it is the only one, using:

```bash
git diff "$REV" -- app/src/migrate.py src/core/migrations_runner.py
```

- [ ] **Step 7: Run the full suite**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 537 passed.

- [ ] **Step 8: Confirm the migration filenames did not change**

```bash
cd app && ls src/core/migrations/ | head -3 && ls src/core/migrations/ | wc -l
```

Expected: 28 files, starting at `001_initial.sql`. The basenames must be byte-identical to what is recorded in `schema_migrations`, or production will re-run them.

- [ ] **Step 9: Commit**

```bash
git add -A app ruff.toml
git commit -m "refactor: move infrastructure modules into src.core

Mechanical move only, verified with tools/check_mechanical_move.py: every
moved file's AST is identical once import nodes are stripped. The one
intentional exception is migrations_runner.get_migrations_dir, which now
defaults to the migrations directory shipped inside the package.

Migration filenames are unchanged, so the 28 rows already recorded in
schema_migrations still match and nothing re-runs."
```

### Task 5: Move standup modules

**Files:**
- Create: `app/src/modules/standup/__init__.py` (empty for now)
- Move into `app/src/modules/standup/`: `handlers.py`, `blocks.py`, `blockers.py`, `autolink.py`, `workflow.py`, `templates_library.py`, `ai_summary.py`, `mailer.py`, `schedule_validation.py`
- Modify: import sites in `app/src` and `app/tests`

**Interfaces:**
- Consumes: `src.core.*` from Task 4
- Produces: `src.modules.standup.handlers.register_handlers(app)` with its existing signature.

- [ ] **Step 1: Move the files**

```bash
cd app/src
mkdir -p modules/standup && touch modules/standup/__init__.py
git mv handlers.py blocks.py blockers.py autolink.py workflow.py \
       templates_library.py ai_summary.py mailer.py schedule_validation.py \
       modules/standup/
```

- [ ] **Step 2: Rewrite import sites**

```bash
cd app
python - <<'PY'
import pathlib, re

MODS = ["handlers", "blocks", "blockers", "autolink", "workflow",
        "templates_library", "ai_summary", "mailer", "schedule_validation"]
names = "|".join(MODS)

pf = re.compile(r'^(\s*)from (' + names + r') import ', re.M)
pia = re.compile(r'^(\s*)import (' + names + r') as ', re.M)
pi = re.compile(r'^(\s*)import (' + names + r')\b(?! as)', re.M)

for p in list(pathlib.Path("src").rglob("*.py")) + list(pathlib.Path("tests").rglob("*.py")):
    t = p.read_text(); o = t
    t = pf.sub(lambda m: f"{m.group(1)}from src.modules.standup.{m.group(2)} import ", t)
    t = pia.sub(lambda m: f"{m.group(1)}import src.modules.standup.{m.group(2)} as ", t)
    t = pi.sub(lambda m: f"{m.group(1)}import src.modules.standup.{m.group(2)} as {m.group(2)}", t)
    if t != o:
        p.write_text(t); print("rewrote", p)
PY
ruff check --fix src tests
```

- [ ] **Step 3: Verify every moved file is mechanically identical**

```bash
cd app
REV=$(cat /tmp/premove_rev.txt)
FAIL=0
for f in handlers blocks blockers autolink workflow templates_library ai_summary mailer schedule_validation; do
  python tools/check_mechanical_move.py "$REV" "app/src/$f.py" "src/modules/standup/$f.py" || FAIL=1
done
echo "FAIL=$FAIL"
```

Expected: every line prints `OK mechanical` and `FAIL=0`. This is the step that protects the 71% of `handlers.py` the tests do not cover. If it reports a difference, revert the file and redo the move without hand-editing.

- [ ] **Step 4: Run the full suite**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 537 passed.

- [ ] **Step 5: Commit**

```bash
git add -A app
git commit -m "refactor: move standup modules into src.modules.standup

Mechanical move only, verified with the AST checker. This is the move the
checker exists for: handlers.py is 29% covered and blocks.py 40%, so a silent
logic change here would not be caught by the suite."
```

### Task 6: Move mcp and google_chat modules

**Files:**
- Create: `app/src/modules/mcp/__init__.py`, `app/src/modules/google_chat/__init__.py`
- Move: `mcp_http.py` to `modules/mcp/http.py`, `mcp_server.py` to `modules/mcp/server.py`
- Move: `google_chat_handler.py` to `modules/google_chat/handler.py`, `adapters/` to `modules/google_chat/adapters/`
- Modify: `app/src/main.py:137` and `app/src/main.py:144` import lines

**Interfaces:**
- Consumes: `src.core.*`
- Produces: `src.modules.mcp.http.mcp_bp`, `src.modules.google_chat.handler.google_chat_bp`, both Flask blueprints with unchanged names.

- [ ] **Step 1: Move the files**

```bash
cd app/src
mkdir -p modules/mcp modules/google_chat
touch modules/mcp/__init__.py modules/google_chat/__init__.py
git mv mcp_http.py modules/mcp/http.py
git mv mcp_server.py modules/mcp/server.py
git mv google_chat_handler.py modules/google_chat/handler.py
git mv adapters modules/google_chat/adapters
```

- [ ] **Step 2: Fix the import sites by hand**

These are few enough to edit directly. In `app/src/main.py`:

```python
            from src.modules.mcp.http import mcp_bp  # noqa: PLC0415
```

```python
            from src.modules.google_chat.handler import google_chat_bp  # noqa: PLC0415
```

In `app/src/modules/google_chat/handler.py`, the adapter import at what was line 29:

```python
        from src.modules.google_chat.adapters.google_chat import GoogleChatAdapter  # noqa: PLC0415
```

In `app/src/modules/mcp/http.py`, any `from mcp_server import ...` becomes:

```python
from src.modules.mcp.server import ...
```

- [ ] **Step 3: Verify the moves are mechanical**

```bash
cd app
REV=$(cat /tmp/premove_rev.txt)
python tools/check_mechanical_move.py "$REV" app/src/mcp_http.py src/modules/mcp/http.py
python tools/check_mechanical_move.py "$REV" app/src/mcp_server.py src/modules/mcp/server.py
python tools/check_mechanical_move.py "$REV" app/src/google_chat_handler.py src/modules/google_chat/handler.py
python tools/check_mechanical_move.py "$REV" app/src/adapters/base.py src/modules/google_chat/adapters/base.py
python tools/check_mechanical_move.py "$REV" app/src/adapters/google_chat.py src/modules/google_chat/adapters/google_chat.py
```

Expected: five `OK mechanical` lines.

- [ ] **Step 4: Verify both blueprints still import**

These modules are at 0% test coverage, so import them explicitly rather than trusting the suite:

```bash
cd app && python -c "
import sys; sys.path.insert(0, '.')
from src.modules.mcp.http import mcp_bp
from src.modules.google_chat.handler import google_chat_bp
print('blueprints import OK:', mcp_bp.name, google_chat_bp.name)
"
```

Expected: `blueprints import OK: mcp google_chat` (or whatever the existing blueprint names are, printed without error).

- [ ] **Step 5: Run the full suite**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 537 passed.

- [ ] **Step 6: Commit**

```bash
git add -A app
git commit -m "refactor: move mcp and google_chat into src.modules

Both are at 0% coverage, so the moves are verified with the AST checker and
an explicit blueprint import rather than by the test suite."
```

### Task 7: Entrypoint, Dockerfile, chart and the migrate shim

This is the task that can break self-hosted users, so it is deliberately separate and small.

**Files:**
- Modify: `app/src/main.py` (remove the `sys.path.insert`, update imports)
- Create: `app/src/migrate.py` (compatibility shim)
- Modify: `app/Dockerfile`
- Modify: `app/helm/morgenruf/templates/deployment.yaml:28`
- Modify: `app/helm/morgenruf/Chart.yaml` (version bump)
- Create: `app/tests/test_migrate_shim.py`

**Interfaces:**
- Consumes: `src.core.migrations_runner.run_migrations`
- Produces: `python -m src.main` as the runtime entrypoint, and `python src/migrate.py` as a still-working migration entrypoint.

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_migrate_shim.py`:

```python
"""The Helm chart hardcodes `python src/migrate.py`, so that path must keep working.

A self-hosted user who pulls a new image while pinning an older chart would
otherwise get an initContainer that crashes, and the pod would never start.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

APP = pathlib.Path(__file__).resolve().parents[1]


def test_shim_file_exists():
    assert (APP / "src" / "migrate.py").is_file()


def test_shim_exposes_run_migrations():
    sys.path.insert(0, str(APP))
    from src.migrate import run_migrations

    assert callable(run_migrations)


def test_shim_runs_as_a_script_path():
    """Without DATABASE_URL the runner exits 1 with a clear message.

    That proves the script path resolves and reaches the real runner, which is
    what the chart depends on.
    """
    result = subprocess.run(
        [sys.executable, "src/migrate.py"],
        cwd=APP,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 1
    assert "DATABASE_URL" in result.stderr


def test_chart_command_matches_the_shim_path():
    chart = (APP / "helm" / "morgenruf" / "templates" / "deployment.yaml").read_text()
    assert 'command: ["python", "src/migrate.py"]' in chart
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_migrate_shim.py -v
```

Expected: FAIL, because `src/migrate.py` was moved to `src/core/migrations_runner.py` in Task 4.

- [ ] **Step 3: Write the shim**

Create `app/src/migrate.py`:

```python
"""Compatibility entrypoint for `python src/migrate.py`.

The Helm chart hardcodes this path in the migrate initContainer
(helm/morgenruf/templates/deployment.yaml). A self-hosted user may pin an older
chart while pulling a newer image, so this path must keep working even though
the implementation now lives in src/core/migrations_runner.py.

Do not delete this file without a chart major version bump and a release note.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.migrations_runner import run_migrations  # noqa: E402

__all__ = ["run_migrations"]

if __name__ == "__main__":
    run_migrations()
```

Add the E402 exemption to `ruff.toml`:

```toml
[lint.per-file-ignores]
"app/src/main.py" = ["E402"]
"app/src/core/db.py" = ["E402"]
"app/src/migrate.py" = ["E402"]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd app && python -m pytest tests/test_migrate_shim.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Update `main.py`**

Remove the `sys.path.insert` line near the top and change the imports to package paths:

```python
from src.core.dashboard import dashboard_bp
from src.core.installation_store import PostgresInstallationStore
from src.core.oauth import oauth_bp
from src.core.scheduler import build_scheduler
from src.modules.standup.handlers import register_handlers
```

Keep the Sentry initialisation block exactly where it is, before those imports. That is why `main.py` carries the E402 exemption.

- [ ] **Step 6: Update the Dockerfile**

```dockerfile
COPY src/ ./src/
COPY teams.yaml.example ./teams.yaml
```

The `COPY migrations/ ./migrations/` line is deleted, because the SQL files now ship inside `src/core/migrations/` and are already covered by `COPY src/`.

Change the final line to:

```dockerfile
CMD ["python", "-m", "src.main"]
```

- [ ] **Step 7: Build and run the image to confirm both entrypoints resolve**

```bash
cd app
docker build -q -t morgenruf-entrypoint-check .
docker run --rm morgenruf-entrypoint-check python src/migrate.py; echo "migrate exit: $?"
docker run --rm morgenruf-entrypoint-check python -c "import src.main; print('main imports OK')"
```

Expected: the migrate run exits 1 with the `DATABASE_URL` error, proving the path resolves inside the image, and the second prints `main imports OK`.

- [ ] **Step 8: Bump the chart version**

In `app/helm/morgenruf/Chart.yaml`, bump `version` by one minor. Leave `deployment.yaml:28` exactly as it is: the shim exists so that line does not have to change.

- [ ] **Step 9: Run the full suite**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: 541 passed.

- [ ] **Step 10: Commit**

```bash
git add -A app ruff.toml
git commit -m "build: switch entrypoint to python -m src.main, keep migrate shim

The chart hardcodes `python src/migrate.py` in the migrate initContainer, a
path that lives in the chart rather than the image. Pulling a new image with
an older pinned chart would otherwise crash the initContainer and the pod
would never start. src/migrate.py stays as a shim so that combination keeps
working, and a test asserts the chart command and the shim path agree.

Migration SQL now ships inside src/core/migrations, so the separate COPY of
the migrations directory is no longer needed."
```

**R2 ships here.** Zero user-visible change. Before deploying, confirm with the checklist in spec section 9.7, and pay particular attention to step 3: the initContainer must complete and `schema_migrations` must gain no new rows.

---

# Release R3: The module contract

### Task 8: ModuleSpec, registry and activation

**Files:**
- Create: `app/src/core/modules.py`
- Create: `app/tests/test_modules_registry.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `ModuleSpec` dataclass with fields `name`, `required_scopes`, `migrations_dir`, `register_slack`, `register_routes`, `plan_jobs`, `claim_dm`, `purge`, `nav`, `default_enabled`
  - `NavItem` dataclass with fields `label`, `path`
  - `is_active(spec, granted_scopes, workspace_setting, allowlist) -> bool`
  - `active_modules(registry, granted_scopes, settings, allowlist) -> list[ModuleSpec]`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_modules_registry.py`:

```python
"""Activation rules for the module registry."""

from __future__ import annotations

from src.core.modules import ModuleSpec, active_modules, is_active


def spec(name="demo", scopes=(), default_enabled=True):
    return ModuleSpec(
        name=name,
        required_scopes=scopes,
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=(),
        default_enabled=default_enabled,
    )


def test_enabled_by_default_when_nothing_objects():
    assert is_active(spec(), granted_scopes={"chat:write"}, workspace_setting=None, allowlist=None) is True


def test_disabled_by_default_stays_off_without_a_workspace_row():
    assert is_active(spec(default_enabled=False), granted_scopes=set(), workspace_setting=None, allowlist=None) is False


def test_workspace_row_overrides_the_default():
    assert is_active(spec(default_enabled=False), granted_scopes=set(), workspace_setting=True, allowlist=None) is True
    assert is_active(spec(default_enabled=True), granted_scopes=set(), workspace_setting=False, allowlist=None) is False


def test_missing_scope_wins_over_an_enabled_workspace_row():
    s = spec(scopes=("mpim:write",))
    assert is_active(s, granted_scopes={"chat:write"}, workspace_setting=True, allowlist=None) is False
    assert is_active(s, granted_scopes={"mpim:write"}, workspace_setting=True, allowlist=None) is True


def test_allowlist_wins_over_everything():
    s = spec(name="connect")
    assert is_active(s, granted_scopes=set(), workspace_setting=True, allowlist={"standup"}) is False
    assert is_active(s, granted_scopes=set(), workspace_setting=True, allowlist={"standup", "connect"}) is True


def test_absent_allowlist_means_all_registered_modules():
    assert is_active(spec(), granted_scopes=set(), workspace_setting=None, allowlist=None) is True


def test_active_modules_filters_and_preserves_registry_order():
    registry = (spec("standup"), spec("connect", default_enabled=False), spec("kudos"))
    result = active_modules(registry, granted_scopes=set(), settings={}, allowlist=None)
    assert [m.name for m in result] == ["standup", "kudos"]
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_modules_registry.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.modules'`.

- [ ] **Step 3: Write the implementation**

Create `app/src/core/modules.py`:

```python
"""Module contract.

Core discovers features through an explicit registry of ModuleSpec values and
never imports a feature module by name. Adding a module is one directory under
src/modules plus one line in src.modules.REGISTRY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional


@dataclass(frozen=True)
class NavItem:
    label: str
    path: str


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    required_scopes: tuple[str, ...]
    migrations_dir: Optional[Path]
    register_slack: Optional[Callable]
    register_routes: Optional[Callable]
    plan_jobs: Optional[Callable]
    claim_dm: Optional[Callable]
    purge: Optional[Callable]
    nav: tuple[NavItem, ...]
    default_enabled: bool


def deploy_allowlist() -> Optional[set[str]]:
    """Module names this deployment permits, or None when unrestricted.

    MORGENRUF_MODULES lets a build ship a module that is present but dark.
    """
    raw = os.environ.get("MORGENRUF_MODULES", "").strip()
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_active(
    spec: ModuleSpec,
    granted_scopes: Iterable[str],
    workspace_setting: Optional[bool],
    allowlist: Optional[set[str]],
) -> bool:
    """Resolve activation. All four gates must pass, checked in order."""
    if allowlist is not None and spec.name not in allowlist:
        return False
    if not set(spec.required_scopes).issubset(set(granted_scopes)):
        return False
    if workspace_setting is not None:
        return workspace_setting
    return spec.default_enabled


def active_modules(
    registry: Iterable[ModuleSpec],
    granted_scopes: Iterable[str],
    settings: dict[str, bool],
    allowlist: Optional[set[str]],
) -> list[ModuleSpec]:
    """Registry members active for one workspace, in registry order."""
    granted = set(granted_scopes)
    return [s for s in registry if is_active(s, granted, settings.get(s.name), allowlist)]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_modules_registry.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add app/src/core/modules.py app/tests/test_modules_registry.py
git commit -m "feat: add ModuleSpec and registry activation rules

Activation resolves four gates in order: deploy allowlist, granted scopes,
per-workspace toggle, then the module default. Pure logic with no I/O, so it
is fully unit tested before anything depends on it."
```

### Task 9: DM router

Standup does not have one DM listener. It has eight, plus four slash commands:

```
handlers.py:803   @app.event("message")          catch-all; returns early unless a standup session is in progress
handlers.py:1380  @app.message("help")
handlers.py:1396  @app.message("standup")
handlers.py:1841  @app.message("skip")
handlers.py:1859  @app.message(re: i'm back / back from vacation)
handlers.py:1891  @app.message(re: ^kudos <@U...> ...)
handlers.py:1934  @app.message(re: ^timezone <zone>)
handlers.py:1480/1488/1504/1535  /standup /skip /help /kudos
```

The seven `@app.message` listeners each self-filter by pattern, so they do not collide with each other. The router therefore covers only the **catch-all** at 803, which is the listener a second module would genuinely fight with.

Keyword listeners still collide across modules, and the collision is concrete: Bolt's `@app.message("skip")` does a **substring** match, so a Connect command containing the word `skip` fires standup's skip handler. Prefixing the Connect command does not avoid it, because `"connect skip"` also contains `skip`. Task 15 adds a guard test that detects this class of overlap between modules, and the fix (anchoring standup's pattern) is a flagged behavior change recorded there.

**Files:**
- Create: `app/src/core/dm_router.py`
- Create: `app/tests/test_dm_router.py`

**Interfaces:**
- Consumes: `ModuleSpec` from Task 8
- Produces:
  - `DMContext` dataclass with fields `team_id`, `user_id`, `channel_id`, `text`, `event`, `client`
  - `route_dm(modules, ctx, fallback) -> str | None` returning the name of the module that claimed the message, or `None`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_dm_router.py`:

```python
"""One DM listener, offered to each active module in registry order."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.dm_router import DMContext, route_dm
from src.core.modules import ModuleSpec


def spec(name, claim):
    return ModuleSpec(
        name=name,
        required_scopes=(),
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=claim,
        purge=None,
        nav=(),
        default_enabled=True,
    )


def ctx(text="hello"):
    return DMContext(team_id="T1", user_id="U1", channel_id="D1", text=text, event={}, client=MagicMock())


def test_first_claimer_wins_and_later_modules_are_not_offered():
    second = MagicMock(return_value=True)
    modules = [spec("standup", lambda c: True), spec("connect", second)]
    assert route_dm(modules, ctx(), fallback=None) == "standup"
    second.assert_not_called()


def test_falls_through_to_the_next_module_when_the_first_declines():
    modules = [spec("standup", lambda c: False), spec("connect", lambda c: True)]
    assert route_dm(modules, ctx(), fallback=None) == "connect"


def test_fallback_runs_when_nobody_claims():
    fallback = MagicMock()
    modules = [spec("standup", lambda c: False)]
    assert route_dm(modules, ctx(), fallback=fallback) is None
    fallback.assert_called_once()


def test_modules_without_claim_dm_are_skipped():
    modules = [spec("mcp", None), spec("standup", lambda c: True)]
    assert route_dm(modules, ctx(), fallback=None) == "standup"


def test_a_raising_module_does_not_block_the_others():
    def boom(c):
        raise RuntimeError("module is broken")

    modules = [spec("broken", boom), spec("standup", lambda c: True)]
    assert route_dm(modules, ctx(), fallback=None) == "standup"
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_dm_router.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.dm_router'`.

- [ ] **Step 3: Write the implementation**

Create `app/src/core/dm_router.py`:

```python
"""Single message.im listener, shared by every module.

Bolt fires every listener that matches an event. If two modules each register
their own message handler, both process the same DM, and standup would treat a
Connect command as a standup answer. So modules expose claim_dm instead and
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
    stop the others from seeing their own commands.
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_dm_router.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add app/src/core/dm_router.py app/tests/test_dm_router.py
git commit -m "feat: add core DM router

Bolt fires every matching listener, so two modules registering their own
message handler would both process the same DM. Modules now expose claim_dm
and core owns the single listener, offering each message in registry order."
```

### Task 10: Per-module migrations

**Files:**
- Modify: `app/src/core/migrations_runner.py`
- Create: `app/tests/test_migrations_discovery.py`

**Interfaces:**
- Consumes: `ModuleSpec.migrations_dir`
- Produces: `collect_migration_files(core_dir, module_dirs, extra_dir=None) -> list[str]` returning absolute paths sorted by basename, and `assert_unique_basenames(paths) -> None` raising `ValueError` on a collision.

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_migrations_discovery.py`:

```python
"""Migration discovery across core and module directories."""

from __future__ import annotations

import pathlib

import pytest

from src.core.migrations_runner import assert_unique_basenames, collect_migration_files


def write(tmp_path: pathlib.Path, rel: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("SELECT 1;")
    return p


def test_collects_from_core_and_modules_sorted_by_basename(tmp_path):
    write(tmp_path, "core/002_b.sql")
    write(tmp_path, "core/001_a.sql")
    write(tmp_path, "connect/003_c.sql")
    found = collect_migration_files(tmp_path / "core", [tmp_path / "connect"])
    assert [pathlib.Path(f).name for f in found] == ["001_a.sql", "002_b.sql", "003_c.sql"]


def test_extra_dir_is_included_for_self_hosted_overrides(tmp_path):
    write(tmp_path, "core/001_a.sql")
    write(tmp_path, "extra/999_z.sql")
    found = collect_migration_files(tmp_path / "core", [], extra_dir=tmp_path / "extra")
    assert [pathlib.Path(f).name for f in found] == ["001_a.sql", "999_z.sql"]


def test_missing_directory_is_ignored(tmp_path):
    write(tmp_path, "core/001_a.sql")
    found = collect_migration_files(tmp_path / "core", [tmp_path / "does_not_exist"])
    assert len(found) == 1


def test_duplicate_basenames_raise():
    with pytest.raises(ValueError, match="001_a.sql"):
        assert_unique_basenames(["/x/core/001_a.sql", "/x/connect/001_a.sql"])


def test_unique_basenames_pass():
    assert_unique_basenames(["/x/core/001_a.sql", "/x/connect/002_b.sql"]) is None


def test_shipped_migrations_have_unique_basenames():
    """Guards the real tree: schema_migrations is keyed on the bare basename."""
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    paths = [str(p) for p in root.rglob("migrations/*.sql")]
    assert paths, "expected to find shipped migrations"
    assert_unique_basenames(paths)
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_migrations_discovery.py -v
```

Expected: FAIL with `ImportError: cannot import name 'collect_migration_files'`.

- [ ] **Step 3: Add the two functions to `migrations_runner.py`**

```python
def collect_migration_files(core_dir, module_dirs, extra_dir=None) -> list[str]:
    """Every .sql file across core, each module, and an optional extra directory.

    Sorted by basename, because schema_migrations is keyed on the bare
    basename and ordering must not depend on which directory a file lives in.
    """
    dirs = [core_dir, *module_dirs]
    if extra_dir:
        dirs.append(extra_dir)
    found: list[str] = []
    for d in dirs:
        if d and os.path.isdir(d):
            found.extend(glob.glob(os.path.join(str(d), "*.sql")))
    return sorted(found, key=lambda p: os.path.basename(p))


def assert_unique_basenames(paths) -> None:
    """Raise if two migrations share a basename.

    schema_migrations.filename is the bare basename, so a collision across two
    module directories would make one migration silently skip.
    """
    seen: dict[str, str] = {}
    for p in paths:
        name = os.path.basename(p)
        if name in seen:
            raise ValueError(f"duplicate migration basename {name}: {seen[name]} and {p}")
        seen[name] = p
```

Then change `run_migrations` to use them in place of its single-directory `glob`:

```python
    sql_files = collect_migration_files(
        core_dir=get_migrations_dir(),
        module_dirs=module_migration_dirs(),
        extra_dir=os.environ.get("EXTRA_MIGRATIONS_DIR"),
    )
    assert_unique_basenames(sql_files)
```

And add the module directory lookup, which reads the registry without importing any module by name:

```python
def module_migration_dirs() -> list:
    """Migration directories declared by registered modules."""
    try:
        from src.modules import REGISTRY
    except Exception:
        return []
    return [spec.migrations_dir for spec in REGISTRY if spec.migrations_dir]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_migrations_discovery.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Prove no already-applied migration would re-run**

```bash
cd app && python -c "
import sys; sys.path.insert(0, '.')
from src.core.migrations_runner import collect_migration_files, get_migrations_dir
names = [f.rsplit('/', 1)[-1] for f in collect_migration_files(get_migrations_dir(), [])]
print(len(names), 'migrations'); print(names[0], '...', names[-1])
"
```

Expected: `28 migrations`, first `001_initial.sql`, last `028_post_summary_default_true.sql`. Any change to these names would make production re-run migrations.

- [ ] **Step 6: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add app/src/core/migrations_runner.py app/tests/test_migrations_discovery.py
git commit -m "feat: discover migrations across core and module directories

Files are sorted by basename rather than full path, because
schema_migrations is keyed on the bare basename and ordering must not depend
on which directory a file lives in. A guard test asserts basenames are unique
across the whole tree, since a collision would silently skip a migration."
```

### Task 11: Convert standup to a ModuleSpec

**Files:**
- Modify: `app/src/modules/standup/__init__.py`
- Create: `app/src/modules/standup/migrations/` (move standup-specific SQL here)
- Modify: `app/src/modules/standup/handlers.py` (extract the DM branch into `claim_dm`)
- Create: `app/src/modules/__init__.py` registry
- Create: `app/tests/test_standup_module_spec.py`

**Interfaces:**
- Consumes: `ModuleSpec`, `NavItem`, `DMContext`
- Produces: `src.modules.standup.MODULE` and `src.modules.REGISTRY`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_standup_module_spec.py`:

```python
"""Standup exposes itself through the module contract."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.core.dm_router import DMContext
from src.core.modules import ModuleSpec
from src.modules import REGISTRY
from src.modules.standup import MODULE


def test_standup_is_a_module_spec():
    assert isinstance(MODULE, ModuleSpec)
    assert MODULE.name == "standup"


def test_standup_is_enabled_by_default():
    assert MODULE.default_enabled is True


def test_standup_requires_no_new_scopes():
    """Existing installs must keep working without re-authorising."""
    assert MODULE.required_scopes == ()


def test_standup_is_in_the_registry():
    assert MODULE in REGISTRY


def test_registry_names_are_unique():
    names = [s.name for s in REGISTRY]
    assert len(names) == len(set(names))


def test_claim_dm_claims_a_message_when_a_session_is_in_progress():
    """claim_dm covers the catch-all at handlers.py:803, which only acts on an
    in-progress standup session. The `standup` keyword is handled separately by
    the @app.message("standup") listener and is not claim_dm's job."""
    ctx = DMContext(
        team_id="T1",
        user_id="U1",
        channel_id="D1",
        text="finished the migration",
        event={},
        client=MagicMock(),
    )
    assert MODULE.claim_dm is not None
    with patch("src.modules.standup.handlers.state_store") as store:
        store.get.return_value = MagicMock(questions=["q1", "q2"])
        assert MODULE.claim_dm(ctx) is True


def test_claim_dm_declines_when_no_session_is_in_progress():
    """Matches the early return at handlers.py:817. Declining lets the router
    offer the message to the next module instead of swallowing it."""
    ctx = DMContext(
        team_id="T1",
        user_id="U1",
        channel_id="D1",
        text="anything",
        event={},
        client=MagicMock(),
    )
    with patch("src.modules.standup.handlers.state_store") as store:
        store.get.return_value = None
        assert MODULE.claim_dm(ctx) is False


def test_claim_dm_declines_messages_with_a_subtype():
    """Matches the early return at handlers.py:808."""
    ctx = DMContext(
        team_id="T1",
        user_id="U1",
        channel_id="D1",
        text="edited text",
        event={"subtype": "message_changed"},
        client=MagicMock(),
    )
    assert MODULE.claim_dm(ctx) is False
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_standup_module_spec.py -v
```

Expected: FAIL with `ImportError: cannot import name 'MODULE'`.

- [ ] **Step 3: Move the standup-owned migrations**

```bash
cd app/src
mkdir -p modules/standup/migrations
git mv core/migrations/002_standup_config.sql \
       core/migrations/004_edit_window.sql \
       core/migrations/005_mood.sql \
       core/migrations/006_standup_schedules.sql \
       core/migrations/007_autolink.sql \
       core/migrations/009_ai_summary.sql \
       core/migrations/016_schedule_report_channel.sql \
       core/migrations/017_vacation_sync_streak.sql \
       core/migrations/018_prepopulate_edit_window.sql \
       core/migrations/020_post_summary_toggle.sql \
       core/migrations/021_disable_summary_and_persist_threads.sql \
       core/migrations/022_daily_thread_schedule_scope.sql \
       core/migrations/024_recompute_has_blockers.sql \
       core/migrations/026_standup_schedule_id.sql \
       core/migrations/027_recompute_blockers_not_applicable.sql \
       core/migrations/028_post_summary_default_true.sql \
       modules/standup/migrations/
```

Basenames are unchanged, so nothing re-runs. `001_initial.sql`, `003_webhooks.sql`, `008_rbac.sql`, `012_platforms.sql`, `013_feed_token.sql`, `014_manager_email.sql`, `019_token_rotation.sql`, `023_webhook_deliveries.sql` and `025_installation_active.sql` stay in core, because they define installations, members, RBAC and webhook plumbing that core or several modules use. `010_kudos.sql` moves in Task 12 and `011_workflow_rules.sql`, `015_mcp_api_keys.sql` move in Task 13.

- [ ] **Step 4: Write the spec**

Replace `app/src/modules/standup/__init__.py`:

```python
"""Standup module.

Registered through the module contract rather than wired directly into
main.py, so that enabling, disabling or removing it is a registry change.
"""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.standup.handlers import claim_dm, register_handlers

MODULE = ModuleSpec(
    name="standup",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=None,
    plan_jobs=None,
    claim_dm=claim_dm,
    purge=None,
    nav=(NavItem(label="Standups", path="/"),),
    default_enabled=True,
)
```

`required_scopes` is deliberately empty. Standup must keep working on tokens issued before `granted_scopes` existed, where the recorded scope set is unknown.

`purge` is `None` because every standup table carries a foreign key to `installations(team_id) ON DELETE CASCADE`, so uninstall already cleans up through `delete_installation` (`core/db.py:1759`). `purge` exists for the narrower case of a workspace disabling a module and asking for its data to be deleted while staying installed.

- [ ] **Step 5: Extract `claim_dm` from the catch-all listener only**

Exactly one listener moves: the `@app.event("message")` catch-all at `handlers.py:803`. The seven `@app.message(...)` keyword listeners and the four slash commands stay exactly where they are and keep being registered by `register_handlers`, which is now called through `ModuleSpec.register_slack`.

Delete the `@app.event("message")` decorator and its wrapper, and turn the body into a module-level function. The three early returns become `False` (decline), and reaching the end becomes `True` (claimed):

```python
def claim_dm(ctx) -> bool:
    """Handle an in-progress standup answer sent by DM.

    This is the catch-all that used to be @app.event("message") at line 803.
    It only acts when a standup session is already in progress, so declining
    is the common case and lets the DM router offer the message to the next
    module.
    """
    event = ctx.event
    if event.get("channel_type") != "im":
        return False
    if event.get("subtype"):
        return False

    cache_key = f"{ctx.team_id}:{ctx.user_id}"
    session = state_store.get(cache_key)
    if not session:
        return False

    session = state_store.record_answer(cache_key, ctx.text)
    # ... the remainder of the original body, unchanged, reading ctx.client
    # where the listener read `client` and using ctx.client.chat_postMessage
    # where it used `say`
    return True
```

`say` is a Bolt convenience that posts to the incoming channel. Replace each `say(...)` with `ctx.client.chat_postMessage(channel=ctx.channel_id, ...)`, which is what `say` does internally. Keep every argument otherwise identical.

Verify the move did not change behavior, using the function-level checker:

```bash
cd app && python -c "
import sys, subprocess; sys.path.insert(0, '.')
from tools.check_mechanical_move import changed_functions
old = subprocess.run(['git','show','HEAD~1:app/src/modules/standup/handlers.py'],
                     capture_output=True, text=True).stdout
new = open('src/modules/standup/handlers.py').read()
print('changed:', changed_functions(old, new, ['register_handlers']))
"
```

Expected: `register_handlers` appears in the changed list, because its DM listener was removed. That is the one intended change in this file. Review the diff by eye to confirm nothing else moved.

- [ ] **Step 6: Create the registry**

Replace `app/src/modules/__init__.py`:

```python
"""Module registry.

Adding a module is one directory here plus one line in REGISTRY. Core never
imports a module by name, so removing a line is enough to remove a feature.
Order matters: the DM router offers each message to modules in this order.
"""

from __future__ import annotations

from src.modules.standup import MODULE as STANDUP

REGISTRY = (STANDUP,)
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_standup_module_spec.py -v
```

Expected: 6 passed.

- [ ] **Step 8: Run the full suite**

```bash
cd app && python -m pytest tests/ -q | tail -3
```

Expected: all green. Some existing standup DM tests will need their call site updated from the Bolt listener to `claim_dm`. Update the call site only. If a test's assertions need changing, stop: that means behavior changed.

- [ ] **Step 9: Commit**

```bash
git add -A app
git commit -m "feat: convert standup to the module contract

Standup now exposes a ModuleSpec and its DM handling moves behind claim_dm,
so core owns the single message.im listener. required_scopes is empty on
purpose: standup must keep working on tokens issued before granted_scopes
existed, where the recorded scope set is unknown.

Standup-owned migrations move into the module directory. Basenames are
unchanged, so nothing re-runs in production."
```

### Task 12: Extract kudos into its own module

Kudos is Donut's Recognition pillar, already shipped but tangled into `core/db.py` and `standup/handlers.py`.

**Files:**
- Create: `app/src/modules/kudos/__init__.py`, `app/src/modules/kudos/db.py`, `app/src/modules/kudos/handlers.py`
- Move: `010_kudos.sql` to `app/src/modules/kudos/migrations/`
- Modify: `app/src/core/db.py` (remove the three kudos functions), `app/src/modules/standup/handlers.py` (remove the kudos command branches)
- Create: `app/tests/test_kudos_module.py`

**Interfaces:**
- Consumes: `ModuleSpec`, `DMContext`
- Produces: `src.modules.kudos.MODULE`, and `save_kudos`, `get_kudos`, `get_kudos_leaderboard` with signatures identical to their previous definitions in `core/db.py:1560-1607`.

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_kudos_module.py`:

```python
"""Kudos is its own module, extracted verbatim from core.db and standup."""

from __future__ import annotations

import inspect
import subprocess

from src.core.modules import ModuleSpec
from src.modules import REGISTRY
from src.modules.kudos import MODULE
from src.modules.kudos import db as kudos_db
from tools.check_mechanical_move import changed_functions

FUNCS = ["save_kudos", "get_kudos", "get_kudos_leaderboard"]


def test_kudos_is_a_module_spec_in_the_registry():
    assert isinstance(MODULE, ModuleSpec)
    assert MODULE.name == "kudos"
    assert MODULE in REGISTRY


def test_kudos_requires_no_new_scopes():
    assert MODULE.required_scopes == ()


def test_the_three_functions_moved_verbatim():
    old = subprocess.run(["git", "show", "HEAD:app/src/core/db.py"], capture_output=True, text=True).stdout
    new = inspect.getsource(kudos_db)
    assert changed_functions(old, new, FUNCS) == []


def test_core_db_no_longer_defines_them():
    from src.core import db as core_db

    for name in FUNCS:
        assert not hasattr(core_db, name), f"core.db still defines {name}"


def test_kudos_has_no_catch_all():
    """Kudos only has anchored patterns, so it never needs the DM router."""
    assert MODULE.claim_dm is None


def test_kudos_registers_its_own_slack_listeners():
    from unittest.mock import MagicMock

    assert MODULE.register_slack is not None
    bolt_app = MagicMock()
    MODULE.register_slack(bolt_app)
    assert bolt_app.message.called, "kudos did not register its message listener"
    assert bolt_app.command.called, "kudos did not register its slash command"
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_kudos_module.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.kudos'`.

- [ ] **Step 3: Move the three functions verbatim**

Cut `save_kudos`, `get_kudos` and `get_kudos_leaderboard` from `core/db.py` (they sit at lines 1560 to 1607) and paste them unchanged into `app/src/modules/kudos/db.py`, with this header:

```python
"""Kudos persistence, extracted verbatim from core.db.

The function bodies are unchanged. A test asserts that with an AST comparison
against the previous revision, so the extraction cannot silently alter
behavior.
"""

from __future__ import annotations

import psycopg2.extras

from src.core.db import db_conn
```

- [ ] **Step 4: Move the migration and the DM branch**

```bash
cd app/src && mkdir -p modules/kudos/migrations && git mv core/migrations/010_kudos.sql modules/kudos/migrations/
```

Kudos has two entry points in `standup/handlers.py`, and both move:

- `@app.message(re.compile(r"^kudos\s+<@([A-Z0-9]+)>\s+(.+)$", re.IGNORECASE))` at line 1891
- `@app.command("/kudos")` at line 1535

Both move into `app/src/modules/kudos/handlers.py` as a `register_handlers(app)` that re-registers them unchanged, wired through `ModuleSpec.register_slack`. The regex is already anchored with `^`, so it does not collide with other modules and does not need a router.

Kudos therefore sets `claim_dm=None`: it has no catch-all behavior, only anchored patterns. That is the normal case for a module, and the reason the DM router only has to arbitrate the catch-all.

- [ ] **Step 5: Write the spec and register it**

`app/src/modules/kudos/__init__.py`:

```python
"""Kudos module: peer recognition."""

from __future__ import annotations

from pathlib import Path

from src.core.modules import ModuleSpec, NavItem
from src.modules.kudos.handlers import register_handlers

MODULE = ModuleSpec(
    name="kudos",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,
    register_routes=None,
    plan_jobs=None,
    claim_dm=None,
    purge=None,
    nav=(NavItem(label="Kudos", path="/m/kudos/"),),
    default_enabled=True,
)
```

In `app/src/modules/__init__.py`:

```python
from src.modules.kudos import MODULE as KUDOS
from src.modules.standup import MODULE as STANDUP

REGISTRY = (STANDUP, KUDOS)
```

Standup comes first so its catch-all sees an in-progress standup answer before any other module's catch-all. Kudos has no catch-all, so ordering does not affect it, but the registry order is what the DM router walks and it should read in priority order.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_kudos_module.py -v
```

Expected: 6 passed.

- [ ] **Step 7: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add -A app
git commit -m "refactor: extract kudos into its own module

Kudos already implements Donut's Recognition pillar but was tangled into
core.db and standup handlers. The three persistence functions move verbatim,
asserted by an AST comparison against the previous revision.

Standup stays ahead of kudos in the registry, so an in-progress standup
answer is still claimed by standup even if it begins with the word kudos."
```

### Task 13: Convert mcp and google_chat, and wire the registry into main

**Files:**
- Modify: `app/src/modules/mcp/__init__.py`, `app/src/modules/google_chat/__init__.py`
- Move: `015_mcp_api_keys.sql` to `modules/mcp/migrations/`, `012_platforms.sql` to `modules/google_chat/migrations/`
- Modify: `app/src/main.py` (replace the two conditional blueprint registrations and `register_handlers` with a registry loop)
- Create: `app/tests/test_main_wiring.py`

**Interfaces:**
- Consumes: `active_modules`, `deploy_allowlist`, `route_dm`, `REGISTRY`
- Produces: `src.main.register_modules(flask_app, bolt_app, registry) -> list[str]` returning the names of the modules it registered.

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_main_wiring.py`:

```python
"""main.py registers modules through the registry, not by name."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.modules import ModuleSpec
from src.main import register_modules


def spec(name, routes=None, slack=None):
    return ModuleSpec(
        name=name,
        required_scopes=(),
        migrations_dir=None,
        register_slack=slack,
        register_routes=routes,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=(),
        default_enabled=True,
    )


def test_registers_routes_and_slack_listeners_for_each_module():
    routes, slack = MagicMock(), MagicMock()
    flask_app, bolt_app = MagicMock(), MagicMock()
    names = register_modules(flask_app, bolt_app, [spec("demo", routes, slack)])
    assert names == ["demo"]
    routes.assert_called_once_with(flask_app)
    slack.assert_called_once_with(bolt_app)


def test_modules_with_no_hooks_are_still_reported():
    names = register_modules(MagicMock(), MagicMock(), [spec("empty")])
    assert names == ["empty"]


def test_a_module_that_fails_to_register_does_not_stop_the_others():
    def boom(_):
        raise RuntimeError("bad module")

    names = register_modules(MagicMock(), MagicMock(), [spec("broken", boom), spec("ok")])
    assert names == ["ok"]


def test_no_module_is_imported_by_name_in_main():
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1] / "src" / "main.py").read_text()
    for forbidden in ["modules.standup", "modules.kudos", "modules.mcp", "modules.google_chat"]:
        assert forbidden not in source, f"main.py still imports {forbidden} directly"
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_main_wiring.py -v
```

Expected: FAIL with `ImportError: cannot import name 'register_modules'`.

- [ ] **Step 3: Write the specs for mcp and google_chat**

`app/src/modules/mcp/__init__.py`:

```python
"""MCP module: HTTP surface for the Model Context Protocol server."""

from __future__ import annotations

import os
from pathlib import Path

from src.core.modules import ModuleSpec
from src.modules.mcp.http import mcp_bp


def register_routes(flask_app) -> None:
    flask_app.register_blueprint(mcp_bp)


MODULE = ModuleSpec(
    name="mcp",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=None,
    register_routes=register_routes,
    plan_jobs=None,
    claim_dm=None,
    purge=None,
    nav=(),
    default_enabled=True,
)
```

`default_enabled=True` is not a guess. `main.py:137` registers `mcp_bp` unconditionally today, with no environment gate at all. Introducing one here would silently disable MCP for every workspace, which is a behavior change. The module contract makes MCP switchable per workspace later through `workspace_modules`, but its default must match today's behavior exactly.

`app/src/modules/google_chat/__init__.py` follows the same shape with `register_routes` registering `google_chat_bp`, but google_chat *is* conditional today (`main.py:142` checks `GOOGLE_CREDENTIALS`), so it mirrors that:

```python
MODULE = ModuleSpec(
    name="google_chat",
    required_scopes=(),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=None,
    register_routes=register_routes,
    plan_jobs=None,
    claim_dm=None,
    purge=None,
    nav=(),
    default_enabled=bool(os.environ.get("GOOGLE_CREDENTIALS")),
)
```

Keep google_chat's existing `try`/`except` around blueprint registration. `register_modules` already logs and skips a module that raises, so the behavior is preserved by the contract rather than by the call site.

- [ ] **Step 4: Write `register_modules` in `main.py`**

```python
def register_modules(flask_app, bolt_app, registry) -> list[str]:
    """Wire each module's routes and Slack listeners. Returns registered names.

    A module that raises during registration is logged and skipped, so one bad
    module cannot stop the process from starting.
    """
    registered: list[str] = []
    for spec in registry:
        try:
            if spec.register_routes is not None:
                spec.register_routes(flask_app)
            if spec.register_slack is not None:
                spec.register_slack(bolt_app)
        except Exception:
            logging.getLogger(__name__).exception("failed to register module %s", spec.name)
            continue
        registered.append(spec.name)
    return registered
```

Replace the direct `register_handlers(app)` call and both conditional blueprint blocks with:

```python
from src.core.modules import active_modules, deploy_allowlist
from src.modules import REGISTRY

_enabled = [s for s in REGISTRY if deploy_allowlist() is None or s.name in deploy_allowlist()]
register_modules(flask_app, app, _enabled)
```

Per-workspace activation (`active_modules`) applies at request and job time, not at process start, because scopes and workspace settings differ per team.

- [ ] **Step 5: Register the core DM listener**

Add the single `message.im` listener in core, replacing the one standup used to own:

```python
@app.event("message")
def handle_dm(event, client, logger):  # noqa: ANN001
    if event.get("channel_type") != "im" or event.get("bot_id"):
        return
    team_id = event.get("team") or ""
    ctx = DMContext(
        team_id=team_id,
        user_id=event.get("user", ""),
        channel_id=event.get("channel", ""),
        text=(event.get("text") or "").strip(),
        event=event,
        client=client,
    )
    modules = active_modules(
        REGISTRY,
        granted_scopes=db.granted_scopes(team_id),
        settings=db.module_settings(team_id),
        allowlist=deploy_allowlist(),
    )
    route_dm(modules, ctx, fallback=_dm_help_fallback)
```

`db.granted_scopes` and `db.module_settings` arrive in Task 17 and Task 18. Until then, stub them in `core/db.py` to return a permissive default so this task stays independently shippable:

```python
def granted_scopes(team_id: str) -> set[str]:
    """Scopes Slack actually granted. Replaced in Task 17 by a real lookup."""
    return set()


def module_settings(team_id: str) -> dict[str, bool]:
    """Per-workspace module toggles. Replaced in Task 18 by a real lookup."""
    return {}
```

Both stubs are safe: an empty scope set only blocks modules that declare `required_scopes`, and every module in the registry at this point declares none.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_main_wiring.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Run the full suite and start the app to check wiring**

```bash
cd app && python -m pytest tests/ -q | tail -3
DATABASE_URL= python -c "
import sys; sys.path.insert(0, '.')
import src.main
print('main imports and wires OK')
"
```

Expected: suite green, and the import prints without raising.

- [ ] **Step 8: Commit**

```bash
git add -A app
git commit -m "feat: wire modules through the registry in main

Replaces the direct register_handlers call and the two hand-rolled
conditional blueprint registrations with one registry loop, so main.py no
longer imports any feature module by name. A test asserts that stays true.

Core now owns the single message.im listener and dispatches through the DM
router. granted_scopes and module_settings are permissive stubs here and get
real implementations in the scope and toggle tasks."
```

### Task 14: Namespaced jobs and reconcile

**Files:**
- Modify: `app/src/core/scheduler.py`
- Create: `app/tests/test_job_reconcile.py`

**Interfaces:**
- Consumes: `ModuleSpec.plan_jobs`
- Produces:
  - `JobSpec` dataclass with fields `key`, `trigger`, `func`, `args`
  - `job_id(module, team_id, key) -> str` returning `"{module}:{team_id}:{key}"`
  - `reconcile_jobs(scheduler, desired) -> tuple[list[str], list[str]]` returning the ids added and removed

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_job_reconcile.py`:

```python
"""Namespaced job ids and reconcile-by-diff."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.scheduler import job_id, reconcile_jobs


def fake_scheduler(existing_ids):
    s = MagicMock()
    s.get_jobs.return_value = [MagicMock(id=i) for i in existing_ids]
    return s


def desired(ids):
    return {i: MagicMock() for i in ids}


def test_job_id_is_namespaced_by_module_and_team():
    assert job_id("connect", "T1", "round") == "connect:T1:round"


def test_adds_missing_jobs():
    s = fake_scheduler([])
    added, removed = reconcile_jobs(s, desired(["connect:T1:round"]))
    assert added == ["connect:T1:round"]
    assert removed == []


def test_removes_jobs_that_are_no_longer_desired():
    s = fake_scheduler(["connect:T1:round"])
    added, removed = reconcile_jobs(s, desired([]))
    assert added == []
    assert removed == ["connect:T1:round"]
    s.remove_job.assert_called_once_with("connect:T1:round")


def test_leaves_unchanged_jobs_alone():
    s = fake_scheduler(["connect:T1:round"])
    added, removed = reconcile_jobs(s, desired(["connect:T1:round"]))
    assert (added, removed) == ([], [])
    s.remove_job.assert_not_called()


def test_disabling_a_module_removes_only_its_jobs():
    s = fake_scheduler(["connect:T1:round", "standup:T1:daily"])
    added, removed = reconcile_jobs(s, desired(["standup:T1:daily"]))
    assert removed == ["connect:T1:round"]


def test_jobs_outside_the_namespace_are_never_removed():
    """Legacy standup job ids predate namespacing and must survive."""
    s = fake_scheduler(["legacy-workspace-T1", "connect:T1:round"])
    added, removed = reconcile_jobs(s, desired(["connect:T1:round"]))
    assert removed == []
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_job_reconcile.py -v
```

Expected: FAIL with `ImportError: cannot import name 'job_id'`.

- [ ] **Step 3: Write the implementation**

Add to `app/src/core/scheduler.py`:

```python
@dataclass(frozen=True)
class JobSpec:
    key: str
    trigger: Any
    func: Any
    args: tuple


def job_id(module: str, team_id: str, key: str) -> str:
    """Namespaced job id, so a module's jobs can be found and removed as a set."""
    return f"{module}:{team_id}:{key}"


def reconcile_jobs(scheduler, desired: dict) -> tuple[list[str], list[str]]:
    """Make the live job set match `desired`, for namespaced ids only.

    Ids without a namespace prefix are left alone: standup's existing job ids
    predate this scheme and removing them would stop production standups.
    """
    live = {j.id for j in scheduler.get_jobs() if ":" in j.id}
    wanted = set(desired)
    added = sorted(wanted - live)
    removed = sorted(live - wanted)
    for jid in removed:
        scheduler.remove_job(jid)
    for jid in added:
        spec = desired[jid]
        scheduler.add_job(spec.func, spec.trigger, args=spec.args, id=jid, replace_existing=True)
    return added, removed
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_job_reconcile.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add app/src/core/scheduler.py app/tests/test_job_reconcile.py
git commit -m "feat: namespaced job ids and reconcile by diff

Disabling a module now makes its jobs disappear on the next reconcile with no
bespoke teardown code. Job ids without a namespace prefix are never removed,
because standup's existing ids predate this scheme and removing them would
stop production standups."
```

### Task 15: Action id namespacing guard

**Files:**
- Create: `app/tests/test_action_id_namespacing.py`

**Interfaces:**
- Consumes: the registry
- Produces: a guard test only

- [ ] **Step 1: Write the test**

Create `app/tests/test_action_id_namespacing.py`:

```python
"""New modules must namespace their Slack action ids.

Standup's existing action ids stay bare on purpose: changing them would break
buttons in Slack messages already delivered to users. Everything added after
the module contract must carry a `<module>:` prefix, so two modules cannot
collide on the same action id.
"""

from __future__ import annotations

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
GRANDFATHERED = {"standup"}

ACTION_RE = re.compile(r'action_id\s*[=:]\s*["\']([^"\']+)["\']')


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
```

- [ ] **Step 2: Run it**

```bash
cd app && python -m pytest tests/test_action_id_namespacing.py -v
```

Expected: 2 passed. If `test_the_guard_actually_finds_action_ids` fails, the regex needs widening to match how this codebase writes action ids. Fix the regex, not the assertion.

- [ ] **Step 3: Add the cross-module message-pattern guard**

Append to the same file:

```python
MESSAGE_RE = re.compile(r'@app\.message\(\s*["\']([^"\']+)["\']', re.M)


def test_no_two_modules_share_a_bare_string_message_pattern():
    """Bolt's @app.message with a plain string does a SUBSTRING match.

    standup registers @app.message("skip"). Any other module whose command
    contains the word skip, including "connect skip" or "skip this round",
    would also fire standup's handler. Prefixing does not avoid it. The fix is
    to anchor the pattern with a regex, which is a flagged behavior change.
    """
    by_module = {}
    for d in module_dirs():
        pats = set()
        for py in d.rglob("*.py"):
            pats.update(MESSAGE_RE.findall(py.read_text()))
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
```

- [ ] **Step 4: Run the guard**

```bash
cd app && python -m pytest tests/test_action_id_namespacing.py -v
```

Expected: 3 passed. The collision test passes today because standup is the only module with bare string patterns. It starts failing the moment a second module adds one, which is exactly when the decision below has to be made.

**Decision (2026-09-16): standup's patterns stay exactly as they are.**

Standup registers three bare string patterns: `@app.message("help")`, `@app.message("standup")` and `@app.message("skip")`. All three are substring matches, so a DM reading "can I skip today" fires standup's skip handler.

Anchoring them as regexes was considered and rejected. It would narrow what standup accepts for users who already rely on the loose matching, and standup is live in production. No behavior change for existing users wins.

The constraint this places on Connect: **Connect must not register any DM command containing the words help, standup or skip.** Opt-out is button-only, through the interactive elements on the intro message, rather than a DM keyword. The Connect plan inherits this as a hard requirement.

The guard test above still earns its place: it goes red if any future module adds a bare string pattern that overlaps, which is precisely the mistake this decision is designed to avoid.

- [ ] **Step 5: Commit**

```bash
git add app/tests/test_action_id_namespacing.py
git commit -m "test: guard action id and message pattern collisions across modules

Standup's bare action ids are grandfathered, because changing them would
break buttons in Slack messages already delivered.

The message-pattern guard catches a concrete hazard: Bolt's @app.message with
a plain string is a substring match, so standup's \"skip\" would fire on any
other module's command containing that word. The guard passes today and
starts failing the moment a second module adds a bare string pattern.

The third test guards against the regexes silently matching nothing and the
checks passing vacuously."
```

**R3 ships here.** Zero user-visible change. Deploy per the checklist in spec section 9.7.

---

# Release R4: Roster, granted scopes, and the enable card

### Task 16: Shared roster

**Files:**
- Create: `app/src/core/roster.py`
- Create: `app/tests/test_roster.py`
- Modify: the standup participant filtering call sites to use it

**Interfaces:**
- Consumes: `src.core.db`
- Produces:
  - `Member` dataclass with fields `user_id`, `name`, `tz`
  - `eligible_members(team_id, channel_id=None, exclude=()) -> list[Member]`

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_roster.py`:

```python
"""Shared eligibility: one answer to who can be contacted right now."""

from __future__ import annotations

from unittest.mock import patch

from src.core.roster import Member, eligible_members

ROWS = [
    {"user_id": "U1", "real_name": "Ada", "tz": "UTC", "is_bot": False, "deleted": False},
    {"user_id": "U2", "real_name": "Bot", "tz": "UTC", "is_bot": True, "deleted": False},
    {"user_id": "U3", "real_name": "Gone", "tz": "UTC", "is_bot": False, "deleted": True},
    {"user_id": "U4", "real_name": "Away", "tz": "UTC", "is_bot": False, "deleted": False},
]


def run(exclude=(), away=("U4",)):
    with patch("src.core.roster.db") as db:
        db.get_members.return_value = ROWS
        db.get_away_user_ids.return_value = set(away)
        return eligible_members("T1", exclude=exclude)


def test_bots_are_excluded():
    assert "U2" not in [m.user_id for m in run()]


def test_deactivated_users_are_excluded():
    assert "U3" not in [m.user_id for m in run()]


def test_users_on_vacation_are_excluded():
    assert "U4" not in [m.user_id for m in run()]


def test_the_remaining_user_is_returned_as_a_member():
    result = run()
    assert result == [Member(user_id="U1", name="Ada", tz="UTC")]


def test_explicit_exclusions_are_honoured():
    assert run(exclude=("U1",)) == []


def test_nobody_is_excluded_when_nobody_is_away():
    assert [m.user_id for m in run(away=())] == ["U1", "U4"]
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_roster.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.roster'`.

- [ ] **Step 3: Write the implementation**

Create `app/src/core/roster.py`:

```python
"""Shared eligibility.

One question, one answer, for every module: who in this workspace can be
contacted right now. Standup filtered this inline; extracting it means Connect
cannot accidentally disagree about who is on vacation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from src.core import db


@dataclass(frozen=True)
class Member:
    user_id: str
    name: str
    tz: str


def eligible_members(
    team_id: str,
    channel_id: Optional[str] = None,
    exclude: Iterable[str] = (),
) -> list[Member]:
    """Members who are real, active, not away, and not explicitly excluded."""
    away = db.get_away_user_ids(team_id)
    skip = set(exclude) | set(away)
    out: list[Member] = []
    for row in db.get_members(team_id, channel_id=channel_id) if channel_id else db.get_members(team_id):
        if row.get("is_bot") or row.get("deleted"):
            continue
        if row["user_id"] in skip:
            continue
        out.append(
            Member(
                user_id=row["user_id"],
                name=row.get("real_name") or row.get("name") or "",
                tz=row.get("tz") or "UTC",
            )
        )
    return out
```

If `db.get_away_user_ids` does not exist yet, add it next to the existing `user_away` queries in `core/db.py`, returning a set of user ids whose away window covers today. Match the date logic the existing vacation filtering already uses rather than inventing new logic.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_roster.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Point standup at the shared roster**

Replace standup's inline bot, deleted and away filtering with a call to `eligible_members`. Run the existing participation tests, which are the regression net here:

```bash
cd app && python -m pytest tests/test_participation.py tests/test_participant_delivery.py tests/test_participant_registration.py tests/test_scheduler_channel_sync.py -v
```

Expected: all pass with no assertion changes. If an assertion has to change, standup's filtering differed from the extracted version. Stop and reconcile the difference before continuing.

- [ ] **Step 6: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add -A app
git commit -m "feat: extract shared roster into core

Standup filtered bots, deactivated users and vacationing members inline.
Extracting it means Connect cannot accidentally disagree with standup about
who is away. The existing participation tests are the regression net and pass
without assertion changes."
```

### Task 17: Record granted scopes

**Files:**
- Create: `app/src/core/migrations/029_granted_scopes.sql`
- Modify: `app/src/core/oauth.py` (capture `resp["scope"]`), `app/src/core/db.py` (`save_installation`, new `granted_scopes`)
- Create: `app/tests/test_granted_scopes.py`

**Interfaces:**
- Consumes: the `oauth.v2.access` response
- Produces: `db.granted_scopes(team_id) -> set[str]`, replacing the Task 13 stub, and `db.has_scopes(team_id, required) -> bool`

- [ ] **Step 1: Write the migration**

Create `app/src/core/migrations/029_granted_scopes.sql`:

```sql
-- Record what Slack actually granted at install time.
--
-- The manifest and the OAuth authorize URL have already drifted apart once
-- (the manifest declares app_mentions:read, channels:join, chat:write.public
-- and team:read, none of which the authorize URL requests), so the requested
-- scope list is not a reliable record of what a workspace holds.
--
-- Nullable with no default, so this is metadata-only and does not rewrite the
-- table. NULL means "installed before we recorded this", which the lookup
-- treats as unknown rather than as empty.
ALTER TABLE installations ADD COLUMN IF NOT EXISTS granted_scopes TEXT[];
```

- [ ] **Step 2: Write the failing test**

Create `app/tests/test_granted_scopes.py`:

```python
"""granted_scopes records what Slack actually granted, not what we asked for."""

from __future__ import annotations

from unittest.mock import patch

from src.core.db import has_scopes, parse_scope_field


def test_parse_splits_the_comma_separated_slack_field():
    assert parse_scope_field("chat:write,im:write,users:read") == ["chat:write", "im:write", "users:read"]


def test_parse_handles_an_empty_field():
    assert parse_scope_field("") == []
    assert parse_scope_field(None) == []


def test_parse_strips_whitespace():
    assert parse_scope_field("chat:write, im:write") == ["chat:write", "im:write"]


def test_has_scopes_is_true_when_all_are_present():
    with patch("src.core.db.granted_scopes", return_value={"mpim:write", "chat:write"}):
        assert has_scopes("T1", ["mpim:write"]) is True


def test_has_scopes_is_false_when_one_is_missing():
    with patch("src.core.db.granted_scopes", return_value={"chat:write"}):
        assert has_scopes("T1", ["mpim:write", "chat:write"]) is False


def test_requiring_nothing_is_always_true():
    """Standup declares no required scopes and must never be gated."""
    with patch("src.core.db.granted_scopes", return_value=set()):
        assert has_scopes("T1", []) is True
```

- [ ] **Step 3: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_granted_scopes.py -v
```

Expected: FAIL with `ImportError: cannot import name 'parse_scope_field'`.

- [ ] **Step 4: Write the implementation**

In `app/src/core/db.py`:

```python
def parse_scope_field(scope: str | None) -> list[str]:
    """Split the comma-separated `scope` field from oauth.v2.access."""
    if not scope:
        return []
    return [s.strip() for s in scope.split(",") if s.strip()]


def granted_scopes(team_id: str) -> set[str]:
    """Scopes Slack granted this workspace, from the OAuth response.

    Returns an empty set when the column is NULL, which means the workspace
    installed before this was recorded. Modules that declare required_scopes
    stay off for those workspaces until an admin re-authorises, which is the
    safe direction to fail in.
    """
    sql = "SELECT granted_scopes FROM installations WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            row = cur.fetchone()
    return set(row[0]) if row and row[0] else set()


def has_scopes(team_id: str, required) -> bool:
    """True when the workspace holds every scope in `required`."""
    required = list(required)
    if not required:
        return True
    return set(required).issubset(granted_scopes(team_id))
```

Delete the Task 13 stub versions of `granted_scopes` and `module_settings` as you replace them.

Add a `granted_scopes` parameter to `save_installation`, defaulting to `None`, and include it in both the `INSERT` column list and the `ON CONFLICT DO UPDATE SET` clause, following the existing pattern for `bot_refresh_token`.

In `app/src/core/oauth.py`, at the `save_installation` call site:

```python
        is_new_install = db.save_installation(
            ...
            bot_token_expires_at=expires_at_str,
            granted_scopes=db.parse_scope_field(resp.get("scope")),
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_granted_scopes.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Verify the migration is metadata-only**

```bash
cd app && grep -c "ADD COLUMN IF NOT EXISTS" src/core/migrations/029_granted_scopes.sql
grep -iE "DROP|ALTER COLUMN|UPDATE |DELETE " src/core/migrations/029_granted_scopes.sql && echo "NOT ADDITIVE" || echo "additive only"
```

Expected: `1` then `additive only`. A non-additive migration here would break the image-revert rollback guarantee.

- [ ] **Step 7: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add -A app
git commit -m "feat: record granted OAuth scopes per installation

The manifest and the authorize URL have already drifted apart once, so the
requested scope list is not a reliable record of what a workspace holds.
granted_scopes is read from the scope field of the oauth.v2.access response.

A NULL column means the workspace installed before this was recorded, and
modules declaring required scopes stay off for those workspaces until an
admin re-authorises. Standup declares none, so it is never gated."
```

### Task 18: Workspace module toggles and the enable card

**Files:**
- Create: `app/src/core/migrations/030_workspace_modules.sql`
- Modify: `app/src/core/db.py` (`module_settings`, `set_module_enabled`)
- Modify: `app/src/core/dashboard.py` (nav from active modules, enable card, toggle endpoint)
- Create: `app/tests/test_workspace_modules.py`

**Interfaces:**
- Consumes: `granted_scopes`, `active_modules`, `ModuleSpec.nav`
- Produces: `db.module_settings(team_id) -> dict[str, bool]` (replacing the Task 13 stub), `db.set_module_enabled(team_id, module, enabled) -> None`, and `POST /api/modules/<name>` on the dashboard

- [ ] **Step 1: Write the migration**

Create `app/src/core/migrations/030_workspace_modules.sql`:

```sql
-- Per-workspace module toggles.
--
-- Absence of a row means "use the module's default_enabled", so this table
-- only ever records an explicit admin choice. New table, so nothing existing
-- is touched and rollback stays an image revert.
CREATE TABLE IF NOT EXISTS workspace_modules (
    team_id TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    module TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (team_id, module)
);

CREATE INDEX IF NOT EXISTS idx_workspace_modules_team ON workspace_modules(team_id);
```

- [ ] **Step 2: Write the failing test**

Create `app/tests/test_workspace_modules.py`:

```python
"""Per-workspace module toggles and the nav they drive."""

from __future__ import annotations

from unittest.mock import patch

from src.core.modules import ModuleSpec, NavItem, active_modules


def spec(name, scopes=(), default_enabled=True, nav=()):
    return ModuleSpec(
        name=name,
        required_scopes=scopes,
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=nav,
        default_enabled=default_enabled,
    )


REGISTRY = (
    spec("standup", nav=(NavItem("Standups", "/"),)),
    spec("connect", scopes=("mpim:write",), default_enabled=False, nav=(NavItem("Connect", "/m/connect/"),)),
)


def test_connect_is_hidden_without_the_scope():
    result = active_modules(REGISTRY, granted_scopes=set(), settings={"connect": True}, allowlist=None)
    assert [m.name for m in result] == ["standup"]


def test_connect_appears_once_the_scope_is_granted_and_it_is_enabled():
    result = active_modules(REGISTRY, granted_scopes={"mpim:write"}, settings={"connect": True}, allowlist=None)
    assert [m.name for m in result] == ["standup", "connect"]


def test_connect_stays_off_by_default_even_with_the_scope():
    result = active_modules(REGISTRY, granted_scopes={"mpim:write"}, settings={}, allowlist=None)
    assert [m.name for m in result] == ["standup"]


def test_nav_comes_from_active_modules_only():
    result = active_modules(REGISTRY, granted_scopes=set(), settings={}, allowlist=None)
    labels = [item.label for m in result for item in m.nav]
    assert labels == ["Standups"]


def test_module_settings_returns_explicit_rows_only():
    rows = [("connect", True), ("kudos", False)]
    with patch("src.core.db.db_conn"), patch("src.core.db._fetch_module_rows", return_value=rows):
        from src.core.db import module_settings

        assert module_settings("T1") == {"connect": True, "kudos": False}
```

- [ ] **Step 3: Run it to make sure it fails**

```bash
cd app && python -m pytest tests/test_workspace_modules.py -v
```

Expected: the last test FAILS with an import or attribute error for `_fetch_module_rows`.

- [ ] **Step 4: Write the db functions**

In `app/src/core/db.py`, replacing the Task 13 `module_settings` stub:

```python
def _fetch_module_rows(team_id: str):
    sql = "SELECT module, enabled FROM workspace_modules WHERE team_id = %s"
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id,))
            return cur.fetchall()


def module_settings(team_id: str) -> dict[str, bool]:
    """Explicit per-workspace toggles. Absent keys fall back to default_enabled."""
    return {module: enabled for module, enabled in _fetch_module_rows(team_id)}


def set_module_enabled(team_id: str, module: str, enabled: bool) -> None:
    """Record an explicit admin choice for one module."""
    sql = """
        INSERT INTO workspace_modules (team_id, module, enabled, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (team_id, module) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            updated_at = NOW()
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (team_id, module, enabled))
```

- [ ] **Step 5: Render nav from active modules and add the toggle endpoint**

In `app/src/core/dashboard.py`, build the nav from `active_modules(...)` rather than a hardcoded list, and add:

```python
@dashboard_bp.route("/api/modules/<name>", methods=["POST"])
@_admin_required
def api_set_module(name: str):
    """Enable or disable one module for this workspace."""
    team_id = session.get("team_id", "")
    spec = next((s for s in REGISTRY if s.name == name), None)
    if spec is None:
        return jsonify({"error": "unknown module"}), 404
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    if enabled and not db.has_scopes(team_id, spec.required_scopes):
        return jsonify({"error": "missing_scopes", "required": list(spec.required_scopes)}), 409
    db.set_module_enabled(team_id, name, enabled)
    return jsonify({"module": name, "enabled": enabled})
```

The 409 is what the enable card reacts to: a workspace that has not re-authorised gets the re-install link rather than a toggle that silently does nothing.

Add the card to the dashboard template, shown when a registered module declares scopes the workspace does not hold:

> **Enable Connect.** Connect needs a few extra Slack permissions to introduce
> people in a group DM. Re-authorise to turn it on. `[ Re-authorise ]`

The button links to the existing OAuth install route.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd app && python -m pytest tests/test_workspace_modules.py tests/test_dashboard.py tests/test_dashboard_template.py -v
```

Expected: all pass.

- [ ] **Step 7: Run the full suite and commit**

```bash
cd app && python -m pytest tests/ -q | tail -3
git add -A app
git commit -m "feat: per-workspace module toggles and the enable card

Absence of a workspace_modules row means the module's own default applies, so
the table only ever records an explicit admin choice. Enabling a module whose
scopes are not granted returns 409 rather than silently doing nothing, and
the dashboard card turns that into a re-authorise link.

Dashboard nav is now built from active modules instead of a hardcoded list."
```

**R4 ships here.** First user-visible change in this plan: an "Enable Connect" card for admins. Connect itself does not exist yet, so the card is the only difference. Deploy per the checklist in spec section 9.7.

---

## Phase 0 exit criteria

Status as executed on 2026-09-16, all 18 tasks complete on branch
`feat/module-contract-phase0`.

- [x] Full suite green: **626 passed**, up from a 530 baseline. ruff clean.
- [x] Both R2 moves verified mechanical **at the commit that made them**
      (`e5ecdb0` for the ten core files, `46de708` for the nine standup files).
      Note the criterion as originally written was wrong: re-running the check
      against today's tree reports differences, because R3 and R4 deliberately
      edited some of those files afterwards. The guarantee is per-move, not
      forever.
- [x] `main.py` names no feature module (0 occurrences of `src.modules.`).
- [x] Migration discovery finds 30 files across core and four modules, with
      the original 28 basenames unchanged, so nothing re-runs in production.
- [x] Image builds; `python src/migrate.py` and `python -m src.main` both
      resolve inside it; all 30 SQL files ship.
- [ ] **Not met: core no longer importing feature modules.** 14 dependencies
      remain, one of them a top-level import (`core/oauth.py:19` imports
      `standup.mailer.send_welcome_email`); the rest are lazy imports inside
      functions in `core/dashboard.py`, `core/scheduler.py` and `core/db.py`.
      Phase 0 moved the files but not all the responsibilities: core's
      dashboard still serves standup's schedule and workflow endpoints, and
      core's scheduler still runs standup's jobs. `test_main_wiring.py`
      ratchets the count so it cannot grow.
- [ ] Production verification (migration rows, `/healthz` continuity, manual
      standup trigger) pending deployment.

## Deviations from this plan, as executed

1. **Test updates were not mechanical.** Under the package layout a lazy
   `import src.core.db as db` binds from `getattr(src.core, "db")`, so the
   existing practice of faking a module by replacing its `sys.modules` entry
   stopped intercepting, silently. Tests began exercising the real database
   and failed on assertions, 90 of them at the worst point. `tests/support.py`
   adds `patch_modules`, which patches the entry and the parent attribute
   together. Four faking styles needed rewiring.
2. **`src/templates` had to move with `dashboard.py`**, since
   `template_folder="templates"` resolves against the blueprint's own
   directory.
3. **`schedule_validation` moved to core, not standup.** `core/dashboard.py`
   imports it, so leaving it in standup made core import a module and created
   an import cycle once a second module registered.
4. **Kudos owned dashboard endpoints too.** Moving only its db functions would
   have forced core to import a module, so `/dashboard/api/kudos` and its
   leaderboard moved into the module, keeping their paths.
5. **Task 16 did not repoint standup at the shared roster.** Standup's
   audience is a per-schedule participant list with vacation checked at send
   time (`scheduler.py:418`), which is a different question from "who in this
   workspace is contactable". Repointing it at `eligible_members(team_id)`
   would have changed a schedule's audience to all members.
6. **mcp is unconditional**, not gated on an `MCP_ENABLED` variable that does
   not exist, and google_chat's `GOOGLE_CREDENTIALS` check lives in
   `register_routes` rather than `default_enabled`, because route registration
   happens once at process start while `default_enabled` is resolved per
   workspace.

## Constraint inherited by the Connect plan

Standup's `@app.message` patterns stay as-is (decision recorded in Task 15). Connect must therefore not register any DM command containing the words **help**, **standup** or **skip**. Connect's opt-out is button-only, driven by the interactive elements on the intro message.

## Next plan

`docs/plans/2026-09-16-connect-pairing.md` covers R5 and R6: the Connect module itself. It is written after Phase 0 ships, because the matcher, jobs and dashboard pages are written against the module contract's real signatures rather than against the ones proposed here.
