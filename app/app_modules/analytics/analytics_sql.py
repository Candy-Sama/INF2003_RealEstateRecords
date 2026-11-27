"""Validate and run user-written SQL for analytics cards.
What this module does to every query:

1. Rejects anything that is not a single SELECT / WITH statement.
2. Rejects comments, user variables (@), quoted identifiers with odd characters,
   write/DDL/admin keywords, file and locking functions, and any mention of the
   `agents` table, `password_hash`, or system schemas.
3. Wraps the query so MySQL itself caps the rows returned.
4. Runs it in a READ ONLY transaction with a server-side time limit, then rolls back.

Queries are executed with no bound parameters, so `%` in LIKE patterns is safe.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

MAX_SQL_CHARS = 5000
MAX_ROWS = 5000
TIMEOUT_MS = 15_000


class QueryRejected(ValueError):
    """The SQL failed a safety check. The message is safe to show to the user."""


# Words that must never appear outside a string literal.
_FORBIDDEN_WORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "CALL", "SET", "LOCK", "UNLOCK", "LOAD", "HANDLER", "DO",
    "PREPARE", "EXECUTE", "DEALLOCATE", "INTO", "OUTFILE", "DUMPFILE", "OPTIMIZE",
    "ANALYZE", "FLUSH", "KILL", "SHUTDOWN", "USE", "SHOW", "DESCRIBE", "EXPLAIN",
    "SLEEP", "BENCHMARK", "GET_LOCK", "RELEASE_LOCK", "IS_FREE_LOCK", "IS_USED_LOCK",
    "LOAD_FILE", "DATABASE", "SCHEMA", "USER", "CURRENT_USER", "SESSION_USER",
    "SYSTEM_USER", "VERSION", "CONNECTION_ID",
}

# Block Sensitive objects
_BLOCKED_IDENTIFIERS = {
    "agents", "password_hash", "information_schema", "mysql",
    "performance_schema", "sys", "estaterecordsdb",
}

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_START = re.compile(r"^[\s(]*(SELECT|WITH)\b", re.IGNORECASE)


def _mask(sql: str) -> str:
    """Return `sql` with string literals blanked and backticks removed.

    Raises QueryRejected for comments, unterminated strings and odd identifiers.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while True:
                if i >= n:
                    raise QueryRejected("A string literal is not closed.")
                c = sql[i]
                if c == "\\":
                    i += 2
                    continue
                if c == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # doubled quote
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append("''")
            continue
        if ch == "`":
            end = sql.find("`", i + 1)
            if end == -1:
                raise QueryRejected("A quoted identifier is not closed.")
            name = sql[i + 1 : end]
            if not re.fullmatch(r"[A-Za-z0-9_$]+", name):
                raise QueryRejected(
                    "Quoted identifiers may only contain letters, digits, _ and $."
                )
            out.append(name)
            i = end + 1
            continue
        if ch == "#" or sql.startswith("--", i) or sql.startswith("/*", i):
            raise QueryRejected("Comments are not allowed in analytics queries.")
        out.append(ch)
        i += 1
    return "".join(out)


def validate_query(sql: Any) -> str:
    """Return the cleaned query (no trailing semicolon) or raise QueryRejected."""
    if not isinstance(sql, str):
        raise QueryRejected("The query must be text.")
    sql = sql.strip()
    if not sql:
        raise QueryRejected("Enter a SQL query.")
    if len(sql) > MAX_SQL_CHARS:
        raise QueryRejected(f"The query is longer than {MAX_SQL_CHARS:,} characters.")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in sql):
        raise QueryRejected("The query contains control characters.")

    masked = _mask(sql)

    # One trailing semicolon is fine; anything else means several statements.
    if masked.rstrip().endswith(";"):
        sql = sql.rstrip()[:-1].rstrip()
        masked = masked.rstrip()[:-1]
    if ";" in masked:
        raise QueryRejected("Only one statement is allowed.")
    if "@" in masked:
        raise QueryRejected("User and system variables (@) are not allowed.")
    if not _START.match(masked):
        raise QueryRejected("Only SELECT queries (optionally starting with WITH) are allowed.")

    for word in _WORD.findall(masked):
        if word.upper() in _FORBIDDEN_WORDS:
            raise QueryRejected(f"`{word.upper()}` is not allowed in analytics queries.")
        if word.lower() in _BLOCKED_IDENTIFIERS:
            raise QueryRejected(f"`{word}` is not available to analytics queries.")
    if not sql:
        raise QueryRejected("Enter a SQL query.")
    return sql


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Turn Decimal and date values into types charts understand."""
    for column in frame.columns:
        series = frame[column]
        if series.dtype != object:
            continue
        first = next((v for v in series if v is not None), None)
        try:
            if isinstance(first, Decimal):
                frame[column] = pd.to_numeric(series)
            elif isinstance(first, (date, datetime)):
                frame[column] = pd.to_datetime(series)
            elif isinstance(first, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", first):
                frame[column] = pd.to_datetime(series, format="%Y-%m-%d")
        except (ValueError, TypeError):
            pass  # leave the column as it came back
    return frame


def bounded_select(sql: str) -> str:
    return f"SELECT * FROM ({validate_query(sql)}) AS analytics_q LIMIT {MAX_ROWS + 1}"


def run_query(connection: Any, sql: str) -> tuple[pd.DataFrame, bool]:
    """
    Validate and run `sql`. Returns (rows as a DataFrame, was_truncated). Note that an
    ORDER BY is only guaranteed to survive the wrapper when it has a LIMIT.
    """
    wrapped = bounded_select(sql)
    with connection.cursor() as cursor:
        cursor.execute(f"SET SESSION max_execution_time = {int(TIMEOUT_MS)}")
        connection.start_transaction(readonly=True)
        try:
            cursor.execute(wrapped)
            rows = cursor.fetchall()
            columns = list(cursor.column_names)
        finally:
            connection.rollback()
    truncated = len(rows) > MAX_ROWS
    frame = pd.DataFrame(rows[:MAX_ROWS], columns=columns)
    return _normalise(frame), truncated
