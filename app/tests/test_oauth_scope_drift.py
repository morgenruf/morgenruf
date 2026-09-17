"""The scopes we ask for must agree across every place they are written down.

There are three: the install URL built in oauth.py, the copy of it in
dashboard.py, and the Slack app manifest. They have drifted before, and the
symptom is not a test failure but an install that Slack rejects, or a feature
that silently never works because the token lacks a scope nobody noticed was
missing.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Slack grants this from declaring slash commands rather than from the oauth
# scope list, so it is legitimately absent from the manifest's bot scopes.
IMPLIED_BY_FEATURES = {"commands"}


def _oauth_scopes() -> list[str]:
    src = (ROOT / "app/src/core/oauth.py").read_text()
    block = re.search(r"_SCOPES = \[(.*?)\]", src, re.S).group(1)
    return re.findall(r'"([^"]+)"', block)


def _dashboard_scopes() -> list[str]:
    """Read the comma-separated list, however the formatter has wrapped it."""
    src = (ROOT / "app/src/core/dashboard.py").read_text()
    block = re.search(r"_SCOPES = \(?\s*(.*?)\s*\)?\n\n", src, re.S).group(1)
    return "".join(re.findall(r'"([^"]*)"', block)).split(",")


def _manifest_scopes() -> set[str]:
    data = json.loads((ROOT / "slack-manifest.json").read_text())
    return set(data["oauth_config"]["scopes"]["bot"])


def test_the_two_install_url_scope_lists_agree():
    assert sorted(_oauth_scopes()) == sorted(_dashboard_scopes())


def test_every_scope_we_request_is_declared_in_the_manifest():
    """Requesting a scope the app does not declare makes Slack refuse the install."""
    requested = set(_oauth_scopes()) - IMPLIED_BY_FEATURES
    missing = sorted(requested - _manifest_scopes())
    assert not missing, f"requested but not in the manifest: {missing}"


def _yaml_scopes() -> set[str]:
    import yaml

    y = yaml.safe_load((ROOT / "slack-manifest.yaml").read_text())
    return set(y["oauth_config"]["scopes"]["bot"])


# The two manifests disagree, and have since before this guard existed. Which
# one was uploaded to Slack is not recorded anywhere, so this pins the known
# difference rather than guessing: if it changes in either direction, someone
# has edited one manifest and not the other and should be told.
KNOWN_JSON_ONLY = {"app_mentions:read", "channels:join", "chat:write.public"}


def test_the_manifests_differ_only_in_the_way_they_already_did():
    json_only = _manifest_scopes() - _yaml_scopes()
    yaml_only = _yaml_scopes() - _manifest_scopes()
    assert yaml_only == set(), f"yaml declares scopes the json does not: {sorted(yaml_only)}"
    assert json_only == KNOWN_JSON_ONLY, (
        "the manifests drifted further apart; reconcile them and update "
        f"KNOWN_JSON_ONLY. json-only is now {sorted(json_only)}"
    )


def test_every_requested_scope_is_in_both_manifests():
    """Whichever manifest was uploaded, an install must not ask for more than it declares."""
    requested = set(_oauth_scopes()) - IMPLIED_BY_FEATURES
    assert not sorted(requested - _manifest_scopes()), "missing from slack-manifest.json"
    assert not sorted(requested - _yaml_scopes()), "missing from slack-manifest.yaml"


def test_emoji_read_is_present_so_the_branded_token_can_be_confirmed():
    assert "emoji:read" in _oauth_scopes()
    assert "emoji:read" in _manifest_scopes()


def test_no_scope_is_listed_twice():
    for name, scopes in (("oauth", _oauth_scopes()), ("dashboard", _dashboard_scopes())):
        assert len(scopes) == len(set(scopes)), f"{name} repeats a scope"
