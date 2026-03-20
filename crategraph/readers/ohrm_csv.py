"""OHRM CSV reader — preconfigured CsvGraphReader for OHRM database exports.

Requires pandas (install via ``pip install crategraph[ohrm]``).
"""

from __future__ import annotations

from crategraph.readers.shared.csv_loader import CsvGraphReader
from crategraph.readers.shared.ohrm_tables import OHRM_TABLE_CONFIG


class OHRMCsvReader(CsvGraphReader):
    """Preconfigured CSV reader for OHRM database exports.

    Usage::

        from crategraph.readers.ohrm_csv import OHRMCsvReader

        reader = OHRMCsvReader()
        graph = reader.read("data/EMEL_CSVs/")
    """

    def __init__(self) -> None:
        super().__init__(**OHRM_TABLE_CONFIG)
