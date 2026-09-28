"""The Celebrations dashboard API: who may change what, and what it stores.

HR runs Celebrations without being a workspace admin, through the delegable
grant. These go through the real routes and schemas with in-memory storage.
"""

from __future__ import annotations

from datetime import date

import pytest

from tests.browser_fixtures import create_test_app


@pytest.fixture
def app(monkeypatch):
    return create_test_app(monkeypatch)


def signed_in(app, role):
    client = app.test_client()
    token = client.post(f"/__test__/session?role={role}").json["csrf_token"]
    return client, {"X-CSRF-Token": token}


SETTINGS = {
    "channel_id": "C_GENERAL",
    "timezone": "Asia/Dubai",
    "post_time": "10:30",
    "birthdays": True,
    "anniversaries": True,
    "working_days": ["sun", "mon", "tue", "wed", "thu"],
}

WRITES = [
    ("PUT", "/dashboard/api/celebrations/settings", SETTINGS),
    ("POST", "/dashboard/api/celebrations/holidays", {"date": "2027-12-25", "name": "Christmas Day"}),
    ("DELETE", "/dashboard/api/celebrations/holidays/2027-12-25", None),
    ("POST", "/dashboard/api/celebrations/holidays/import", {"csv": "2027-01-01,New Year\n", "preview": False}),
    ("POST", "/dashboard/api/celebrations/ask-dates", None),
]
ADMIN_READS = ["/dashboard/api/celebrations/upcoming", "/dashboard/api/celebrations/ask-dates"]


class TestDelegation:
    @pytest.mark.parametrize("method,path,body", WRITES)
    def test_a_member_is_refused(self, app, method, path, body):
        client, headers = signed_in(app, "member")
        assert client.open(path, method=method, json=body, headers=headers).status_code == 403

    @pytest.mark.parametrize("path", ADMIN_READS)
    def test_a_member_cannot_list_birthdays_or_the_ask(self, app, path):
        client, _ = signed_in(app, "member")
        assert client.get(path).status_code == 403

    @pytest.mark.parametrize("method,path,body", WRITES)
    def test_a_celebrations_admin_may(self, app, method, path, body):
        app.extensions["browser_test_data"].grants["U_LEAD"].add("celebrations")
        client, headers = signed_in(app, "feature-admin")
        assert client.open(path, method=method, json=body, headers=headers).status_code == 200

    @pytest.mark.parametrize("method,path,body", WRITES)
    def test_another_features_admin_may_not(self, app, method, path, body):
        client, headers = signed_in(app, "feature-admin")  # standup and connect only
        assert client.open(path, method=method, json=body, headers=headers).status_code == 403

    @pytest.mark.parametrize("method,path,body", WRITES)
    def test_a_workspace_admin_may(self, app, method, path, body):
        client, headers = signed_in(app, "admin")
        assert client.open(path, method=method, json=body, headers=headers).status_code == 200

    def test_anyone_signed_in_can_read_the_settings(self, app):
        client, _ = signed_in(app, "member")
        assert client.get("/dashboard/api/celebrations/settings").status_code == 200
        assert client.get("/dashboard/api/celebrations/holidays").status_code == 200


