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


# ---------------------------------------------------------------------------
# Visual rules that are easy to regress and hard to notice in review
# ---------------------------------------------------------------------------

EMOJI = re.compile("[\U0001f000-\U0001faff]")

# Emoji also hide as numeric character references, which are plain ASCII in the
# source. Checking only for literal characters passed while the sidebar, the MCP
# title and four copy buttons were still drawing emoji in the browser.
ENTITY = re.compile(r"&#(\d+);|&#x([0-9a-fA-F]+);")

# Geometric glyphs that render as monochrome text on every platform and are
# conventional interface furniture rather than emoji.
TEXT_GLYPHS = {0x2630, 0x2715, 0x2713, 0x2605, 0x2606, 0x26A0, 0x2699, 0x25B8, 0x25AA}


def pictographic_entities(markup: str) -> list[str]:
    found = []
    for match in ENTITY.finditer(markup):
        point = int(match.group(1)) if match.group(1) else int(match.group(2), 16)
        if point in TEXT_GLYPHS:
            continue
        if 0x1F000 <= point <= 0x1FAFF or 0x2600 <= point <= 0x27BF:
            found.append(f"{match.group(0)} ({chr(point)})")
    return found


def palette(markup: str) -> dict[str, str]:
    root = re.search(r":root \{(.*?)\n    \}", markup, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", root))


def luminance(value: str) -> float:
    channels = [int(value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(foreground: str, background: str) -> float:
    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestNoEmojiAsIcons:
    """Emoji render differently on every platform, cannot take the colour of the
    control they sit in, and read as a placeholder. The dashboard used them for
    the whole sidebar, several page titles and the kudos leaderboard.
    """

    def test_the_template_carries_no_emoji(self):
        found = sorted(set(EMOJI.findall(read_template())))
        assert not found, f"emoji in the template: {found}"

    def test_no_emoji_hiding_as_a_character_reference(self):
        """&#128268; is ASCII in the source and an emoji in the browser."""
        found = sorted(set(pictographic_entities(read_template())))
        assert not found, f"emoji written as entities: {found}"

    def test_the_entity_check_is_actually_matching_something(self):
        """A guard on the parser, so a broken regex cannot pass by finding nothing."""
        assert pictographic_entities("&#128268; and &#127942;")

    def test_the_sidebar_uses_the_icon_set(self):
        markup = read_template()
        assert markup.count('use href="#i-') >= 9
        assert '<span class="nav-icon">' not in markup

    def test_every_icon_referenced_is_defined(self):
        markup = read_template()
        defined = set(re.findall(r'<symbol id="(i-[\w-]+)"', markup))
        used = set(re.findall(r'use href="#(i-[\w-]+)"', markup))
        assert used <= defined, f"referenced but not defined: {sorted(used - defined)}"

    def test_no_symbol_is_defined_and_never_used(self):
        markup = read_template()
        defined = set(re.findall(r'<symbol id="(i-[\w-]+)"', markup))
        used = set(re.findall(r'use href="#(i-[\w-]+)"', markup))
        assert defined <= used, f"defined but unused: {sorted(defined - used)}"


class TestContrast:
    """WCAG AA. Checked here because a palette change is exactly the kind of edit
    that looks fine to whoever made it and fails for everyone else.
    """

    PAIRS = [
        ("text", "bg", 4.5),
        ("text", "surface", 4.5),
        ("text", "surface2", 4.5),
        ("text-muted", "bg", 4.5),
        ("text-muted", "surface", 4.5),
        ("text-dim", "surface", 3.0),
        ("panel-text", "panel", 4.5),
        ("panel-weak", "panel", 3.0),
        ("accent", "surface", 3.0),
        ("danger", "surface", 3.0),
        ("warning", "surface", 3.0),
        ("sev-good", "panel", 3.0),
        ("sev-warn", "panel", 3.0),
        ("sev-mid", "panel", 3.0),
        ("sev-bad", "panel", 3.0),
        ("sev-info", "panel", 3.0),
    ]

    def test_every_text_and_surface_pair_meets_aa(self):
        tokens = palette(read_template())
        failures = []
        for foreground, background, required in self.PAIRS:
            assert foreground in tokens, f"--{foreground} is not defined"
            assert background in tokens, f"--{background} is not defined"
            actual = contrast(tokens[foreground], tokens[background])
            if actual < required:
                failures.append(f"--{foreground} on --{background}: {actual:.2f}:1 < {required}")
        assert not failures, "; ".join(failures)

    def test_the_palette_is_actually_being_read(self):
        """A guard on the parsing, so an empty token map cannot pass the checks."""
        assert len(palette(read_template())) > 15

    def test_green_and_red_differ_by_more_than_hue(self):
        """A share of readers cannot separate those two by colour alone."""
        tokens = palette(read_template())
        assert abs(luminance(tokens["sev-good"]) - luminance(tokens["sev-bad"])) > 0.05
