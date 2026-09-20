"""Everything Connect stores has to be reachable from somewhere.

This session added four tables and several columns and then shipped none of
them to any surface, which is the same defect the settings audit had just
finished fixing: storage that works, writes that land, and nothing that ever
shows it. This file is the guard against doing it a third time.
"""

from __future__ import annotations

import pathlib
import re

APP = pathlib.Path(__file__).resolve().parent.parent
CONNECT = APP / "src/modules/connect"


def api_source() -> str:
    return (CONNECT / "dashboard.py").read_text()


class TestAgreedTimesAreVisible:
    """Agreeing a time is the step between an introduction and a meeting."""

    def test_the_api_returns_it(self):
        assert "agreed_at" in api_source()

    def test_the_round_query_counts_them(self):
        sql = (CONNECT / "db.py").read_text()
        assert "agreed_slot_utc IS NOT NULL) AS agreed" in sql


class TestZoomIsVisibleAndRevocable:
    def test_there_is_an_endpoint_for_the_summary(self):
        assert "/dashboard/api/connect/zoom" in api_source()

    def test_it_distinguishes_unconfigured_from_nobody_connected(self):
        # Different problems with different fixes: one needs credentials, the
        # other needs people to press a button.
        src = api_source()
        assert '"configured": False' in src
        assert "needs_reconnect" in src

    def test_a_person_can_disconnect_their_own_account(self):
        """The one that matters: connecting must be undoable by the person who
        did it, without an admin."""
        home = (CONNECT / "home.py").read_text()
        handlers = (CONNECT / "handlers.py").read_text()
        assert "connect:zoom_unlink" in home
        assert "connect:zoom_unlink" in handlers
        assert "revoke_zoom_link" in handlers

    def test_the_zoom_section_is_actually_called_not_merely_defined(self):
        """A defined-but-uncalled block function is the same as no block.

        Removing the call while leaving the function passed an earlier version
        of these tests, which is exactly the shape of bug they exist to catch.
        """
        home = (CONNECT / "home.py").read_text()
        body = home[home.index("def home_blocks") : home.index("def _zoom_blocks")]
        assert "_zoom_blocks(" in body, "home_blocks never calls _zoom_blocks"

    def test_the_disconnect_button_is_wired(self):
        import importlib.util

        registered = []

        class FakeApp:
            def action(self, pattern):
                registered.append(pattern)
                return lambda f: f

            def __getattr__(self, _):
                return lambda *a, **k: lambda f: f

        spec = importlib.util.spec_from_file_location("probe_unlink", CONNECT / "handlers.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.register_handlers(FakeApp())
        literals = [p for p in registered if not hasattr(p, "match")]
        assert "connect:zoom_unlink" in literals


class TestRematchRequestsAreVisible:
    def test_the_round_query_counts_them(self):
        assert "connect_rematch_requests q WHERE q.round_id" in (CONNECT / "db.py").read_text()


class TestNoNewStorageIsOrphaned:
    """A table nothing can reach is a feature nobody has.

    Table names belong in SQL only, so the check is not "does the name appear
    elsewhere" but "does anything call the functions that read it". Adding a
    table plus accessors and then never wiring them up fails here.
    """

    TABLES = [
        "connect_zoom_links",
        "connect_rematch_requests",
        "connect_slot_votes",
    ]

    def _db_functions_touching(self, table: str) -> set[str]:
        """Names of db.py functions whose body mentions the table."""
        src = (CONNECT / "db.py").read_text()
        found = set()
        # Split on top-level defs and keep those whose body names the table.
        parts = re.split(r"\ndef ", src)
        for part in parts[1:]:
            name = part.split("(", 1)[0].strip()
            body = part
            if table in body:
                found.add(name)
        return found

    def _callers_outside_db(self, names: set[str]) -> dict[str, list[str]]:
        callers: dict[str, list[str]] = {n: [] for n in names}
        targets = [p for p in CONNECT.rglob("*.py") if p.name != "db.py"]
        targets += [APP / "src/core/scheduler.py"]
        for path in targets:
            text = path.read_text()
            for n in names:
                if re.search(rf"\b{re.escape(n)}\s*\(", text):
                    callers[n].append(path.name)
        return callers

    def test_every_table_is_reachable_from_outside_the_db_layer(self):
        unreachable = []
        for table in self.TABLES:
            funcs = self._db_functions_touching(table)
            assert funcs, f"no db function reads {table}"
            callers = self._callers_outside_db(funcs)
            if not any(callers.values()):
                unreachable.append(f"{table} (accessors: {sorted(funcs)})")
        assert not unreachable, "tables nothing outside db.py can reach: " + "; ".join(unreachable)

    def test_the_columns_surface_by_name_in_the_api_or_page(self):
        # These do travel by name, in API payloads and in the markup.
        for column in ("agreed_slot_utc", "zoom_join_url"):
            hits = [
                path.name for path in list(CONNECT.rglob("*.py")) if path.name != "db.py" and column in path.read_text()
            ]
            assert hits, f"{column} is stored and never read"

    def test_migration_numbers_do_not_collide(self):
        nums = sorted(
            int(re.match(r"(\d+)", p.name).group(1))
            for p in (CONNECT / "migrations").glob("*.sql")
            if re.match(r"\d+", p.name)
        )
        assert nums == sorted(set(nums)), "duplicate migration numbers"


class TestNoColumnIsWrittenAndNeverRead:
    """Every column the settings page can write must change something.

    video_mode shipped as a control that saved and did nothing, and
    include_guests as a column with no feature at all. Both were mine, added
    an hour after the audit that removed the same defect from standups, and
    neither was caught by a test. Naming the columns individually did not
    scale; this reads the write allowlist itself.
    """

    # Columns whose only job is to be stored and handed back. Each needs a
    # reason, so the list cannot quietly absorb a mistake.
    PASSTHROUGH = {
        "name",  # shown on the card and in the settings form
        "channel_id",  # the programme's identity, used everywhere
        "enabled",  # read by the scheduler and the card
    }

    def _write_allowlist(self) -> set[str]:
        import re

        src = (CONNECT / "db.py").read_text()
        block = src[src.index("def update_program") :]
        block = block[block.index("allowed = {") : block.index("}", block.index("allowed = {"))]
        return set(re.findall(r'"(\w+)"', block))

    def _read_outside_db(self, column: str) -> list[str]:
        """Python that acts on the column.

        The template is deliberately excluded. A field that the page sends and
        reads back is the write side, not a consumer, and counting it made the
        first version of this test pass while video_mode did nothing: it
        appeared in dashboard.html on both the save and the load.
        """
        hits = []
        for path in list(CONNECT.rglob("*.py")) + [APP / "src/core/scheduler.py"]:
            if path.name in {"db.py", "schemas.py"} or path.parts[-2] == "tests":
                continue
            if column in path.read_text():
                hits.append(path.name)
        return hits

    def test_every_writable_column_is_read_somewhere(self):
        orphans = []
        for column in sorted(self._write_allowlist() - self.PASSTHROUGH):
            if not self._read_outside_db(column):
                orphans.append(column)
        assert not orphans, (
            "settings the page can write that nothing acts on, so they save "
            f"and report success while doing nothing: {orphans}"
        )

    def test_the_check_would_notice_a_new_column(self):
        # Guard against the guard silently passing because the allowlist could
        # not be parsed.
        allowlist = self._write_allowlist()
        assert "group_size" in allowlist and "video_mode" in allowlist
        assert len(allowlist) > 10