class TestSettings:
    def test_saving_stores_the_timezone_and_the_working_week(self, app):
        state = app.extensions["browser_test_data"]
        client, headers = signed_in(app, "admin")
        body = client.put("/dashboard/api/celebrations/settings", json=SETTINGS, headers=headers).json
        assert body["timezone"] == "Asia/Dubai"
        assert body["post_time"] == "10:30"
        assert body["working_days"] == ["mon", "tue", "wed", "thu", "sun"]
        assert body["ready"] is True
        assert state.working_days == "mon,tue,wed,thu,sun"
        assert state.celebration_settings["updated_by"] == "U_ADMIN"

    def test_the_timezone_is_not_standups(self, app):
        state = app.extensions["browser_test_data"]
        client, headers = signed_in(app, "admin")
        client.put("/dashboard/api/celebrations/settings", json=SETTINGS, headers=headers)
        assert "schedule_tz" not in state.workspace
        assert all(s["schedule_tz"] == "UTC" for s in state.schedules)

    @pytest.mark.parametrize(
        "change,field",
        [
            ({"timezone": "Mars/Olympus"}, "timezone"),
            ({"post_time": "25:00"}, "post_time"),
            ({"working_days": []}, "working_days"),
            ({"working_days": ["funday"]}, "working_days"),
            ({"channel_id": ""}, "channel_id"),
        ],
    )
    def test_bad_values_are_refused_on_the_field(self, app, change, field):
        client, headers = signed_in(app, "admin")
        response = client.put("/dashboard/api/celebrations/settings", json={**SETTINGS, **change}, headers=headers)
        assert response.status_code == 400
        assert field in str(response.json)

    def test_the_page_knows_whether_the_reaction_is_available(self, app):
        client, _ = signed_in(app, "admin")
        # The fixture grants only what modules require; reactions:write is optional.
        assert client.get("/dashboard/api/celebrations/settings").json["can_react"] is False


class TestHolidays:
    def test_add_rename_and_remove(self, app):
        client, headers = signed_in(app, "admin")
        url = "/dashboard/api/celebrations/holidays"
        client.post(url, json={"date": "2027-12-25", "name": "Christmas"}, headers=headers)
        listed = client.post(url, json={"date": "2027-12-25", "name": " Christmas  Day "}, headers=headers).json
        assert {"date": "2027-12-25", "name": "Christmas Day"} in listed
        listed = client.delete(f"{url}/2027-12-25", headers=headers).json
        assert all(h["date"] != "2027-12-25" for h in listed)

    def test_import_previews_before_writing(self, app):
        state = app.extensions["browser_test_data"]
        client, headers = signed_in(app, "admin")
        url = "/dashboard/api/celebrations/holidays/import"
        csv = "date,name\n2027-01-01,New Year\n2027-02-30,Nope\n"
        before = dict(state.holidays)
        preview = client.post(url, json={"csv": csv}, headers=headers).json
        assert (preview["preview"], preview["ready"], preview["invalid"], preview["written"]) == (True, 1, 1, 0)
        assert state.holidays == before
        saved = client.post(url, json={"csv": csv, "preview": False}, headers=headers).json
        assert saved["written"] == 1
        assert state.holidays[date(2027, 1, 1)] == "New Year"

    def test_an_unreadable_file_is_a_field_error(self, app):
        client, headers = signed_in(app, "admin")
        response = client.post("/dashboard/api/celebrations/holidays/import", json={"csv": "\n"}, headers=headers)
        assert response.status_code == 400
        assert "csv" in response.json["details"]


class TestAskForDates:
    def test_preview_counts_and_shows_the_message(self, app):
        client, _ = signed_in(app, "admin")
        body = client.get("/dashboard/api/celebrations/ask-dates").json
        # U_LEAD has dates; Alex and Jamie do not.
        assert body["count"] == 2
        assert body["message"].startswith("👋 Hi Priya! Your team celebrates")

    def test_sending_claims_so_a_second_click_sends_nothing(self, app):
        client, headers = signed_in(app, "admin")
        assert client.post("/dashboard/api/celebrations/ask-dates", headers=headers).json["count"] == 2
        assert client.post("/dashboard/api/celebrations/ask-dates", headers=headers).json["count"] == 0
        assert client.get("/dashboard/api/celebrations/ask-dates").json["count"] == 0

    def test_refused_until_there_is_a_channel(self, app):
        state = app.extensions["browser_test_data"]
        state.celebration_settings["channel_id"] = None
        client, headers = signed_in(app, "admin")
        assert client.post("/dashboard/api/celebrations/ask-dates", headers=headers).status_code == 409
