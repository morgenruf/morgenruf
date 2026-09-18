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

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "../src/core/templates/dashboard.html")

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
        # Some are referenced by building the href, e.g. "'#i-' + MODULE_ICON[m]",
        # so the bare id appearing in a JS string counts as a use. Without this
        # the check would push people towards literal duplication to satisfy it.
        dynamic = {sid for sid in defined - used if re.search(r"['\"]" + re.escape(sid[2:]) + r"['\"]", markup)}
        assert defined <= (used | dynamic), f"defined but unused: {sorted(defined - used - dynamic)}"


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
        # 4.5, not 3.0. This token is used for stat-sub and page-subtitle,
        # which are sentences someone reads, not hints. At 3.0 the guard passed
        # while the dark theme rendered them at 3.71 and they were hard to read.
        ("text-dim", "surface", 4.5),
        ("text-dim", "bg", 4.5),
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


class TestMCPEndpointFollowsDeployment:
    """The MCP setup panel must point at this deployment, not the hosted one.

    Every URL in the panel was the literal https://api.morgenruf.dev/mcp, so a
    self-hosted install handed its users a config pointing at our SaaS, where
    their key would not work and their data is not.
    """

    def test_no_hardcoded_hosted_endpoint(self):
        assert "api.morgenruf.dev/mcp" not in read_template()

    def test_the_panel_uses_the_injected_endpoint(self):
        markup = read_template()
        # Every place that showed a URL: the four config snippets, the curl
        # example, the page subtitle, and the generator's constant.
        assert markup.count("{{ mcp_endpoint }}") >= 6

    def test_the_tool_count_is_not_hardcoded(self):
        # The list is gated per workspace, so a fixed number is wrong as soon
        # as a module is enabled.
        assert "8 Tools" not in read_template()


class TestWebhookEventPicker:
    """Webhooks could only ever fire standup.completed.

    The backend has three events, POST and PATCH both accept an events list,
    and /webhooks/events exists to enumerate them. The UI created webhooks
    with a URL only, never showed which events a webhook was on, and never
    called that endpoint, so blocker.detected and participation.low were
    unreachable from the dashboard.
    """

    def test_the_event_catalog_is_fetched(self):
        assert "'/webhooks/events'" in read_template()

    def test_create_sends_the_chosen_events(self):
        markup = read_template()
        assert "readEventPicker('wh-new')" in markup
        assert "{ url, events }" in markup

    def test_events_can_be_changed_on_an_existing_webhook(self):
        markup = read_template()
        assert "saveWebhookEvents" in markup
        assert "apiSoft('PATCH', '/webhooks/' + id, { events })" in markup

    def test_the_event_names_are_not_hardcoded_in_the_picker(self):
        # The labels are cosmetic, but the list itself must come from the
        # server or a new event will not appear without a frontend change.
        markup = read_template()
        picker = markup[markup.index("function eventCheckboxes") : markup.index("function readEventPicker")]
        assert "webhookEventCatalog" in picker
        assert "standup.completed" not in picker


class TestCoffeeChatCard:
    """The Coffee chats page presented a programme as one flex row of eleven
    metadata spans with no separators and five equal-weight buttons.

    It read as a run-on and wrapped mid-phrase ("15" then "min Active"), and
    Delete sat at the same weight as Settings.
    """

    def test_the_channel_is_the_card_title(self):
        markup = read_template()
        card = markup[markup.index("function ccCard") : markup.index("function ccCloseMenus")]
        assert "cc-title" in card
        assert "connectChannelName" in card

    def test_metadata_is_joined_with_separators(self):
        card = read_template()
        block = card[card.index("function ccCard") : card.index("function ccCloseMenus")]
        # A real middot between items, so a wrap cannot split a phrase silently.
        assert "\\u00b7" in block

    def test_destructive_actions_are_behind_a_menu(self):
        markup = read_template()
        block = markup[markup.index("function ccCard") : markup.index("function ccCloseMenus")]
        # Settings stays on the card; Delete and Run now move into the overflow.
        assert "openConnectSettings" in block
        assert "cc-menu" in block
        assert 'class="danger"' in block

    def test_the_old_five_button_row_is_gone(self):
        markup = read_template()
        assert "standup-actions" not in markup[markup.index("function ccCard") :][:4000]


