"""The Helm chart hardcodes `python src/migrate.py`, so that path must keep working.

A self-hosted user who pulls a new image while pinning an older chart would
otherwise get an initContainer that crashes, and the pod would never start.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

APP = pathlib.Path(__file__).resolve().parents[1]


def test_shim_file_exists():
    assert (APP / "src" / "migrate.py").is_file()


def test_shim_exposes_run_migrations():
    sys.path.insert(0, str(APP))
    from src.migrate import run_migrations

    assert callable(run_migrations)


def test_shim_runs_as_a_script_path():
    """Without DATABASE_URL the runner exits 1 with a clear message.

    That proves the script path resolves and reaches the real runner, which is
    what the chart depends on.
    """
    result = subprocess.run(
        [sys.executable, "src/migrate.py"],
        cwd=APP,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    assert "DATABASE_URL" in result.stderr


def test_chart_command_matches_the_shim_path():
    chart = (APP / "helm" / "morgenruf" / "templates" / "deployment.yaml").read_text()
    assert 'command: ["python", "src/migrate.py"]' in chart
