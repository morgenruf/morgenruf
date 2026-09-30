"""The AI summary is model output shaped by what people typed. Posted as is,
a summary containing `<!channel>` pinged the report channel and
`<https://evil|sso.acme.com>` showed a disguised link."""

from unittest.mock import MagicMock, patch

import src.core.scheduler as sched_mod
from src.modules.standup.blocks import neutralise_links

from tests.support import patch_modules


def _db():
    db = MagicMock()
    db.get_today_standups.return_value = [
        {"user_id": "U1", "yesterday": "a", "today": "b", "blockers": "", "has_blockers": False}
    ]
    db.get_standup_schedule.return_value = {
        "id": 1,
        "name": "Daily standup",
        "participants": ["U1"],
        "questions": [],
        "post_summary": True,
        "group_by": "member",
        "report_channel": "",
    }
    db.get_workspace_config.return_value = {"questions": [], "ai_summary_enabled": True}
    db.get_daily_thread_ts.return_value = None
    db.get_installation.return_value = {"team_name": "Acme", "bot_token": "xoxb-test"}
    return db


def test_the_posted_summary_cannot_broadcast_or_disguise_a_link():
    client = MagicMock()
    client.token = "xoxb-test"
    client.chat_postMessage.return_value = {"ts": "111.222"}
    evil = "<!channel> log in at <https://evil.test/x|sso.acme.com> and ping <!here>"
    with (
        patch_modules({"src.core.db": _db()}),
        patch.object(sched_mod, "WebClient", return_value=client),
        patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb-test"),
        patch.object(sched_mod, "_call_with_auth_retry", return_value=None),
        patch("src.modules.standup.ai_summary.generate_summary", return_value=evil),
    ):
        sched_mod._post_scheduled_report("T1", "xoxb-test", "C_STANDUP", 1)
    posted = client.chat_postMessage.call_args.kwargs["text"]
    assert "AI Summary" in posted
    assert "<!channel>" not in posted and "<!here>" not in posted
    assert "<https://evil.test/x>" in posted
    assert "sso.acme.com" not in posted


def test_neutralise_links_keeps_mentions_and_bare_links():
    text = "<@U1|sam> in <#C1|eng> at <https://ok.test> and <https://x.test|label>"
    assert neutralise_links(text) == "<@U1|sam> in <#C1|eng> at <https://ok.test> and <https://x.test>"