class TestAttendancePanelHonesty:
    """The attendance panel drew a chart and a pattern column with no data.

    Two identical grey bars, both labelled the same date, under a four-colour
    legend where only grey appeared; an identical flat bar for every person;
    and a Met of 0 painted green, which reads as a good number.
    """

    def test_the_chart_only_renders_when_it_could_show_a_difference(self):
        markup = read_template()
        assert "chartWorthIt" in markup
        assert "a.rounds.length > 1 && answered > 0" in markup

    def test_the_pattern_column_is_conditional(self):
        markup = read_template()
        block = markup[markup.index("function peopleTable") : markup.index("function peopleTable") + 2200]
        assert "hasOutcomes" in block
        assert "hasOutcomes ? '<th>Pattern</th>' : ''" in block

    def test_a_zero_is_not_coloured_as_a_good_number(self):
        markup = read_template()
        block = markup[markup.index("function peopleTable") : markup.index("function peopleTable") + 2200]
        assert "n === 0" in block
        assert "var(--text-dim)" in block

    def test_same_day_rounds_are_distinguishable(self):
        markup = read_template()
        block = markup[markup.index("function roundRow") : markup.index("function roundRow") + 1200]
        assert "sameDay" in block
        assert "formatDateTime" in block

    def test_no_stray_dash_headline_when_nothing_is_answered(self):
        # The panel used to lead with a bare em dash as the stat value, which
        # read as a rendering fault rather than "no data".
        markup = read_template()
        assert "No outcomes yet, " in markup


class TestCoffeeChatNavGroup:
    """Coffee chats is three places, so it is a group rather than a row.

    The .nav-sub and .nav-group styles had existed unused since the sidebar was
    grouped; this is what they were for.
    """

    def test_it_is_a_group_with_three_children(self):
        markup = read_template()
        assert 'id="nav-group-connect"' in markup
        assert markup.count("data-connect-sub=") == 3

    def test_children_do_not_carry_the_section(self):
        """switchSection marks every element carrying the section as active,
        which lit all three children at once."""
        markup = read_template()
        group = markup[markup.index('id="nav-group-connect"') :][:1400]
        sub = group[group.index('class="nav-sub"') :]
        assert 'data-section="connect"' not in sub

    def test_switch_section_re_marks_the_group(self):
        # It clears every nav item, sub-items included, so the current place
        # has to be restored or a fresh load shows none of them selected.
        markup = read_template()
        assert "el.dataset.connectSub === 'list'" in markup

    def test_the_caret_collapses_without_navigating(self):
        markup = read_template()
        fn = markup[markup.index("function toggleNavGroup") :][:400]
        assert "stopPropagation" in fn

    def test_the_chevron_icon_is_defined(self):
        # A <use> pointing at a symbol that does not exist renders nothing.
        markup = read_template()
        assert 'symbol id="i-chevron"' in markup


class TestMemberStatusRespectsRole:
    def test_a_non_admin_gets_a_label_not_a_control(self):
        """The endpoint refuses anyone who does not run coffee chats, so
        offering everyone a dropdown means a 403 that looks like a broken
        page."""
        markup = read_template()
        fn = markup[markup.index("function memberStateControl") :][:900]
        assert "!canAdminister('connect')" in fn
        assert "att-zero" in fn

    def test_and_the_page_says_why_it_is_read_only(self):
        assert "Only someone who runs coffee chats can change these." in read_template()

    def test_the_check_matches_what_the_api_allows(self):
        """A workspace admin or whoever holds the feature, and nobody else."""
        markup = read_template()
        fn = markup[markup.index("function canAdminister") :][:400]
        assert "window._myRole === 'admin'" in fn
        assert "_myModuleAdmin" in fn


