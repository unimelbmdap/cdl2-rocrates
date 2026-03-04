"""OHRM CSV reader — preconfigured CsvGraphReader for OHRM database exports.

Requires pandas (install via ``pip install crategraph[ohrm]``).
"""

from __future__ import annotations

from crategraph.readers.csv import (
    CsvGraphReader,
    EdgeDef,
    FileEntityDef,
    LinkedMetadataDef,
    NodeDef,
)

_OHRM_NODE_TABLES = [
    NodeDef("ENTITY", id_col="EID", type_col="ETYPE"),
    NodeDef("ARCRESOURCE", id_col="ARCID", fixed_types=["ArchivalResource"]),
    NodeDef("PUBRESOURCE", id_col="PUBID", fixed_types=["PublishedResource"]),
    NodeDef("DOBJECT", id_col="DOID", fixed_types=["DigitalObject"]),
    NodeDef("REPOSITORY", id_col="REPID", fixed_types=["Repository"]),
    NodeDef("FUNCTION", id_col="FID", fixed_types=["Function"]),
]

_OHRM_EDGE_TABLES = [
    EdgeDef("RELATEDENTITY", source_col="EID", target_col="REID", type_col="RERELATIONSHIP"),
    EdgeDef("EARRSHIP", source_col="EID", target_col="ArcID", type_col="RELATIONSHIP"),
    EdgeDef("EPRRSHIP", source_col="EID", target_col="PUBID", type_col="RELATIONSHIP"),
    EdgeDef("EDORSHIP", source_col="DOID", target_col="EID", type_col="RELATIONSHIP"),
    EdgeDef("PRREPRSHIP", source_col="PUBID", target_col="REPID"),
    EdgeDef("EFRSHIP", source_col="EID", target_col="FID"),
]

_OHRM_LINKED_METADATA = [
    LinkedMetadataDef("ENTITYNAME", parent_id_col="EID", property_name="entitynames"),
    LinkedMetadataDef("ENTITYEVENT", parent_id_col="EID", property_name="entityevents"),
]

_OHRM_FILE_ENTITIES = [
    FileEntityDef(
        "DOBJECTVERSION",
        parent_id_col="DOID",
        file_path_col="DOV",
        relationship_type="hasFile",
    ),
]


class OHRMCsvReader(CsvGraphReader):
    """Preconfigured CSV reader for OHRM database exports.

    Usage::

        from crategraph.readers.ohrm_csv import OHRMCsvReader

        reader = OHRMCsvReader()
        graph = reader.read("data/EMEL_CSVs/")
    """

    def __init__(self) -> None:
        super().__init__(
            node_tables=_OHRM_NODE_TABLES,
            edge_tables=_OHRM_EDGE_TABLES,
            linked_metadata_tables=_OHRM_LINKED_METADATA,
            file_entity_tables=_OHRM_FILE_ENTITIES,
        )
