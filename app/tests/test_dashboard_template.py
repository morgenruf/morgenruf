"""Invariants for templates/dashboard.html.

The template is one big file of markup plus inline JavaScript, so the checks
that matter are structural: no id used twice (#62), no connection string in a
page a browser downloads (#63), the responsive rules still present (#64), and
every getElementById target actually in the markup.

Reads the file as text. No database, no network.
"""

import os
import re
from collections import Counter

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "../src/templates/dashboard.html")

# An id built at runtime ("sc-' + s.id + '") is not a literal id, so only plain
# HTML id values count.
ID_LITERAL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

# "data-id=" must not be mistaken for "id=".
ID_ATTR = re.compile(r'(?<![-\w])id="([^"]*)"')

# Only straight-quoted literals. Template literals build ids at runtime.
GET_BY_ID = re.compile(r"getElementById\(\s*'([A-Za-z][A-Za-z0-9_-]*)'\s*\)")


def read_template() -> str:
    with open(TEMPLATE_PATH, encoding="utf-8") as fh:
        return fh.read()


def literal_ids(markup: str) -> list[str]:
    return [value for value in ID_ATTR.findall(markup) if ID_LITERAL.match(value)]


class TestElementIds:
    def test_no_duplicate_ids(self):
        """#62: two elements sharing an id makes getElementById pick the wrong one."""
        counts = Counter(literal_ids(read_template()))
        duplicates = sorted(name for name, seen in counts.items() if seen > 1)
        assert duplicates == [], f"duplicate element ids: {duplicates}"

    def test_ids_are_found(self):
        """A guard on the parsing itself, so an empty match set cannot pass the suite."""
        assert len(literal_ids(read_template())) > 50

    def test_every_get_element_by_id_target_exists(self):
        markup = read_template()
        present = set(literal_ids(markup))
        wanted = set(GET_BY_ID.findall(markup))
        missing = sorted(wanted - present)
        assert missing == [], f"getElementById targets with no matching id: {missing}"


class TestNoDatabaseCredentials:
    def test_no_postgres_url(self):
        """#63: the dashboard is served to browsers, so a connection string leaks."""
        assert "postgresql://" not in read_template()

    def test_no_database_url_literal(self):
        assert "DATABASE_URL" not in read_template()


class TestResponsive:
    def test_has_media_queries(self):
        """#64: the layout has to survive a narrow viewport."""
        assert len(re.findall(r"@media", read_template())) >= 1
