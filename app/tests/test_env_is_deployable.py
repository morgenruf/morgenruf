"""Every environment variable the code reads has to be settable on a deploy.

ZOOM_CLIENT_ID went in with the feature and appeared in no Helm template and
no .env.example, so the feature could not be switched on by any Helm install,
production included. That is the same shape as a column nothing reads: the
work is done and unreachable.

Reads the source as text. No cluster, no Helm binary.
"""

from __future__ import annotations

import pathlib
import re

APP = pathlib.Path(__file__).resolve().parent.parent
SRC = APP / "src"
CHART = APP / "helm/morgenruf"
ENV_EXAMPLE = APP / ".env.example"

# Read by the code but not set by whoever deploys it: supplied by the platform,
# by the MCP client on someone's laptop, or only meaningful in a dev checkout.
# Each entry is a deliberate exemption, not a way to silence the check.
NOT_OPERATOR_SET = {
    # The stdio MCP server runs on a developer's machine from their own MCP
    # client config, so these are theirs to set, not the cluster's.
    "MCP_TEAM_ID",
    "MORGENRUF_API_KEY",
    "PORT",
    "PATH",
    "HOME",
    "TZ",
    "PYTHONPATH",
    "PYTEST_CURRENT_TEST",
    "MIGRATIONS_DIR",
    "EXTRA_MIGRATIONS_DIR",
    "MORGENRUF_MODULES",
    "GOOGLE_CREDENTIALS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEV_MODE",
    "FLASK_ENV",
    "DB_PASSWORD",
    "POSTGRES_PASSWORD",
    "REDIS_URL",
    "DATABASE_URL",
    "SENTRY_ENV",
}

# Documented for a local checkout, deliberately absent from the chart: turning
# Flask's debugger on in a deployment is not something to make easy.
DEV_ONLY = {"FLASK_DEBUG"}

READ = re.compile(r"""os\.environ(?:\.get\(\s*["']([A-Z0-9_]+)["']|\[\s*["']([A-Z0-9_]+)["'])""")


def env_names_read() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        for a, b in READ.findall(path.read_text()):
            found.add(a or b)
    return {n for n in found if n not in NOT_OPERATOR_SET}


def chart_text() -> str:
    return "\n".join(p.read_text() for p in CHART.rglob("*.yaml"))


class TestEveryVariableCanBeSet:
    def test_the_scan_finds_something(self):
        names = env_names_read()
        assert "SLACK_CLIENT_ID" in names, "the scanner is not reading the source"

    def test_each_one_is_in_the_chart(self):
        chart = chart_text()
        missing = sorted(n for n in env_names_read() - DEV_ONLY if n not in chart)
        assert not missing, f"read by the code and not settable via Helm, so unreachable on a chart install: {missing}"

    def test_each_one_is_in_env_example(self):
        example = ENV_EXAMPLE.read_text()
        missing = sorted(n for n in env_names_read() if n not in example)
        assert not missing, f"read by the code and undocumented in .env.example: {missing}"


class TestZoomSpecifically:
    def test_it_is_optional_in_both_places(self):
        """Both halves or neither: one alone must not reference a secret key
        that the secret does not contain."""
        dep = (CHART / "templates/deployment.yaml").read_text()
        sec = (CHART / "templates/secret.yaml").read_text()
        for text in (dep, sec):
            assert "if and .Values.zoom.clientId .Values.zoom.clientSecret" in text

    def test_values_declares_it_empty_by_default(self):
        values = (CHART / "values.yaml").read_text()
        assert re.search(r"zoom:\s*\n\s*clientId:\s*\"\"\s*\n\s*clientSecret:\s*\"\"", values)

    def test_the_readme_explains_the_setup_and_the_distribution_limit(self):
        readme = (APP.parent / "README.md").read_text()
        assert "connect/zoom/callback" in readme
        assert "meeting:write:meeting" in readme
        # The constraint that decides whether customers can use it at all.
        assert "unpublished" in readme.lower()
