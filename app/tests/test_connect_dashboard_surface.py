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
TEMPLATE = APP / "src/core/templates/dashboard.html"
CONNECT = APP / "src/modules/connect"


def template() -> str:
    return TEMPLATE.read_text()


def api_source() -> str:
    return (CONNECT / "dashboard.py").read_text()


class TestAgreedTimesAreVisible:
    """Agreeing a time is the step between an introduction and a meeting."""

    def test_the_api_returns_it(self):
        assert "agreed_at" in api_source()

    def test_a_pairing_shows_the_time_it_settled_on(self):
        assert "m.agreed_at" in template()

    def test_the_headline_counts_them(self):
        markup = template()
        assert "agreed a time" in markup
        assert "acc.agreed" in markup

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

    def test_the_page_reads_it(self):
        markup = template()
        assert "'/connect/zoom'" in markup
        assert "zoomStatusRow" in markup

    def test_nothing_is_shown_when_zoom_is_not_configured(self):
        markup = template()
        row = markup[markup.index("function zoomStatusRow") :][:600]
        assert "!z.configured" in row

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

    def test_the_round_row_shows_them(self):
        assert "asked for a new match" in template()


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
        targets += [TEMPLATE, APP / "src/core/scheduler.py"]
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
                path.name
                for path in list(CONNECT.rglob("*.py")) + [TEMPLATE]
                if path.name != "db.py" and column in path.read_text()
            ]
            assert hits, f"{column} is stored and never read"

    def test_migration_numbers_do_not_collide(self):
        nums = sorted(
            int(re.match(r"(\d+)", p.name).group(1))
            for p in (CONNECT / "migrations").glob("*.sql")
            if re.match(r"\d+", p.name)
        )
        assert nums == sorted(set(nums)), "duplicate migration numbers"
