"""Central database management. Schema and migrations live in sql/ files."""

import re
import sqlite3
from pathlib import Path

from toybaru.const import DATA_DIR

SQL_DIR = Path(__file__).parent / "sql"

_query_cache: dict[str, dict[str, str]] = {}


def load_queries(db_name: str) -> dict[str, str]:
    """Load named queries from sql/{db_name}/queries.sql.

    Format: lines starting with '-- name: query_name' start a new query.
    Returns dict of name -> sql string.
    """
    if db_name in _query_cache:
        return _query_cache[db_name]

    path = SQL_DIR / db_name / "queries.sql"
    if not path.exists():
        _query_cache[db_name] = {}
        return {}

    queries = {}
    current_name = None
    current_lines = []

    for line in path.read_text().splitlines():
        m = re.match(r"^--\s*name:\s*(\w+)", line)
        if m:
            if current_name:
                queries[current_name] = "\n".join(current_lines).strip()
            current_name = m.group(1)
            current_lines = []
        else:
            current_lines.append(line)

    if current_name:
        queries[current_name] = "\n".join(current_lines).strip()

    _query_cache[db_name] = queries
    return queries


def get_db(db_name: str) -> sqlite3.Connection:
    """Open a database, create schema if needed, run pending migrations.

    Args:
        db_name: 'trips' or 'snapshots' - maps to {db_name}.db and sql/{db_name}/
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DATA_DIR / f"{db_name}.db"
    sql_dir = SQL_DIR / db_name

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # Migration tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT (datetime('now'))
        )
    """)

    # Run schema.sql if main table doesn't exist yet
    schema_file = sql_dir / "schema.sql"
    if schema_file.exists():
        # Check if the main table exists (first CREATE TABLE in schema.sql)
        schema_sql = schema_file.read_text()
        match = re.search(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)", schema_sql, re.IGNORECASE)
        if match:
            table_name = match.group(1)
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
            ).fetchone()
            if not exists:
                conn.executescript(schema_sql)
                conn.commit()

    # Run numbered migrations in order
    applied = {r[0] for r in conn.execute("SELECT name FROM _migrations").fetchall()}
    migration_files = sorted(sql_dir.glob("[0-9][0-9][0-9]_*.sql"))

    for mf in migration_files:
        if mf.name in applied:
            continue
        try:
            conn.executescript(mf.read_text())
            conn.execute("INSERT INTO _migrations (name) VALUES (?)", (mf.name,))
            conn.commit()
        except sqlite3.OperationalError as e:
            # Migration might fail if it was already applied manually (e.g. column already exists)
            # Log and mark as applied
            conn.rollback()
            conn.execute("INSERT OR IGNORE INTO _migrations (name) VALUES (?)", (mf.name,))
            conn.commit()

    return conn
