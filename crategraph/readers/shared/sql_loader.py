"""SQL loader — TabularGraphReader subclass that reads PostgreSQL dumps via sqlite3.

Uses only Python standard library (sqlite3, re, pathlib). No external
dependencies required.
"""

from __future__ import annotations

import re
import sqlite3
import warnings
from pathlib import Path
from typing import Any

from crategraph.core.graph import Graph
from crategraph.readers.shared.tabular import TabularGraphReader


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


# --- sqlite3 authoriser ---

_ALLOWED_SQL_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_TRANSACTION,
        # Required internally by SQLite for DDL (sqlite_master updates,
        # DROP TABLE IF EXISTS cleanup) and built-in functions (UPPER).
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_FUNCTION,
    }
)


def sql_authoriser(
    action: int, arg1: str | None, arg2: str | None, db_name: str | None, trigger: str | None
) -> int:
    """Restrict SQL operations to a safe subset for loading data.

    Allows DDL (CREATE/DROP TABLE/INDEX), DML (INSERT, SELECT/READ,
    UPDATE, DELETE), transactions, and built-in functions. UPDATE and
    DELETE are needed internally by SQLite for DDL bookkeeping
    (sqlite_master) and DROP TABLE cleanup. FUNCTION is needed for
    built-in functions like UPPER().

    Denies ATTACH, DETACH, PRAGMA, and everything else.
    """
    if action in _ALLOWED_SQL_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


# --- SqlGraphReader ---


class SqlGraphReader(TabularGraphReader):
    """Read a directory of PostgreSQL SQL dump files into a Graph.

    Preprocesses PostgreSQL-dialect SQL into SQLite-compatible SQL,
    executes it in an in-memory sqlite3 database with a restrictive
    authoriser, then queries tables to build the graph.

    Uses only Python standard library — no external dependencies.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._conn: sqlite3.Connection | None = None

    def can_read(self, path: str) -> bool:
        """Return True if *path* is a directory containing SQL with matching tables."""
        p = Path(path)
        if not p.is_dir():
            return False
        expected = self._all_table_names()
        if not expected:
            return False
        sql_files = list(p.rglob("*.sql"))
        if not sql_files:
            return False
        # Check if any SQL file references a configured table.
        for sql_file in sql_files:
            content = sql_file.read_text(errors="replace").upper()
            for table_name in expected:
                if f"INSERT INTO {table_name}" in content:
                    return True
        return False

    def read(self, path: str) -> Graph:
        """Read SQL dump files at *path* and return a populated Graph."""
        self._conn = self._build_database(Path(path))
        try:
            return super().read(path)
        finally:
            self._conn.close()
            self._conn = None

    def _load_table(self, table_name: str) -> list[dict[str, Any]] | None:
        """Query a table from the in-memory database, returning rows as dicts."""
        assert self._conn is not None
        # Find the table (case-insensitive).
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND UPPER(name)=?",
            (table_name.upper(),),
        )
        result = cursor.fetchone()
        if result is None:
            warnings.warn(
                f"SQL table '{table_name}' not found — skipping.",
                stacklevel=3,
            )
            return None
        actual_name = result[0]
        cursor = self._conn.execute(f"SELECT * FROM [{actual_name}]")
        columns = [desc[0].upper() for desc in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    def _build_database(self, root: Path) -> sqlite3.Connection:
        """Read SQL files, preprocess, and execute into an in-memory database."""
        conn = sqlite3.connect(":memory:")
        conn.set_authorizer(sql_authoriser)
        sql = self._collect_sql(root)
        sql = preprocess_postgresql(sql)
        conn.executescript(sql)
        return conn

    def _collect_sql(self, root: Path) -> str:
        """Collect SQL from files in *root*, resolving ``\\i`` includes.

        Looks for an ``initialise*.sql`` entry point first. Falls back to
        concatenating all ``.sql`` files.
        """
        root_resolved = root.resolve(strict=False)
        init_files = list(root.glob("initialise*.sql"))
        if init_files:
            return self._resolve_includes(
                init_files[0],
                root_dir=root_resolved,
                visited=set(),
            )
        # Fallback: concatenate all SQL files.
        parts = []
        for sql_file in sorted(root.glob("*.sql")):
            parts.append(sql_file.read_text(errors="replace"))
        return "\n".join(parts)

    @staticmethod
    def _resolve_includes(
        sql_file: Path,
        *,
        root_dir: Path,
        visited: set[Path],
    ) -> str:
        """Read a SQL file, recursively resolving crate-local ``\\i`` directives."""
        sql_file_resolved = sql_file.resolve(strict=False)
        if sql_file_resolved in visited:
            msg = f"Recursive SQL include detected for '{sql_file_resolved}'."
            raise ValueError(msg)

        try:
            sql_file_resolved.relative_to(root_dir)
        except ValueError as exc:
            msg = f"SQL include '{sql_file_resolved}' resolves outside the import root."
            raise ValueError(msg) from exc

        visited.add(sql_file_resolved)
        lines: list[str] = []
        try:
            for line in sql_file_resolved.read_text(errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("\\i "):
                    include_name = stripped[3:].strip()
                    include_path = (sql_file_resolved.parent / include_name).resolve(strict=False)
                    if include_path.exists():
                        lines.append(
                            SqlGraphReader._resolve_includes(
                                include_path,
                                root_dir=root_dir,
                                visited=visited,
                            )
                        )
                else:
                    lines.append(line)
            return "\n".join(lines)
        finally:
            visited.remove(sql_file_resolved)
