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


# Classes that carry no styling of their own because the element is already
# covered by a bare element selector (`input, select, textarea { ... }` and
# `label { ... }` near the top of the stylesheet). They are naming hooks, not
# broken references, so the check would only produce noise. Justify additions.
CLASS_IGNORE = frozenset(
    {
        "form-input",  # on <input>/<select>, styled by the element selector
        "form-label",  # on <label>, styled by the element selector
        "input",  # same, an older spelling still in the automation modal
        "question-input",  # on <input>
    }
)

# Only classes written literally in markup. A value containing a quote, brace or
# operator is a className assembled in JavaScript and cannot be checked from
# static text.
CLASS_ATTR = re.compile('class="([A-Za-z0-9 _-]*)"')

# A base rule: the selector is followed by "{" or ",". Deliberately NOT matched
# by ".foo:hover" alone. The equivalent guard on the marketing site originally
# passed with its bug reintroduced, because ".btn-green:hover" was still present
# and a naive grep counted it as a definition.
CLASS_RULE = re.compile(r"\.([A-Za-z][A-Za-z0-9_-]*)\s*[,{]")


def markup_classes(markup: str) -> set[str]:
    names: set[str] = set()
    for value in CLASS_ATTR.findall(markup):
        names.update(token for token in value.split() if token)
    return names


def defined_classes(markup: str) -> set[str]:
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", markup, re.S))
    return set(CLASS_RULE.findall(style))


class TestClassesAreStyled:
    """#83: `class="modal-box"` had no rule, so that dialog rendered unstyled.

    Same failure as morgenruf/website#1, where both primary calls to action
    rendered as bare text because `.btn-green` was used and never defined.
    Twice in one codebase is enough to justify a guard.
    """

    def test_every_class_in_markup_has_a_base_rule(self):
        markup = read_template()
        used = markup_classes(markup) - CLASS_IGNORE
        missing = sorted(used - defined_classes(markup))
        assert not missing, f"classes used in markup with no CSS rule: {missing}"

    def test_a_pseudo_class_alone_does_not_count_as_defined(self):
        """Guard the guard: the naive version of this check passed with the bug in."""
        fake = '<style>.ghost:hover { color: red; }</style><div class="ghost"></div>'
        assert "ghost" in markup_classes(fake)
        assert "ghost" not in defined_classes(fake)

    def test_a_base_rule_does_count(self):
        fake = '<style>.solid { color: red; }</style><div class="solid"></div>'
        assert "solid" in defined_classes(fake)

    def test_a_rule_in_a_selector_list_counts(self):
        fake = '<style>.a, .b { color: red; }</style><div class="b"></div>'
        assert defined_classes(fake) >= {"a", "b"}
