"""The scopes must agree everywhere they are written down.

They used to live in three hand-kept copies: the install URL in oauth.py, a
second copy in dashboard.py, and the two manifests. They drifted twice, and the
symptom was never a failing test: it was coffee chats installing and staying
dark because the token lacked scopes nobody noticed were missing.

There is now one source, src/core/scopes.py, and everything else is generated
from it. These tests assert that, and that each module's declared requirements
are inside it.
"""

from __future__ import annotations

import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]

from src.core.scopes import BOT_SCOPES, SCOPE_STRING  # noqa: E402


def _yaml_manifest_scopes() -> list[str]:
    return yaml.safe_load((ROOT / "slack-manifest.yaml").read_text())["oauth_config"]["scopes"]["bot"]


def _json_manifest_scopes() -> list[str]:
    return json.loads((ROOT / "slack-manifest.json").read_text())["oauth_config"]["scopes"]["bot"]


def test_no_scope_is_listed_twice():
    assert len(BOT_SCOPES) == len(set(BOT_SCOPES))


def test_both_manifests_match_the_source_of_truth():
    assert sorted(_yaml_manifest_scopes()) == sorted(BOT_SCOPES)
    assert sorted(_json_manifest_scopes()) == sorted(BOT_SCOPES)


def test_the_manifests_match_each_other():
    """They carried three scopes the YAML did not, for months."""
    assert sorted(_json_manifest_scopes()) == sorted(_yaml_manifest_scopes())


def test_the_install_url_is_generated_not_copied():
    src = (ROOT / "app/src/core/oauth.py").read_text()
    assert "from src.core.scopes import BOT_SCOPES" in src
    dash = (ROOT / "app/src/core/dashboard.py").read_text()
    assert "SCOPE_STRING" in dash


def test_every_module_scope_is_actually_requested_at_install():
    """A module that needs a scope nobody asks for is a feature that never runs."""
    from src.modules import REGISTRY

    missing = {}
    for spec in REGISTRY:
        absent = [s for s in spec.required_scopes if s not in BOT_SCOPES]
        if absent:
            missing[spec.name] = absent
    assert not missing, f"modules needing scopes the install never asks for: {missing}"


def test_subscribed_events_have_the_scope_that_delivers_them():
    """app_mention is subscribed in the manifest; without app_mentions:read it
    never arrives. That exact pair was wrong until the marketplace audit."""
    manifest = yaml.safe_load((ROOT / "slack-manifest.yaml").read_text())
    events = manifest["settings"]["event_subscriptions"]["bot_events"]
    needs = {"app_mention": "app_mentions:read", "message.im": "im:history"}
    for event, scope in needs.items():
        if event in events:
            assert scope in BOT_SCOPES, f"{event} is subscribed but {scope} is not requested"


def test_the_scope_string_is_the_same_list():
    assert sorted(SCOPE_STRING.split(",")) == sorted(BOT_SCOPES)
