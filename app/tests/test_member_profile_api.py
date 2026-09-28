"""Who may read and write which profile, through the real routes and schemas.

A member reads and writes their own profile and nobody else's. The user id
comes from the session, so there is nothing in a request that can point the
write at someone else. An admin may write anyone's, and import dates for the
whole workspace, and a preview of that import writes nothing.
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


def profiles(app):
    return app.extensions["browser_test_data"].profiles


class TestAMemberAndTheirOwnProfile:
    def test_reads_their_own_even_before_filling_it_in(self, app):
        client, _ = signed_in(app, "member")
        body = client.get("/dashboard/api/profile").json
        assert body["user_id"] == "U_MEMBER"
        assert body["birth_month"] is None and body["celebrate"] is True

    def test_writes_their_own_and_is_recorded_as_the_author(self, app):
        client, headers = signed_in(app, "member")
        response = client.put(
            "/dashboard/api/profile",
            json={"birth_month": 2, "birth_day": 29, "role": "Designer", "location": "Lisbon"},
            headers=headers,
        )
        assert response.status_code == 200, response.json
        stored = profiles(app)["U_MEMBER"]
        assert (stored["birth_month"], stored["birth_day"], stored["updated_by"]) == (2, 29, "U_MEMBER")
        assert response.json["set_by_admin"] is False

    def test_a_user_id_in_the_body_cannot_redirect_the_write(self, app):
        client, headers = signed_in(app, "member")
        before = dict(profiles(app)["U_LEAD"])
        response = client.put("/dashboard/api/profile", json={"user_id": "U_LEAD", "role": "Hijacked"}, headers=headers)
        assert response.status_code == 200
        assert response.json["user_id"] == "U_MEMBER"
        assert profiles(app)["U_LEAD"] == before
        assert profiles(app)["U_MEMBER"]["role"] == "Hijacked"

    def test_cannot_write_someone_else(self, app):
        client, headers = signed_in(app, "member")
        response = client.put("/dashboard/api/profiles/U_LEAD", json={"role": "Nope"}, headers=headers)
        assert response.status_code == 403
        assert profiles(app)["U_LEAD"]["role"] == "Engineering lead"

    def test_cannot_list_everyone(self, app):
        client, _ = signed_in(app, "member")
        assert client.get("/dashboard/api/profiles").status_code == 403

    def test_cannot_import(self, app):
        client, headers = signed_in(app, "member")
        response = client.post(
            "/dashboard/api/profiles/import",
            json={"csv": "email,birthday\nu_lead@example.test,01-01\n", "preview": False},
            headers=headers,
        )
        assert response.status_code == 403
        assert profiles(app)["U_LEAD"]["birth_month"] == 3

    def test_a_feature_admin_is_not_a_profile_admin(self, app):
        client, headers = signed_in(app, "feature-admin")
        assert client.put("/dashboard/api/profiles/U_MEMBER", json={}, headers=headers).status_code == 403

    def test_30_february_is_a_field_error(self, app):
        client, headers = signed_in(app, "member")
        response = client.put("/dashboard/api/profile", json={"birth_month": 2, "birth_day": 30}, headers=headers)
        assert response.status_code == 400
        assert "birth_day" in response.json["details"]
        assert "U_MEMBER" not in profiles(app)

    def test_too_long_is_a_field_error(self, app):
        client, headers = signed_in(app, "member")
        response = client.put("/dashboard/api/profile", json={"ask_me_about": "x" * 201}, headers=headers)
        assert response.status_code == 400
        assert "ask_me_about" in response.json["details"]

    def test_the_member_can_clear_their_dates(self, app):
        client, headers = signed_in(app, "feature-admin")  # U_LEAD, who has dates on file
        response = client.put(
            "/dashboard/api/profile",
            json={"birth_month": None, "birth_day": None, "start_date": None},
            headers=headers,
        )
        assert response.status_code == 200
        stored = profiles(app)["U_LEAD"]
        assert stored["birth_month"] is None and stored["start_date"] is None
        assert stored["role"] == "Engineering lead"

    def test_needs_the_csrf_token(self, app):
        client, _ = signed_in(app, "member")
        assert client.put("/dashboard/api/profile", json={"role": "x"}).status_code == 403

    def test_needs_a_session(self, app):
        assert app.test_client().get("/dashboard/api/profile").status_code == 401


class TestAnAdmin:
    def test_writes_anyone_and_is_recorded_as_the_author(self, app):
        client, headers = signed_in(app, "admin")
        response = client.put("/dashboard/api/profiles/U_MEMBER", json={"start_date": "2022-05-01"}, headers=headers)
        assert response.status_code == 200
        assert response.json["set_by_admin"] is True
        stored = profiles(app)["U_MEMBER"]
        assert stored["start_date"] == date(2022, 5, 1) and stored["updated_by"] == "U_ADMIN"

    def test_lists_everyone(self, app):
        client, _ = signed_in(app, "admin")
        body = client.get("/dashboard/api/profiles").json
        assert [p["user_id"] for p in body] == ["U_LEAD"]
        assert body[0]["set_by_admin"] is True

    def test_a_malformed_id_is_refused(self, app):
        client, headers = signed_in(app, "admin")
        response = client.put("/dashboard/api/profiles/not-an-id", json={"role": "x"}, headers=headers)
        assert response.status_code == 404


CSV = (
    "email,birthday,start_date\n"
    "u_member@example.test,1990-07-04,2022-05-01\n"
    "u_lead@example.test,12-25,\n"
    "stranger@example.test,01-01,\n"
    "u_admin@example.test,02-30,\n"
)


class TestTheImport:
    def test_preview_writes_nothing(self, app):
        client, headers = signed_in(app, "admin")
        before = {k: dict(v) for k, v in profiles(app).items()}
        response = client.post("/dashboard/api/profiles/import", json={"csv": CSV}, headers=headers)
        assert response.status_code == 200, response.json
        body = response.json
        assert body["preview"] is True and body["written"] == 0
        assert (body["ready"], body["unmatched"], body["invalid"]) == (2, 1, 1)
        assert {k: dict(v) for k, v in profiles(app).items()} == before

    def test_import_writes_ready_rows_and_drops_the_year(self, app):
        client, headers = signed_in(app, "admin")
        response = client.post("/dashboard/api/profiles/import", json={"csv": CSV, "preview": False}, headers=headers)
        assert response.json["written"] == 2
        member = profiles(app)["U_MEMBER"]
        assert (member["birth_month"], member["birth_day"]) == (7, 4)
        assert member["start_date"] == date(2022, 5, 1)
        assert member["updated_by"] == "U_ADMIN"
        assert "1990" not in repr(member)
        # The lead's role survives an import that only carried a birthday.
        lead = profiles(app)["U_LEAD"]
        assert (lead["birth_month"], lead["birth_day"], lead["role"]) == (12, 25, "Engineering lead")

    def test_a_member_set_profile_is_kept_unless_overwrite(self, app):
        member, member_headers = signed_in(app, "member")
        member.put("/dashboard/api/profile", json={"birth_month": 8, "birth_day": 1}, headers=member_headers)

        admin, headers = signed_in(app, "admin")
        kept = admin.post("/dashboard/api/profiles/import", json={"csv": CSV, "preview": False}, headers=headers)
        row = next(r for r in kept.json["rows"] if r["email"] == "u_member@example.test")
        assert row["status"] == "kept"
        assert profiles(app)["U_MEMBER"]["birth_month"] == 8

        replaced = admin.post(
            "/dashboard/api/profiles/import",
            json={"csv": CSV, "preview": False, "overwrite": True},
            headers=headers,
        )
        row = next(r for r in replaced.json["rows"] if r["email"] == "u_member@example.test")
        assert row["status"] == "ready"
        assert profiles(app)["U_MEMBER"]["birth_month"] == 7

    def test_an_unreadable_file_is_a_400(self, app):
        client, headers = signed_in(app, "admin")
        response = client.post("/dashboard/api/profiles/import", json={"csv": "name\nx\n"}, headers=headers)
        assert response.status_code == 400
        assert "csv" in response.json["details"]
