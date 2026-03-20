"""OHRM SQL reader — preconfigured SqlGraphReader for OHRM PostgreSQL dumps.

Uses only Python standard library (sqlite3). No external dependencies.
"""

from __future__ import annotations

from crategraph.readers.shared.ohrm_tables import OHRM_TABLE_CONFIG
from crategraph.readers.shared.sql_loader import SqlGraphReader


class OHRMSqlReader(SqlGraphReader):
    """Preconfigured SQL reader for OHRM PostgreSQL database dumps.

    Usage::

        from crategraph.readers.ohrm_sql import OHRMSqlReader

        reader = OHRMSqlReader()
        graph = reader.read("data/ohrm/AABR-ro-crate/ohrm/web/sql/")
    """

    def __init__(self) -> None:
        super().__init__(**OHRM_TABLE_CONFIG)
