"""Personal banner cards: signed URLs, drawing, and when a post gets one."""

from __future__ import annotations

import io
from datetime import date

import pytest
from PIL import Image
from src.modules.celebrations import cards, jobs
from src.modules.celebrations.rules import ANNIVERSARY, BIRTHDAY

from tests.test_celebrations import FRI, FRIDAY_MORNING, row, world  # noqa: F401

CARD = {"k": BIRTHDAY, "d": "deploy", "n": "Priya Raman", "w": "Acme", "a": ""}


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_URL", "https://api.example.com")


class TestToken:
    def test_round_trip(self):
        assert cards.read_token(cards.token(CARD)) == CARD

    def test_a_changed_card_is_refused(self):
        signed = cards.token(CARD)
        other = cards.token({**CARD, "n": "Someone Else"})
        assert cards.read_token(other.split(".")[0] + "." + signed.split(".")[1]) is None

    def test_a_token_from_another_secret_is_refused(self, monkeypatch):
        signed = cards.token(CARD)
        monkeypatch.setenv("FLASK_SECRET_KEY", "another")
        assert cards.read_token(signed) is None

    @pytest.mark.parametrize("value", ["", "abc", "abc.def", "."])
    def test_garbage_is_refused(self, value):
        assert cards.read_token(value) is None

    def test_an_unknown_design_is_refused(self):
        assert cards.read_token(cards.token({**CARD, "d": "nope"})) is None

    def test_no_card_without_a_secret(self, monkeypatch):
        monkeypatch.delenv("FLASK_SECRET_KEY")
        assert cards.image_block(CARD) is None


class TestDrawing:
    @pytest.mark.parametrize(
        "kind,design", [(kind, design) for kind, designs in cards.DESIGNS.items() for design in designs]
    )
    @pytest.mark.parametrize("name", ["Priya Raman", "Maximilian Alexander Featherstonehaugh-Smythe", "李"])
    def test_every_design_draws_a_banner_sized_png(self, kind, design, name):
        card = {"k": kind, "d": design, "n": name, "w": "A Very Long Workspace Name", "a": "", "y": 12}
        image = Image.open(io.BytesIO(cards.render(card, Image.new("RGB", (512, 512), "#c98b5e"))))
        assert image.format == "PNG"
        assert image.size == (cards.WIDTH, cards.HEIGHT)

    def test_initials_without_a_photo(self):
        assert cards._initials("Priya Raman") == "PR"
        assert cards._initials("Cher") == "C"
        assert cards._initials("") == "?"

    @pytest.mark.parametrize(
        "url", ["http://avatars.slack-edge.com/a.png", "https://evil.example/a.png", "https://169.254.169.254/", ""]
    )
    def test_photos_only_come_from_slack(self, url, monkeypatch):
        monkeypatch.setattr("requests.get", lambda *a, **k: pytest.fail("fetched " + url))
        assert cards._photo(url) is None

    def test_pick_never_repeats_the_last_design(self):
        for _ in range(20):
            assert cards.pick(BIRTHDAY, "card-deploy") == "merged"


class TestRoute:
    @pytest.fixture
    def client(self):
        from flask import Flask

        app = Flask(__name__)
        cards.register_route(app)
        return app.test_client()

    def test_draws_a_signed_card(self, client):
        response = client.get(f"/celebrations/cards/{cards.token(CARD)}.png")
        assert response.status_code == 200
        assert response.mimetype == "image/png"
        assert "max-age" in response.headers["Cache-Control"]

    def test_an_unsigned_card_is_not_found(self, client):
        assert client.get("/celebrations/cards/abc.def.png").status_code == 404


@pytest.fixture
def card_world(world, monkeypatch):  # noqa: F811 (the fixture imported above)
    state, store, slack = world
    state["settings"]["personal_banners"] = True
    monkeypatch.setattr("src.modules.celebrations.db.last_banner", lambda team, kind: None)
    monkeypatch.setattr("src.core.db.get_installation", lambda team: {"team_name": "Acme"})
    profiles = {
        "U1": {
            "real_name": "Priya Raman",
            "image_512": "https://avatars.slack-edge.com/p.png",
            "is_custom_image": True,
        },
        "U2": {"real_name": "Tom Berg", "image_512": "https://secure.gravatar.com/x", "is_custom_image": False},
    }
    slack.users_info = lambda user: {"user": {"id": user, "profile": profiles.get(user, {})}}
    return state, store, slack


def _card(post):
    url = post["blocks"][1]["image_url"]
    assert url.startswith("https://api.example.com/celebrations/cards/")
    return cards.read_token(url.rsplit("/", 1)[1].removesuffix(".png"))


class TestPosting:
    def test_one_birthday_gets_a_personal_card(self, card_world):
        state, store, slack = card_world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        card = _card(slack.posts[0])
        assert card == {
            "k": BIRTHDAY,
            "d": card["d"],
            "n": "Priya Raman",
            "w": "Acme",
            "a": "https://avatars.slack-edge.com/p.png",
        }
        assert slack.posts[0]["blocks"][1]["alt_text"] == "A birthday card for Priya Raman"
        assert store.posts[("T1", BIRTHDAY, FRI)]["banner"] == f"card-{card['d']}"

    def test_an_anniversary_card_carries_the_years_and_no_default_avatar(self, card_world):
        state, store, slack = card_world
        state["rows"] = [row("U2", "Tom", start=date(2023, 9, 25))]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        card = _card(slack.posts[0])
        assert card["k"] == ANNIVERSARY and card["y"] == 3 and card["a"] == ""

    def test_two_people_get_a_stock_banner(self, card_world):
        state, store, slack = card_world
        state["rows"] = [row("U1", "Priya", 9, 25), row("U2", "Tom", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert "/celebrations/banners/birthday-" in slack.posts[0]["blocks"][1]["image_url"]

    def test_off_by_default(self, card_world):
        state, store, slack = card_world
        state["settings"]["personal_banners"] = False
        state["rows"] = [row("U1", "Priya", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert "/celebrations/banners/birthday-" in slack.posts[0]["blocks"][1]["image_url"]

    def test_a_card_that_cannot_be_signed_falls_back_to_a_stock_banner(self, card_world, monkeypatch):
        state, store, slack = card_world
        monkeypatch.delenv("FLASK_SECRET_KEY")
        state["rows"] = [row("U1", "Priya", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert "/celebrations/banners/birthday-" in slack.posts[0]["blocks"][1]["image_url"]
