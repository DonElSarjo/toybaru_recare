"""Local audit log for high-impact remote and electric commands."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from toybaru.database import get_db as _get_db_raw


def _get_db() -> sqlite3.Connection:
    return _get_db_raw("command_audit")


def log_command(
    *,
    vin: str,
    command: str,
    request: dict[str, Any] | None,
    outcome: str,
    response_code: str | None = None,
    response_summary: str | None = None,
) -> int:
    """Append one command attempt and return its local audit identifier."""
    conn = _get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO command_audit
                (vin, command, request_json, outcome, response_code, response_summary)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                vin,
                command,
                json.dumps(request, separators=(",", ":")) if request is not None else None,
                outcome,
                response_code,
                response_summary,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def get_commands(vin: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent audit entries without exposing stored request bodies."""
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT id, vin, command, outcome, response_code, response_summary, created_at
            FROM command_audit
        """
        params: list[Any] = []
        if vin:
            sql += " WHERE vin = ?"
            params.append(vin)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
