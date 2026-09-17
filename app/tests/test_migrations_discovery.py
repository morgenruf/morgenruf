"""Migration discovery across core and module directories."""

from __future__ import annotations

import pathlib

import pytest
from src.core.migrations_runner import assert_unique_basenames, collect_migration_files


def write(tmp_path: pathlib.Path, rel: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("SELECT 1;")
    return p


def test_collects_from_core_and_modules_sorted_by_basename(tmp_path):
    write(tmp_path, "core/002_b.sql")
    write(tmp_path, "core/001_a.sql")
    write(tmp_path, "connect/003_c.sql")
    found = collect_migration_files(tmp_path / "core", [tmp_path / "connect"])
    assert [pathlib.Path(f).name for f in found] == ["001_a.sql", "002_b.sql", "003_c.sql"]


def test_extra_dir_is_included_for_self_hosted_overrides(tmp_path):
    write(tmp_path, "core/001_a.sql")
    write(tmp_path, "extra/999_z.sql")
    found = collect_migration_files(tmp_path / "core", [], extra_dir=tmp_path / "extra")
    assert [pathlib.Path(f).name for f in found] == ["001_a.sql", "999_z.sql"]


def test_missing_directory_is_ignored(tmp_path):
    write(tmp_path, "core/001_a.sql")
    found = collect_migration_files(tmp_path / "core", [tmp_path / "does_not_exist"])
    assert len(found) == 1


def test_duplicate_basenames_raise():
    with pytest.raises(ValueError, match="001_a.sql"):
        assert_unique_basenames(["/x/core/001_a.sql", "/x/connect/001_a.sql"])


def test_unique_basenames_pass():
    assert assert_unique_basenames(["/x/core/001_a.sql", "/x/connect/002_b.sql"]) is None


def test_shipped_migrations_have_unique_basenames():
    """Guards the real tree: schema_migrations is keyed on the bare basename."""
    root = pathlib.Path(__file__).resolve().parents[1] / "src"
    paths = [str(p) for p in root.rglob("migrations/*.sql")]
    assert paths, "expected to find shipped migrations"
    assert_unique_basenames(paths)
