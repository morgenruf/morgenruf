"""Webhooks must not reach internal addresses.

The URL check ran only when a webhook was saved and never resolved hostnames,
and delivery followed redirects. A webhook pointed at redis.<ns>.svc, or at a
public host redirecting to 169.254.169.254, reached the internal service, and
the test-send endpoint reported back what it found.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.core import url_guard


def _resolving_to(monkeypatch, *addrs):
    monkeypatch.setattr(url_guard, "_resolve", lambda host: list(addrs))


class TestResolvesToPublic:
    def test_public_address_passes(self, monkeypatch):
        _resolving_to(monkeypatch, "93.184.215.14")
        assert url_guard.resolves_to_public("https://hooks.example.com/x") is True

    @pytest.mark.parametrize(
        "addr",
        [
            "10.0.0.5",  # cluster service
            "172.20.1.1",
            "192.168.1.10",
            "127.0.0.1",
            "169.254.169.254",  # cloud metadata
            "100.64.0.10",  # shared address space, used for pods in some clusters
            "::1",
            "fd00::1",
            "::ffff:10.0.0.5",  # IPv4-mapped private address
            "0.0.0.0",
        ],
    )
    def test_internal_address_is_refused(self, monkeypatch, addr):
        _resolving_to(monkeypatch, addr)
        assert url_guard.resolves_to_public("https://redis.default.svc/x") is False

    def test_one_private_answer_among_public_ones_is_refused(self, monkeypatch):
        _resolving_to(monkeypatch, "93.184.215.14", "10.0.0.5")
        assert url_guard.resolves_to_public("https://mixed.example.com/") is False

    def test_resolution_failure_is_refused(self, monkeypatch):
        def fail(host):
            raise OSError("no such host")

        monkeypatch.setattr(url_guard, "_resolve", fail)
        assert url_guard.resolves_to_public("https://nowhere.invalid/") is False

    def test_real_resolver_reads_getaddrinfo(self, monkeypatch):
        import socket

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET6, 1, 6, "", ("fe80::1%eth0", 0, 0, 0))],
        )
        assert url_guard._system_resolve("x") == ["fe80::1"]

    def test_shared_address_literal_is_refused_at_save_time(self):
        assert url_guard.is_safe_webhook_url("http://100.64.0.10/hook") is False


class TestDelivery:
    def _deliver(self, monkeypatch, addr):
        from src.modules.standup import handlers

        _resolving_to(monkeypatch, addr)
        monkeypatch.setattr(handlers, "_record_delivery", lambda *a: None)
        requests_mock = MagicMock()
        requests_mock.post.return_value.status_code = 200
        with patch.object(handlers, "requests", requests_mock):
            result = handlers.deliver_webhook(
                {"id": 1, "webhook_url": "https://hooks.example.com/x", "secret": None},
                "standup.completed",
                {"a": 1},
                team_id="T1",
            )
        return result, requests_mock

    def test_internal_target_is_never_contacted(self, monkeypatch):
        result, requests_mock = self._deliver(monkeypatch, "10.0.0.5")
        requests_mock.post.assert_not_called()
        assert result["ok"] is False
        assert result["status_code"] is None

    def test_redirects_are_not_followed(self, monkeypatch):
        _, requests_mock = self._deliver(monkeypatch, "93.184.215.14")
        assert requests_mock.post.call_args.kwargs["allow_redirects"] is False
