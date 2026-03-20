"""SQL loader — TabularGraphReader subclass that reads PostgreSQL dumps via sqlite3.

Uses only Python standard library (sqlite3, re, pathlib). No external
dependencies required.
"""

from __future__ import annotations

import re


def preprocess_postgresql(sql: str) -> str:
    """Convert PostgreSQL SQL to SQLite-compatible SQL.

    Handles:
    - ``E'...'`` escape strings → standard ``'...'`` with decoded escapes
    - ``DROP TABLE X`` → ``DROP TABLE IF EXISTS X``
    - ``\\i filename`` psql meta-commands → removed
    """

    def _decode_e_string(match: re.Match[str]) -> str:
        inner = match.group(1)
        # Decode PostgreSQL backslash escapes to literal values.
        inner = inner.replace("\\'", "''")  # \' → '' (SQLite quote escape)
        inner = inner.replace("\\\\", "\x00")  # \\ → placeholder
        inner = inner.replace("\\n", "\n")
        inner = inner.replace("\\r", "\r")
        inner = inner.replace("\\t", "\t")
        # Remove backslash before non-special characters (e.g. \-).
        inner = re.sub(r"\\(.)", r"\1", inner)
        inner = inner.replace("\x00", "\\")  # Restore literal backslashes.
        return f"'{inner}'"

    sql = re.sub(r"E'((?:[^'\\]|\\.)*)'", _decode_e_string, sql)
    sql = re.sub(r"DROP TABLE (\w+)", r"DROP TABLE IF EXISTS \1", sql)
    sql = re.sub(r"^\\i .*$", "", sql, flags=re.MULTILINE)
    return sql
