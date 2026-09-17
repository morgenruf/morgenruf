import glob
import os
import sys

import psycopg2


def get_migrations_dir():
    """Default to the core migrations directory that now ships inside the package.

    MIGRATIONS_DIR still wins when set, because self-hosted deployments may
    point it somewhere else.
    """
    default = os.path.join(os.path.dirname(__file__), "migrations")
    return os.environ.get("MIGRATIONS_DIR", default)


def module_migration_dirs() -> list:
    """Migration directories declared by registered modules.

    Reads the registry rather than importing any module by name, so core stays
    module-agnostic. A registry that cannot be imported yet (during the split,
    or in a trimmed deployment) simply contributes nothing.
    """
    try:
        from src.modules import REGISTRY
    except Exception:
        return []
    return [spec.migrations_dir for spec in REGISTRY if spec.migrations_dir]


def collect_migration_files(core_dir, module_dirs, extra_dir=None) -> list[str]:
    """Every .sql file across core, each module, and an optional extra directory.

    Sorted by basename, because schema_migrations is keyed on the bare
    basename and ordering must not depend on which directory a file lives in.
    """
    dirs = [core_dir, *module_dirs]
    if extra_dir:
        dirs.append(extra_dir)
    found: list[str] = []
    for d in dirs:
        if d and os.path.isdir(str(d)):
            found.extend(glob.glob(os.path.join(str(d), "*.sql")))
    return sorted(found, key=lambda p: os.path.basename(p))


def assert_unique_basenames(paths) -> None:
    """Raise if two migrations share a basename.

    schema_migrations.filename is the bare basename, so a collision across two
    module directories would make one migration silently skip.
    """
    seen: dict[str, str] = {}
    for p in paths:
        name = os.path.basename(p)
        if name in seen:
            raise ValueError(f"duplicate migration basename {name}: {seen[name]} and {p}")
        seen[name] = p


def run_migrations():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("[migrate] ERROR: DATABASE_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)

    migrations_dir = get_migrations_dir()
    migrations_dir = os.path.realpath(migrations_dir)

    if not os.path.isdir(migrations_dir):
        print(f"[migrate] ERROR: migrations directory not found: {migrations_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
    except Exception as e:
        print(f"[migrate] ERROR: could not connect to database: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.commit()

        sql_files = collect_migration_files(
            core_dir=migrations_dir,
            module_dirs=module_migration_dirs(),
            extra_dir=os.environ.get("EXTRA_MIGRATIONS_DIR"),
        )
        assert_unique_basenames(sql_files)

        for filepath in sql_files:
            filename = os.path.basename(filepath)
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (filename,))
                if cur.fetchone():
                    print(f"[migrate] Skipping {filename} (already applied)")
                    continue

            with open(filepath, "r") as f:
                sql = f.read()

            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,))
                conn.commit()
                print(f"[migrate] Applied {filename}")
            except Exception as e:
                conn.rollback()
                print(f"[migrate] ERROR: failed to apply {filename}: {e}", file=sys.stderr)
                sys.exit(1)

        print("[migrate] Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