class TestIconsAreOfficialAndMeaningful:
    """Icons come from Lucide, and each one means the row it sits on.

    The set was already Lucide; the mistake was reusing whichever symbol
    existed. "How they meet" is a video call and had an eye on it.
    """

    def test_the_icons_used_are_all_defined(self):
        import re

        markup = read_template()
        used = set(re.findall(r'href="#(i-[a-z-]+)"', markup))
        defined = set(re.findall(r'<symbol id="(i-[a-z-]+)"', markup))
        missing = sorted(used - defined)
        assert not missing, f"referenced but never defined, so they render nothing: {missing}"

    def test_no_symbol_is_defined_twice(self):
        import re
        from collections import Counter

        counts = Counter(re.findall(r'<symbol id="(i-[a-z-]+)"', read_template()))
        dupes = [k for k, n in counts.items() if n > 1]
        assert not dupes, f"a duplicate symbol id makes the later one unreachable: {dupes}"

    def test_the_meeting_row_uses_a_video_icon_not_an_eye(self):
        markup = read_template()
        row = markup[markup.index('<div class="set-label">How they meet') - 300 :]
        head = row[: row.index("How they meet")]
        assert "#i-video" in head
        assert "#i-eye" not in head

    def test_the_group_size_row_uses_the_users_icon(self):
        markup = read_template()
        row = markup[markup.index("How many people in each group") - 300 :]
        assert "#i-users" in row[: row.index("How many people in each group")]

    def test_the_chevron_is_the_official_one(self):
        # Lucide's chevron-down is a path, not the polyline I first drew.
        markup = read_template()
        sym = markup[markup.index('<symbol id="i-chevron"') :][:220]
        assert "polyline" not in sym


class TestCheckboxesAreNotTextFields:
    """A checkbox must not inherit the text-field rule.

    `input, select, textarea` sets width:100% and 8px of padding, so every
    checkbox rendered about 190px wide and pushed its own label out of the
    row. It affected every checkbox in the settings rows, not only the new
    ones, and it read as a layout bug rather than a styling one.
    """

    def test_checkboxes_and_radios_are_excluded(self):
        css = read_template()
        rule = css[css.index('input[type="checkbox"], input[type="radio"]') :][:320]
        assert "width: auto" in rule
        assert "padding: 0" in rule

    def test_the_exclusion_comes_after_the_rule_it_undoes(self):
        # Same specificity would let source order decide, so the override has
        # to be the later of the two.
        css = read_template()
        assert css.index("input, select, textarea {") < css.index('input[type="checkbox"], input[type="radio"]')


class TestNoDuplicateFunctionDefinitions:
    """Two functions with the same name silently shadow each other.

    A second sparkline() was added beside the one that already existed, and
    which of the two ran depended on source order. The chart rendered in the
    other one's colour and nothing said why. The same mistake had already been
    made with the .pick cards and the Slack preview, both of which existed
    unused.
    """

    def test_no_top_level_function_is_declared_twice(self):
        import re
        from collections import Counter

        markup = read_template()
        # Two-space indent is the file's top level inside <script>.
        names = re.findall(r"^  (?:async )?function ([A-Za-z_]\w*)\s*\(", markup, re.M)
        dupes = sorted({n for n, c in Counter(names).items() if c > 1})
        assert not dupes, f"declared more than once, so one silently wins: {dupes}"

    def test_the_scan_sees_the_real_functions(self):
        import re

        names = re.findall(r"^  (?:async )?function ([A-Za-z_]\w*)\s*\(", read_template(), re.M)
        assert "sparkline" in names and len(names) > 40


class TestTheFontStackMatchesWhatIsLoaded:
    """The page asked for Inter and downloaded IBM Plex Sans.

    Neither the designer nor the browser got what they wanted: every screen
    rendered in the system fallback while a webfont was fetched and never
    referenced.
    """

    def _families(self, markup):
        import re

        return {f.replace("+", " ") for f in re.findall(r"family=([A-Za-z+]+)", markup)}

    def test_the_first_declared_family_is_actually_fetched(self):
        import re

        markup = read_template()
        stack = re.search(r"--sans:\s*'([^']+)'", markup)
        assert stack, "no --sans declared"
        assert stack.group(1) in self._families(markup), (
            f"--sans asks for {stack.group(1)!r} which is never loaded, so the page renders in the system fallback"
        )

    def test_no_family_is_downloaded_and_never_used(self):
        markup = read_template()
        for family in self._families(markup):
            assert family in markup.split("<style>", 1)[1], f"{family} is fetched but never referenced in CSS"


