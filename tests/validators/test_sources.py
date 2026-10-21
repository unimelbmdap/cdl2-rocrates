from pathlib import Path

import pytest

from crategraph import Crate
from crategraph.core.graph import Graph
from crategraph.readers.folder import SimpleFolderReader
from crategraph.validators.sources import crate_metadata_paths

FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal-crate"
SECOND = FIXTURES / "second-crate"
META = "ro-crate-metadata.json"


def _expected(*dirs):
    return sorted((d / META).resolve() for d in dirs)


def test_single_crate_returns_its_metadata_file():
    assert crate_metadata_paths(Crate(str(MINIMAL))) == _expected(MINIMAL)


def test_multi_crate_returns_each_crate_sorted():
    graph = Crate(str(MINIMAL), str(SECOND))
    assert crate_metadata_paths(graph) == _expected(MINIMAL, SECOND)


def test_filtered_graph_still_points_at_full_source():
    graph = Crate(str(MINIMAL)).where(name="Alice Example")
    assert len(graph.entities) < len(graph._root.entities)
    assert crate_metadata_paths(graph) == _expected(MINIMAL)


def test_filtered_multi_crate_selection_keeps_all_crates():
    graph = Crate(str(MINIMAL), str(SECOND))
    one_crate = graph.where(name="Alice Smith")
    none = graph.where(name="no such name anywhere")
    assert {e.source for e in one_crate._entities.values()} == {str(MINIMAL)}
    assert len(none.entities) == 0
    assert crate_metadata_paths(one_crate) == _expected(MINIMAL, SECOND)
    assert crate_metadata_paths(none) == _expected(MINIMAL, SECOND)


def test_filtered_then_transformed_multi_crate_keeps_all_crates():
    # Transforms rebase graph._root onto the result, so only recorded paths
    # can find a crate whose entities were all filtered out.
    graph = Crate(str(MINIMAL), str(SECOND)).where(name="Alice Smith")
    annotated = graph.annotate_entities(flag=lambda e: True)
    assert annotated._root is annotated
    assert {e.source for e in annotated._entities.values()} == {str(MINIMAL)}
    assert crate_metadata_paths(annotated) == _expected(MINIMAL, SECOND)


def test_non_rocrate_graph_raises():
    graph = SimpleFolderReader().read(str(FIXTURES / "simple-folder"))
    with pytest.raises(ValueError, match="not loaded from an RO-Crate"):
        crate_metadata_paths(graph)


def test_folder_reader_over_crate_directory_raises():
    graph = SimpleFolderReader().read(str(MINIMAL))
    with pytest.raises(ValueError, match="not loaded from an RO-Crate"):
        crate_metadata_paths(graph)


def test_graph_without_source_raises():
    with pytest.raises(ValueError, match="no RO-Crate source"):
        crate_metadata_paths(Graph(metadata={"_source_format": "ro-crate"}))


def test_symlinked_metadata_file_is_validated(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    target = storage / "snapshot.json"
    target.write_text((MINIMAL / META).read_text(encoding="utf-8"), encoding="utf-8")
    crate_dir = tmp_path / "crate"
    crate_dir.mkdir()
    (crate_dir / META).symlink_to(target)
    assert crate_metadata_paths(Crate(str(crate_dir))) == [target.resolve()]


def test_dict_valued_crate_property_cannot_add_a_crate():
    graph = Crate(str(MINIMAL))
    graph.metadata["customProvenance"] = {
        "_source_format": "ro-crate",
        "_source_path": str(SECOND / META),
    }
    assert crate_metadata_paths(graph) == _expected(MINIMAL)


def test_missing_recorded_metadata_file_raises(tmp_path):
    graph = Crate(str(MINIMAL))
    graph.metadata["_source_path"] = str(tmp_path / META)
    with pytest.raises(FileNotFoundError, match=r"ro-crate-metadata\.json"):
        crate_metadata_paths(graph)


def test_legacy_graph_without_recorded_paths_falls_back_to_sources():
    single = Crate(str(MINIMAL))
    del single.metadata["_source_path"]
    assert crate_metadata_paths(single) == _expected(MINIMAL)
    multi = Crate(str(MINIMAL), str(SECOND))
    for crate_meta in multi.metadata.values():
        del crate_meta["_source_path"]
    assert crate_metadata_paths(multi) == _expected(MINIMAL, SECOND)


def test_missing_metadata_file_raises(tmp_path):
    graph = Graph(source=str(tmp_path), metadata={"_source_format": "ro-crate"})
    with pytest.raises(FileNotFoundError, match=r"ro-crate-metadata\.json"):
        crate_metadata_paths(graph)
