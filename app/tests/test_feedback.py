"""feedback.file_issue: the GitHub call behind the dashboard's feedback dialog."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest
from src.core import feedback


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setenv("FEEDBACK_GITHUB_TOKEN", "github_pat_test")
    monkeypatch.setenv("FEEDBACK_GITHUB_REPO", "morgenruf/feedback")


@pytest.fixture()
def github(monkeypatch):
    requests = MagicMock()
    requests.post.return_value.status_code = 201
    requests.post.return_value.json.return_value = {"html_url": "https://github.com/morgenruf/feedback/issues/7"}
    monkeypatch.setitem(sys.modules, "requests", requests)
    return requests


def test_off_without_both_settings(monkeypatch):
    monkeypatch.delenv("FEEDBACK_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("FEEDBACK_GITHUB_REPO", "morgenruf/feedback")
    assert feedback.enabled() is False
    monkeypatch.setenv("FEEDBACK_GITHUB_TOKEN", "t")
    monkeypatch.setenv("FEEDBACK_GITHUB_REPO", "not a repo")
    assert feedback.enabled() is False


def test_files_a_labelled_issue(configured, github):
    url = feedback.file_issue("idea", "Dark mode", "Please @team", {"workspace": "Acme (T1)", "page": "/dashboard/x"})
    assert url == "https://github.com/morgenruf/feedback/issues/7"
    (endpoint,), kwargs = github.post.call_args
    assert endpoint == "https://api.github.com/repos/morgenruf/feedback/issues"
    assert kwargs["headers"]["Authorization"] == "Bearer github_pat_test"
    issue = kwargs["json"]
    assert issue["title"] == "Dark mode"
    assert issue["labels"] == ["enhancement", "feedback"]
    assert "Acme (T1)" in issue["body"]
    assert "`/dashboard/x`" in issue["body"]
    # A mention in someone's report must not notify that GitHub user.
    assert "@team" not in issue["body"]


def test_github_refusal_is_none(configured, github):
    github.post.return_value.status_code = 401
    assert feedback.file_issue("bug", "Broken", "", {}) is None


def test_network_error_is_none(configured, github):
    github.post.side_effect = OSError("down")
    assert feedback.file_issue("bug", "Broken", "", {}) is None


def test_unconfigured_makes_no_call(monkeypatch, github):
    monkeypatch.delenv("FEEDBACK_GITHUB_TOKEN", raising=False)
    assert feedback.file_issue("bug", "Broken", "", {}) is None
    github.post.assert_not_called()
