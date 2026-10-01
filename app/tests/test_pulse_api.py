"""The Pulse dashboard API: settings for admins, team trends for everyone,
and nothing at all from a round under five."""

from __future__ import annotations

import pytest

from tests.browser_fixtures import create_test_app

SETTINGS = {
    "enabled": True,
    "day_of_week": 1,
    "hour": 10,
    "minute": 30,
    "timezone": "Europe/Berlin",
    "audience_channel_id": "C_GENERAL",
}


@pytest.fixture
def app(monkeypatch):
    return create_test_app(monkeypatch)


def signed_in(app, role):
    client = app.test_client()
    token = client.post(f"/__test__/session?role={role}").json["csrf_token"]
    return client, {"X-CSRF-Token": token}


class TestTrend:
    def test_a_hidden_round_has_no_result_keys_at_all(self, app):
        client, _ = signed_in(app, "member")
        hidden, shown = client.get("/dashboard/api/pulse/trend").json
        assert set(hidden) == {"sent_on", "respondents", "invited", "hidden", "needed"}
        assert hidden["hidden"] is True and hidden["needed"] == 5 and hidden["respondents"] == 3
        assert shown["hidden"] is False and shown["mood_avg"] == 3.71 and shown["enps"] == 14
        assert shown["mood_dist"] == [0, 2, 3, 4, 3]

    def test_the_route_hides_a_round_even_if_storage_returned_numbers(self, app):
        state = app.extensions["browser_test_data"]
        state.pulse_trend[0].update(mood_avg=1.0, mood_dist=[3, 0, 0, 0, 0], enps=-100)
        client, _ = signed_in(app, "admin")
        hidden = client.get("/dashboard/api/pulse/trend").json[0]
        assert "mood_avg" not in hidden and "mood_dist" not in hidden and "enps" not in hidden

    def test_the_route_hides_a_round_under_five_whatever_the_flag_says(self, app):
        state = app.extensions["browser_test_data"]
        state.pulse_trend[1]["respondents"] = 4
        client, _ = signed_in(app, "admin")
        row = client.get("/dashboard/api/pulse/trend").json[1]
        assert row["hidden"] is True and "mood_avg" not in row

    def test_an_open_round_has_no_result_keys_even_with_many_answers(self, app):
        state = app.extensions["browser_test_data"]
        state.pulse_trend.append(
            {
                "sent_on": state.today,
                "respondents": 11,
                "invited": 14,
                "hidden": False,
                "open": True,
                "mood_avg": 4.2,
                "mood_dist": [0, 0, 2, 4, 5],
                "enps": 30,
            }
        )
        client, _ = signed_in(app, "admin")
        row = client.get("/dashboard/api/pulse/trend").json[2]
        assert set(row) == {"sent_on", "respondents", "invited", "hidden", "needed", "open"}
        assert row["open"] is True and row["respondents"] == 11

    def test_under_ten_shows_the_average_but_not_the_breakdown_or_enps(self, app):
        state = app.extensions["browser_test_data"]
        state.pulse_trend[1]["respondents"] = 7
        client, _ = signed_in(app, "admin")
        row = client.get("/dashboard/api/pulse/trend").json[1]
        assert row["mood_avg"] == 3.71
        assert "mood_dist" not in row and "enps" not in row

    def test_signed_out_is_refused(self, app):
        assert app.test_client().get("/dashboard/api/pulse/trend").status_code == 401


class TestSettings:
    def test_anyone_signed_in_can_read_them(self, app):
        client, _ = signed_in(app, "member")
        body = client.get("/dashboard/api/pulse/settings").json
        assert body["enabled"] is True and body["day_of_week"] == 4

    def test_a_member_cannot_change_them(self, app):
        client, headers = signed_in(app, "member")
        assert client.put("/dashboard/api/pulse/settings", json=SETTINGS, headers=headers).status_code == 403
        assert app.extensions["browser_test_data"].pulse_program["hour"] == 14

    def test_a_pulse_admin_can(self, app):
        app.extensions["browser_test_data"].grants["U_LEAD"].add("pulse")
        client, headers = signed_in(app, "feature-admin")
        body = client.put("/dashboard/api/pulse/settings", json=SETTINGS, headers=headers).json
        assert body["hour"] == 10 and body["timezone"] == "Europe/Berlin"
        assert app.extensions["browser_test_data"].pulse_program["updated_by"] == "U_LEAD"

    def test_another_features_admin_cannot(self, app):
        client, headers = signed_in(app, "feature-admin")
        assert client.put("/dashboard/api/pulse/settings", json=SETTINGS, headers=headers).status_code == 403

    def test_a_bad_timezone_is_refused(self, app):
        client, headers = signed_in(app, "admin")
        response = client.put(
            "/dashboard/api/pulse/settings", json={**SETTINGS, "timezone": "Mars/Base"}, headers=headers
        )
        assert response.status_code == 400 and "timezone" in response.json["details"]

    def test_a_legacy_timezone_is_stored_canonical(self, app):
        client, headers = signed_in(app, "admin")
        body = client.put(
            "/dashboard/api/pulse/settings", json={**SETTINGS, "timezone": "Asia/Calcutta"}, headers=headers
        ).json
        assert body["timezone"] == "Asia/Kolkata"

    @pytest.mark.parametrize("field,value", [("day_of_week", 7), ("hour", 24), ("minute", 60)])
    def test_out_of_range_is_refused(self, app, field, value):
        client, headers = signed_in(app, "admin")
        response = client.put("/dashboard/api/pulse/settings", json={**SETTINGS, field: value}, headers=headers)
        assert response.status_code == 400

    def test_an_audience_channel_without_the_bot_is_refused(self, app):
        client, headers = signed_in(app, "admin")
        response = client.put(
            "/dashboard/api/pulse/settings", json={**SETTINGS, "audience_channel_id": "C_ELSEWHERE"}, headers=headers
        )
        assert response.status_code == 400
        assert response.json["details"]["audience_channel_id"] == ["Invite @Morgenruf to that channel first"]
        assert app.extensions["browser_test_data"].pulse_program["audience_channel_id"] is None

    def test_a_slack_error_checking_the_channel_is_a_502(self, app, monkeypatch):
        import slack_sdk

        def boom(self, **kwargs):
            raise RuntimeError("ratelimited")

        monkeypatch.setattr(slack_sdk.WebClient, "users_conversations", boom)
        client, headers = signed_in(app, "admin")
        response = client.put("/dashboard/api/pulse/settings", json=SETTINGS, headers=headers)
        assert response.status_code == 502 and response.json["error"]

    def test_turning_the_module_off_closes_open_rounds(self, app, monkeypatch):
        import src.modules.pulse.db as pdb

        closed = []
        monkeypatch.setattr(pdb, "close_open_rounds", lambda team: closed.append(team) or [])
        client, headers = signed_in(app, "admin")
        assert client.post("/dashboard/api/modules/pulse", json={"enabled": False}, headers=headers).status_code == 200
        assert closed == ["T_BROWSER"]

    def test_an_empty_audience_means_everyone(self, app):
        client, headers = signed_in(app, "admin")
        body = client.put(
            "/dashboard/api/pulse/settings", json={**SETTINGS, "audience_channel_id": ""}, headers=headers
        ).json
        assert body["audience_channel_id"] is None