class TestNoDeadCss:
    """A class defined and never used is a component nobody can see.

    An audit found twenty such rules, two of them written the same day they
    were orphaned: .cc-preview was replaced by .slack-preview an hour later,
    and .mascot-sm was built beside .mascot and never applied.
    """

    # Classes applied only from Python, from a library, or as a state hook.
    ALLOWED_UNUSED = {
        "section",  # toggled by switchSection
        "active",
        "on",
        "open",
        "hidden",
        "soon",
        "danger",
    }

    def _defined(self, css):
        import re

        return {m.group(1) for m in re.finditer(r"^\s*\.([a-z][a-z0-9-]*)(?:[,:\s{])", css, re.M)}

    def test_every_defined_class_is_used_somewhere(self):
        markup = read_template()
        css = markup[markup.index("<style>") : markup.index("</style>")]
        body = markup[markup.index("</style>") :]
        unused = sorted(c for c in self._defined(css) - self.ALLOWED_UNUSED if c not in body)
        assert not unused, f"defined and never used, so invisible: {unused}"

    def test_the_scan_sees_real_classes(self):
        markup = read_template()
        css = markup[markup.index("<style>") : markup.index("</style>")]
        found = self._defined(css)
        assert "stat-card" in found and len(found) > 100


class TestAdminOnlyControlsAreNotOfferedToEveryone:
    """A control that answers 403 reads as a broken page.

    This was fixed for the coffee-chat members table and then repeated hours
    later on the Settings module switches, so it is asserted for both.
    """

    def test_module_switches_are_read_only_for_a_member(self):
        markup = read_template()
        fn = markup[markup.index("async function loadModuleSettings") :][:3000]
        assert "window._myRole !== 'admin'" in fn

    def test_member_status_control_is_read_only_for_a_member(self):
        markup = read_template()
        fn = markup[markup.index("function memberStateControl") :][:900]
        assert "!canAdminister('connect')" in fn

    def test_both_say_why_rather_than_silently_hiding_it(self):
        markup = read_template()
        assert "Only an admin can change these." in markup  # the feature switches
        assert "Only someone who runs coffee chats can change these." in markup


class TestEveryPageCarriesItsMark:
    """The sidebar had a mark per page and the page itself had none.

    A <use> pointing at a symbol that does not exist renders as nothing, and
    nothing is exactly what a missing icon looks like, so it goes unnoticed.
    """

    def _markup(self):
        return read_template()

    def test_every_page_title_has_one(self):
        markup = self._markup()
        titles = re.findall(r'<div class="page-title"[^>]*>([^<]+)</div>', markup)
        heads = markup.count('class="page-head"')
        assert heads == len(titles), f"{len(titles)} page titles, {heads} with a mark"
        assert heads >= 12

    def test_every_icon_reference_resolves(self):
        markup = self._markup()
        defined = set(re.findall(r'<symbol id="(i-[a-z0-9-]+)"', markup))
        used = set(re.findall(r'<use href="#(i-[a-z0-9-]+)"', markup))
        missing = sorted(used - defined)
        assert not missing, f"icons referenced but never drawn: {missing}"

    def test_the_greeting_keeps_its_mark(self):
        # today-greeting is rewritten with textContent, which would wipe an
        # icon nested inside it.
        markup = self._markup()
        head = markup[markup.index('id="section-today"') :][:600]
        assert 'class="title-ico"' in head
        assert '<div class="page-title" id="today-greeting">' in head

    def test_the_grant_chips_show_the_feature_not_a_dot(self):
        markup = self._markup()
        fn = markup[markup.index("function grantsHtml") :][:1600]
        assert "grant-ico" in fn
        assert "MODULE_ICON[name]" in fn


class TestAnOverdueCoffeeChatSaysSo:
    """A past date under "Next coffee chat" reads as a forecast."""

    def _fn(self):
        markup = read_template()
        return markup[markup.index("function todayNextChat") :][:1400]

    def test_the_card_changes_its_title(self):
        fn = self._fn()
        assert "Coffee chat overdue" in fn
        assert "next.overdue" in fn

    def test_it_says_the_round_did_not_run(self):
        assert "and has not run" in self._fn()

    def test_a_future_round_says_how_far_off_it_is(self):
        fn = self._fn()
        assert "Today" in fn and "Tomorrow" in fn and "In ' + away + ' days" in fn


