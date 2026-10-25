"""Read-only access to the Chinook sample database.

The analyst agent's "direct database connection". Every connection is
opened read-only, and results are capped so a careless query can't flood
the agent's context with thousands of rows.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chinook.sqlite"
MAX_ROWS = 50


def connect(path=DB_PATH):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def query(sql, max_rows=MAX_ROWS, path=DB_PATH):
    """Run one SQL statement and return {columns, rows, row_count, truncated}.

    Only reads are possible: the connection is read-only, so INSERT/UPDATE/
    DELETE fail with an error instead of changing the data.
    """
    with connect(path) as conn:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows + 1)
    truncated = len(rows) > max_rows
    rows = [list(r) for r in rows[:max_rows]]
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}


def schema(path=DB_PATH):
    """Compact schema: one line per table with its columns and row count."""
    lines = []
    with connect(path) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for t in tables:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')]
            count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            lines.append(f"{t} ({count} rows): {', '.join(cols)}")
    return "\n".join(lines)
