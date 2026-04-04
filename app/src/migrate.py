import os
import sys
import glob

import psycopg2


def get_migrations_dir():
    default = os.path.join(os.path.dirname(__file__), '..', 'migrations')
    return os.environ.get('MIGRATIONS_DIR', default)


def run_migrations():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print('[migrate] ERROR: DATABASE_URL environment variable is not set', file=sys.stderr)
        sys.exit(1)

    migrations_dir = get_migrations_dir()
    migrations_dir = os.path.realpath(migrations_dir)

    if not os.path.isdir(migrations_dir):
        print(f'[migrate] ERROR: migrations directory not found: {migrations_dir}', file=sys.stderr)
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
    except Exception as e:
        print(f'[migrate] ERROR: could not connect to database: {e}', file=sys.stderr)
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

        sql_files = sorted(glob.glob(os.path.join(migrations_dir, '*.sql')))

        for filepath in sql_files:
            filename = os.path.basename(filepath)
            with conn.cursor() as cur:
                cur.execute('SELECT 1 FROM schema_migrations WHERE filename = %s', (filename,))
                if cur.fetchone():
                    print(f'[migrate] Skipping {filename} (already applied)')
                    continue

            with open(filepath, 'r') as f:
                sql = f.read()

            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        'INSERT INTO schema_migrations (filename) VALUES (%s)',
                        (filename,)
                    )
                conn.commit()
                print(f'[migrate] Applied {filename}')
            except Exception as e:
                conn.rollback()
                print(f'[migrate] ERROR: failed to apply {filename}: {e}', file=sys.stderr)
                sys.exit(1)

        print('[migrate] Done.')
    finally:
        conn.close()


if __name__ == '__main__':
    run_migrations()
