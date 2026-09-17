"""Every ON CONFLICT target must have a constraint that can match it.

workspace_config.team_id never had one. upsert_workspace_config has always
written with ON CONFLICT (team_id) against a table whose only unique index was
the serial primary key, so Postgres raised "there is no unique or exclusion
constraint matching the ON CONFLICT specification" on every call and every
workspace-level setting was silently unwritable.

The whole test suite missed it because the tests that exercise those endpoints
mock src.core.db, so the SQL never reached a database. This reads the SQL and
the migrations as text instead: no database, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
SRC = APP / "src"

# INSERT INTO <table> ... ON CONFLICT (<cols>)
INSERT_TABLE = re.compile(r"INSERT\s+INTO\s+([a-z_]+)", re.I)
ON_CONFLICT = re.compile(r"ON\s+CONFLICT\s*\(([^)]*)\)", re.I)

# What the migrations declare: inline PRIMARY KEY / UNIQUE, table-level
# constraints, and CREATE UNIQUE INDEX.
TABLE_UNIQUE = re.compile(r"\bUNIQUE\s*\(([^)]*)\)", re.I)
TABLE_PK = re.compile(r"\bPRIMARY\s+KEY\s*\(([^)]*)\)", re.I)
UNIQUE_INDEX = re.compile(
    r"CREATE\s+UNIQUE\s+INDEX[^;]*?\bON\s+(?:public\.)?([a-z_]+)\s*(?:USING\s+\w+\s*)?\(([^)]*)\)", re.I
)
ADD_CONSTRAINT_UNIQUE = re.compile(
    r"ALTER\s+TABLE\s+(?:public\.)?([a-z_]+)[^;]*?ADD\s+CONSTRAINT\s+\w+\s+UNIQUE\s*\(([^)]*)\)", re.I | re.S
)
# A primary key added after the fact is just as valid an ON CONFLICT target,
# and migration 022 re-keys daily_standup_threads this way.
ADD_PRIMARY_KEY = re.compile(
    r"ALTER\s+TABLE\s+(?:public\.)?([a-z_]+)[^;]*?ADD\s+PRIMARY\s+KEY\s*\(([^)]*)\)", re.I | re.S
)
CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:public\.)?([a-z_]+)\s*\((.*?)\n\s*\);", re.I | re.S
)


def _cols(raw: str) -> frozenset[str]:
    return frozenset(c.strip().strip('"') for c in raw.split(",") if c.strip())


def migration_files() -> list[Path]:
    return sorted(SRC.rglob("migrations/*.sql"))


def declared_unique_sets() -> dict[str, set[frozenset[str]]]:
    """table -> the column sets Postgres can use as an ON CONFLICT target."""
    found: dict[str, set[frozenset[str]]] = {}

    def add(table: str, cols: frozenset[str]) -> None:
        if cols:
            found.setdefault(table, set()).add(cols)

    for path in migration_files():
        text = path.read_text()

        for table, body in CREATE_TABLE.findall(text):
            for line in body.splitlines():
                line = line.strip().rstrip(",")
                # "col TYPE PRIMARY KEY" / "col TYPE UNIQUE"
                inline = re.match(r"([a-z_]+)\s+[A-Za-z]+.*\b(PRIMARY\s+KEY|UNIQUE)\b", line, re.I)
                if inline and not line.upper().startswith(("PRIMARY", "UNIQUE", "CONSTRAINT")):
                    add(table, frozenset({inline.group(1)}))
            for raw in TABLE_UNIQUE.findall(body) + TABLE_PK.findall(body):
                add(table, _cols(raw))

        for table, raw in UNIQUE_INDEX.findall(text):
            add(table, _cols(raw))
        for table, raw in ADD_CONSTRAINT_UNIQUE.findall(text):
            add(table, _cols(raw))
        for table, raw in ADD_PRIMARY_KEY.findall(text):
            add(table, _cols(raw))

    return found


def upsert_targets() -> list[tuple[Path, int, str, frozenset[str]]]:
    """(file, line, table, conflict columns) for every ON CONFLICT (...) we write."""
    out = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text()
        for match in ON_CONFLICT.finditer(text):
            before = text[: match.start()]
            tables = INSERT_TABLE.findall(before)
            if not tables:
                continue
            out.append((path, before.count("\n") + 1, tables[-1].lower(), _cols(match.group(1))))
    return out


class TestOnConflictTargets:
    def test_migrations_declare_something_to_parse(self):
        assert migration_files(), "no migrations found, the other checks would pass vacuously"
        declared = declared_unique_sets()
        assert "workspace_config" in declared

    def test_every_on_conflict_has_a_matching_constraint(self):
        declared = declared_unique_sets()
        problems = []
        for path, line, table, cols in upsert_targets():
            if cols <= frozenset():
                continue
            if cols not in declared.get(table, set()):
                rel = path.relative_to(APP)
                problems.append(
                    f"{rel}:{line} ON CONFLICT {sorted(cols)} on {table}, which declares {sorted(map(sorted, declared.get(table, set())))}"
                )
        assert not problems, "ON CONFLICT with no constraint Postgres can match:\n  " + "\n  ".join(problems)

    def test_workspace_config_team_id_is_unique(self):
        # The specific gap, named so a future schema change cannot quietly
        # reintroduce it.
        assert frozenset({"team_id"}) in declared_unique_sets()["workspace_config"]
