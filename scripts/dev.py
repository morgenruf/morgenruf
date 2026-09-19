#!/usr/bin/env python3
"""Run Morgenruf against Tilt's isolated local database."""

from __future__ import annotations

import argparse
import importlib
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def port(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a port number") from exc
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("must be a port between 1 and 65535")
    return number


def origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and not any(character.isspace() for character in value)
        )
        # Accessing port also rejects malformed and out-of-range ports.
        if parsed.port == 0:
            valid = False
    except ValueError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError("must be an HTTP(S) origin without a path, credentials, query, or fragment")
    return value.rstrip("/")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("migrate", "serve"))
    parser.add_argument("--db-port", type=port, default=5436)
    parser.add_argument("--backend-port", type=port, default=3007)
    parser.add_argument("--app-url", type=origin, default="http://localhost:3006")
    parser.add_argument("--env-file", type=Path, default=ROOT / "app" / ".env")
    return parser.parse_args(argv)


def local_secret() -> str:
    """Keep local sessions valid across reloads without writing to app/.env."""
    directory = ROOT / ".local"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "flask-secret-key"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_text().strip()
        if not key:
            raise RuntimeError(f"The local session key file is empty: {path}") from None
        path.chmod(0o600)
        return key
    key = secrets.token_hex(32)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(key + "\n")
    return key


def configure_environment(args: argparse.Namespace) -> None:
    # Do not execute shell syntax or interpolate credential values such as ${...}.
    # Existing shell values take precedence for integration configuration.
    if args.env_file.exists():
        for name, value in dotenv_values(args.env_file, interpolate=False).items():
            if value is not None:
                os.environ.setdefault(name, value)

    # These connections always belong to this local stack, even when the shell
    # or app/.env contains production configuration.
    os.environ.update(
        DATABASE_URL=f"postgresql://morgenruf:morgenruf@127.0.0.1:{args.db_port}/morgenruf",
        APP_URL=args.app_url,
        PORT=str(args.backend_port),
        SESSION_COOKIE_SECURE="true" if urlsplit(args.app_url).scheme == "https" else "false",
    )
    if not os.environ.get("FLASK_SECRET_KEY", "").strip():
        os.environ["FLASK_SECRET_KEY"] = local_secret()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_environment(args)
    app_directory = ROOT / "app"
    sys.path.insert(0, str(app_directory))
    os.chdir(app_directory)

    if args.command == "migrate":
        importlib.import_module("src.core.migrations_runner").run_migrations()
    else:
        _, flask_app = importlib.import_module("src.main").create_app()
        # Tilt restarts this process when source changes. Werkzeug's reloader
        # would initialize Slack and the scheduler twice.
        flask_app.run(host="127.0.0.1", port=args.backend_port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