class TestNoBlockSwallowsAnother:
    """One missing </div> put the standup modal inside a hidden one.

    The coffee chat settings modal never closed its body, so everything after
    it in the file (the create/edit standup modal, the new coffee chat modal
    and the toast container, 48 elements) became its children. Its parent is
    display:none until opened, so editing a standup opened a modal nobody
    could see, creating one did nothing, and no toast ever appeared. Nothing
    threw: the browser nests happily and the page looks fine until you press
    something.
    """

    def _top_level_blocks(self, markup: str):
        """Walk the body, returning (id, depth) for every element with an id."""
        body = markup[markup.index("<body") :]
        body = body[: body.index("</body>")]
        out, depth = [], 0
        for token in re.finditer(r"<div\b[^>]*>|</div>", body):
            text = token.group(0)
            if text == "</div>":
                depth -= 1
                continue
            found = re.search(r'id="([^"]+)"', text)
            if found:
                out.append((found.group(1), depth))
            if not text.rstrip().endswith("/>"):
                depth += 1
        return out, depth

    def test_every_modal_is_a_top_level_element(self):
        markup = read_template()
        blocks, _ = self._top_level_blocks(markup)
        modals = {"invite-modal", "mcp-key-modal", "cc-settings-modal", "connect-modal", "standup-modal"}
        nested = [(i, d) for i, d in blocks if i in modals and d != 0]
        assert not nested, f"modals nested inside another element: {nested}"

    def test_the_toast_container_is_not_inside_a_modal(self):
        markup = read_template()
        blocks, _ = self._top_level_blocks(markup)
        depth = dict(blocks).get("toast-container")
        assert depth == 0, f"toast-container sits at depth {depth}; a hidden parent hides every toast"

    def test_the_body_balances(self):
        markup = read_template()
        _, leftover = self._top_level_blocks(markup)
        assert leftover == 0, f"{leftover} unclosed <div> in the page body"


class TestEveryControlHasSomethingBehindIt:
    """A button whose handler does not exist is indistinguishable from a dead
    page: no error is raised until it is pressed, and then only in a console
    nobody has open.

    Written after a release where several controls did nothing. Those had a
    different cause, but the audit that found it had no way to run twice.
    """

    # Called on an object, not a bare function: document.getElementById(...),
    # classList.toggle(...), event.stopPropagation(), el.remove().
    METHODS = {"getElementById", "querySelector", "remove", "stopPropagation", "toggle", "preventDefault", "focus"}
    BUILTINS = {
        "esc", "alert", "confirm", "parseInt", "parseFloat", "String", "Number",
        "Boolean", "Array", "Object", "JSON", "Math", "Date", "setTimeout",
        "encodeURIComponent", "decodeURIComponent",
    }
    KEYWORDS = {"if", "for", "while", "return", "function", "new", "typeof", "catch", "switch"}

    def _handlers(self, markup: str) -> set:
        out = set()
        for attr in re.finditer(r'on(?:click|change|input|submit|keyup)\s*=\s*(["\'])(.*?)\1', markup, re.S):
            for call in re.finditer(r"([A-Za-z_$][\w$]*)\s*\(", attr.group(2)):
                name = call.group(1)
                if name not in self.KEYWORDS:
                    out.add(name)
        return out

    def _defined(self, markup: str) -> set:
        out = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", markup))
        out |= set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\()", markup))
        out |= set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=", markup))
        return out

    def test_every_handler_resolves(self):
        markup = read_template()
        missing = sorted(
            h
            for h in self._handlers(markup)
            if h not in self._defined(markup) and h not in self.BUILTINS and h not in self.METHODS
        )
        assert not missing, f"controls calling functions that do not exist: {missing}"

    def test_the_scan_sees_the_controls(self):
        # Guard against a regex change making the check pass vacuously.
        assert len(self._handlers(read_template())) > 60
