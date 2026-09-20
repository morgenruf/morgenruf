"""The Tilt launcher must not inherit a non-local database connection."""

import argparse
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location("morgenruf_dev", Path(__file__).parents[1] / "dev.py")
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "app").mkdir()
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setattr(os, "environ", {})
    return tmp_path


def test_local_configuration_overrides_database_and_origin(workspace):
    os.environ.update(
        DATABASE_URL="postgresql://production.invalid/production",
        APP_URL="https://production.invalid",
        PORT="80",
        SESSION_COOKIE_SECURE="true",
        SLACK_CLIENT_SECRET="shell-secret",
    )
    env = workspace / "app" / ".env"
    env.write_text(
        "DATABASE_URL=postgresql://another-production.invalid/production\n"
        "SLACK_CLIENT_SECRET=file-secret\n"
        "SLACK_SIGNING_SECRET='quoted $value ${NOT_EXPANDED} $(not-executed)'\n"
        'ZOOM_CLIENT_SECRET="double quoted value"\n'
    )

    dev.configure_environment(dev.parse_args(["migrate", "--db-port", "5544", "--backend-port", "3009"]))

    assert os.environ["DATABASE_URL"] == "postgresql://morgenruf:morgenruf@127.0.0.1:5544/morgenruf"
    assert os.environ["APP_URL"] == "http://localhost:3006"
    assert os.environ["PORT"] == "3009"
    assert os.environ["SESSION_COOKIE_SECURE"] == "false"
    assert os.environ["SLACK_CLIENT_SECRET"] == "shell-secret"
    assert os.environ["SLACK_SIGNING_SECRET"] == "quoted $value ${NOT_EXPANDED} $(not-executed)"
    assert os.environ["ZOOM_CLIENT_SECRET"] == "double quoted value"


@pytest.mark.parametrize(
    ("app_url", "secure"),
    [("https://local.example.test/", "true"), ("http://localhost:3006", "false")],
)
def test_cookie_security_follows_explicit_public_origin(workspace, app_url, secure):
    os.environ["SESSION_COOKIE_SECURE"] = "false" if secure == "true" else "true"

    dev.configure_environment(dev.parse_args(["serve", "--app-url", app_url]))

    assert os.environ["APP_URL"] == app_url.rstrip("/")
    assert os.environ["SESSION_COOKIE_SECURE"] == secure


def test_missing_env_file_is_optional_and_secret_is_stable(workspace):
    env_file = workspace / "app" / ".env"
    args = dev.parse_args(["serve"])

    dev.configure_environment(args)
    first_secret = os.environ.pop("FLASK_SECRET_KEY")
    dev.configure_environment(args)

    assert os.environ["FLASK_SECRET_KEY"] == first_secret
    assert len(first_secret) == 64
    assert (workspace / ".local" / "flask-secret-key").stat().st_mode & 0o777 == 0o600
    assert not env_file.exists()


def test_env_file_is_preserved_when_generating_secret(workspace):
    env_file = workspace / "app" / ".env"
    original = "FLASK_SECRET_KEY=\nSLACK_CLIENT_ID=example\n"
    env_file.write_text(original)

    dev.configure_environment(dev.parse_args(["serve"]))

    assert env_file.read_text() == original
    assert len(os.environ["FLASK_SECRET_KEY"]) == 64


def test_supplied_secret_does_not_create_fallback_file(workspace):
    env_file = workspace / "custom.env"
    env_file.write_text("FLASK_SECRET_KEY='a supplied stable development key'\n")

    dev.configure_environment(dev.parse_args(["serve", "--env-file", str(env_file)]))

    assert os.environ["FLASK_SECRET_KEY"] == "a supplied stable development key"
    assert not (workspace / ".local").exists()


@pytest.mark.parametrize(
    "value",
    [
        "ftp://localhost:3006",
        "localhost:3006",
        "https://user:password@example.test",
        "http://localhost/dashboard",
        "http://localhost?next=dashboard",
        "http://localhost#dashboard",
        "http://localhost:70000",
        "http://localhost:0",
        "http://local host",
    ],
)
def test_rejects_invalid_public_origins(value):
    with pytest.raises(argparse.ArgumentTypeError):
        dev.origin(value)


@pytest.mark.parametrize("value", ["not-a-port", "0", "65536"])
def test_rejects_invalid_ports(value):
    with pytest.raises(argparse.ArgumentTypeError):
        dev.port(value)


def test_serve_uses_one_app_without_werkzeug_reloader(workspace, monkeypatch):
    app = Mock()
    create_app = Mock(return_value=(Mock(), app))
    imports = Mock(return_value=SimpleNamespace(create_app=create_app))
    monkeypatch.setattr(dev.importlib, "import_module", imports)
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(dev.sys, "path", list(dev.sys.path))

    assert dev.main(["serve", "--backend-port", "3011"]) == 0

    imports.assert_called_once_with("src.main")
    create_app.assert_called_once_with()
    app.run.assert_called_once_with(host="127.0.0.1", port=3011, debug=False, use_reloader=False)
    assert dev.sys.path[0] == str(workspace / "app")
    assert Path.cwd() == workspace / "app"


def test_migrate_only_imports_migration_runner(workspace, monkeypatch):
    run_migrations = Mock()
    imports = Mock(return_value=SimpleNamespace(run_migrations=run_migrations))
    monkeypatch.setattr(dev.importlib, "import_module", imports)
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(dev.sys, "path", list(dev.sys.path))

    assert dev.main(["migrate"]) == 0

    imports.assert_called_once_with("src.core.migrations_runner")
    run_migrations.assert_called_once_with()
