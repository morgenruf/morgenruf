"""Celebration banners: which image goes on a post, and that a post never depends on one."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from src.modules.celebrations import banners, jobs
from src.modules.celebrations.rules import ANNIVERSARY, BIRTHDAY

from tests.test_celebrations import FRI, FRIDAY_MORNING, row, world  # noqa: F401


class TestCatalogue:
    def test_eight_of_each_kind_ship_with_the_app(self):
        assert len(banners.available(BIRTHDAY)) == 8
        assert len(banners.available(ANNIVERSARY)) == 8

    def test_every_banner_file_exists(self):
        for kind in (BIRTHDAY, ANNIVERSARY):
            for name in banners.available(kind):
                assert (banners.BANNER_DIR / name).is_file()
                assert banners.is_banner(name)

    @pytest.mark.parametrize("name", ["../jobs.py", "birthday-1.svg", "", "x.png", "birthday-9.png"])
    def test_only_shipped_files_count_as_banners(self, name):
        assert not banners.is_banner(name)


class TestPick:
    def test_never_the_same_banner_twice_in_a_row(self):
        last = banners.available(BIRTHDAY)[0]
        for _ in range(50):
            assert banners.pick(BIRTHDAY, last) != last

    def test_any_banner_when_there_is_no_last(self):
        assert banners.pick(BIRTHDAY, None, choose=lambda options: options[-1]) == banners.available(BIRTHDAY)[-1]

    def test_an_unknown_last_banner_is_ignored(self):
        assert banners.pick(ANNIVERSARY, "gone.png") in banners.available(ANNIVERSARY)


class TestUrl:
    def test_built_from_the_app_url(self, monkeypatch):
        monkeypatch.setenv("APP_URL", "https://api.example.com/")
        assert banners.url("birthday-2.png") == "https://api.example.com/celebrations/banners/birthday-2.png"

    def test_none_without_an_app_url(self, monkeypatch):
        monkeypatch.delenv("APP_URL", raising=False)
        assert banners.url("birthday-2.png") is None


@pytest.fixture
def banner_world(world, monkeypatch):  # noqa: F811 (the fixture imported above)
    state, store, slack = world
    monkeypatch.setenv("APP_URL", "https://api.example.com")
    state["last_banner"] = {}
    monkeypatch.setattr("src.modules.celebrations.db.last_banner", lambda team, kind: state["last_banner"].get(kind))
    return state, store, slack


class TestPosting:
    def test_a_post_carries_a_banner_with_alt_text(self, banner_world):
        state, store, slack = banner_world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        post = slack.posts[0]
        assert post["text"].startswith("🎂 Today is <@U1>'s birthday!")
        section, image = post["blocks"]
        assert section["text"]["text"] == post["text"]
        assert image["type"] == "image"
        assert image["alt_text"] == banners.ALT_TEXT[BIRTHDAY]
        assert image["image_url"].startswith("https://api.example.com/celebrations/banners/birthday-")
        assert store.posts[("T1", BIRTHDAY, FRI)]["banner"] in banners.available(BIRTHDAY)

    def test_the_last_banner_is_not_repeated(self, banner_world):
        state, store, slack = banner_world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        last = banners.available(BIRTHDAY)[3]
        state["last_banner"][BIRTHDAY] = last
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert not slack.posts[0]["blocks"][1]["image_url"].endswith(last)

    def test_no_banner_when_switched_off(self, banner_world):
        state, store, slack = banner_world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        state["settings"]["banners"] = False
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert "blocks" not in slack.posts[0]
        assert store.posts[("T1", BIRTHDAY, FRI)]["banner"] is None

    def test_no_banner_without_a_public_url(self, banner_world, monkeypatch):
        state, store, slack = banner_world
        monkeypatch.delenv("APP_URL")
        state["rows"] = [row("U1", "Priya", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert "blocks" not in slack.posts[0]

    def test_slack_refusing_the_image_still_posts_the_text(self, banner_world):
        """A self-hosted install Slack cannot reach: the image fails, the celebration does not."""
        state, store, slack = banner_world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        original = slack.chat_postMessage

        def refuse_images(**kw):
            if "blocks" in kw:
                raise RuntimeError("invalid_blocks: downloading image failed")
            return original(**kw)

        slack.chat_postMessage = refuse_images
        assert len(jobs.run_daily("T1", now=FRIDAY_MORNING)) == 1
        assert "blocks" not in slack.posts[0]
        assert store.posts[("T1", BIRTHDAY, FRI)]["banner"] is None
        assert store.released == []

    def test_anniversaries_get_anniversary_banners(self, banner_world):
        state, store, slack = banner_world
        state["rows"] = [row("U2", "Tom", start=date(2023, 9, 25))]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        image = slack.posts[0]["blocks"][1]
        assert "/anniversary-" in image["image_url"]
        assert image["alt_text"] == banners.ALT_TEXT[ANNIVERSARY]


class TestRoute:
    @pytest.fixture
    def client(self):
        from flask import Flask

        app = Flask(__name__)
        banners.register_route(app)
        return app.test_client()

    def test_serves_a_banner_with_a_long_cache(self, client):
        name = banners.available(BIRTHDAY)[0]
        response = client.get(f"/celebrations/banners/{name}")
        assert response.status_code == 200
        assert response.mimetype in {"image/png", "image/jpeg"}
        assert "max-age" in response.headers["Cache-Control"]

    @pytest.mark.parametrize("name", ["..%2Fjobs.py", "nope.png", "birthday-1.svg"])
    def test_anything_else_is_not_found(self, client, name):
        assert client.get(f"/celebrations/banners/{name}").status_code == 404


def test_world_time_constant_is_friday():
    assert FRIDAY_MORNING == datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
