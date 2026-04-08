"""Tests for crategraph.readers.shared.sql_loader — SqlGraphReader."""

from __future__ import annotations

import sqlite3

import pytest

from crategraph.readers.shared.tabular import EdgeDef, NodeDef


class TestPreprocessPostgresql:
    """Unit tests for PostgreSQL → SQLite preprocessing."""

    def test_strips_e_prefix_from_strings(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        result = preprocess_postgresql("VALUES (E'hello')")
        assert result == "VALUES ('hello')"

    def test_handles_escaped_single_quote(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        result = preprocess_postgresql(r"VALUES (E'it\'s')")
        assert result == "VALUES ('it''s')"

    def test_handles_escaped_backslash(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        result = preprocess_postgresql(r"VALUES (E'back\\slash')")
        assert result == "VALUES ('back\\slash')"

    def test_strips_backslash_before_non_special_chars(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        result = preprocess_postgresql(r"VALUES (E'Bin\-Salik')")
        assert result == "VALUES ('Bin-Salik')"

    def test_adds_if_exists_to_drop_table(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        result = preprocess_postgresql("DROP TABLE ENTITY;")
        assert result == "DROP TABLE IF EXISTS ENTITY;"

    def test_removes_backslash_i_lines(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        sql = "\\i createOHRM.sql\nINSERT INTO X VALUES (1);"
        result = preprocess_postgresql(sql)
        assert "\\i" not in result
        assert "INSERT INTO X VALUES (1);" in result

    def test_preserves_null_values(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        result = preprocess_postgresql("VALUES (E'hello',NULL,E'world')")
        assert result == "VALUES ('hello',NULL,'world')"

    def test_multiple_e_strings_on_one_line(self):
        from crategraph.readers.shared.sql_loader import preprocess_postgresql

        result = preprocess_postgresql("VALUES (E'a',E'b',E'c')")
        assert result == "VALUES ('a','b','c')"


class TestSqlAuthoriser:
    """Tests for the sqlite3 authoriser that restricts operations."""

    def test_allows_create_table(self):
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert (
            sql_authoriser(sqlite3.SQLITE_CREATE_TABLE, None, None, None, None)
            == sqlite3.SQLITE_OK
        )

    def test_allows_insert(self):
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert sql_authoriser(sqlite3.SQLITE_INSERT, None, None, None, None) == sqlite3.SQLITE_OK

    def test_allows_select(self):
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert sql_authoriser(sqlite3.SQLITE_SELECT, None, None, None, None) == sqlite3.SQLITE_OK

    def test_allows_update(self):
        """UPDATE is needed internally by SQLite for DDL (sqlite_master updates)."""
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert sql_authoriser(sqlite3.SQLITE_UPDATE, None, None, None, None) == sqlite3.SQLITE_OK

    def test_allows_delete(self):
        """DELETE is needed internally by DROP TABLE IF EXISTS cleanup."""
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert sql_authoriser(sqlite3.SQLITE_DELETE, None, None, None, None) == sqlite3.SQLITE_OK

    def test_allows_function(self):
        """FUNCTION is needed for built-in functions like UPPER()."""
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert sql_authoriser(sqlite3.SQLITE_FUNCTION, None, None, None, None) == sqlite3.SQLITE_OK

    def test_denies_attach(self):
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert sql_authoriser(sqlite3.SQLITE_ATTACH, None, None, None, None) == sqlite3.SQLITE_DENY

    def test_denies_pragma(self):
        from crategraph.readers.shared.sql_loader import sql_authoriser

        assert sql_authoriser(sqlite3.SQLITE_PRAGMA, None, None, None, None) == sqlite3.SQLITE_DENY

    def test_authoriser_works_on_real_connection(self):
        """Integration test: authoriser permits basic CREATE + INSERT + SELECT."""
        from crategraph.readers.shared.sql_loader import sql_authoriser

        conn = sqlite3.connect(":memory:")
        conn.set_authorizer(sql_authoriser)
        conn.executescript("CREATE TABLE T(id TEXT PRIMARY KEY); INSERT INTO T (id) VALUES ('x');")
        result = conn.execute("SELECT * FROM T").fetchall()
        assert result == [("x",)]
        conn.close()


class TestSqlGraphReaderCanRead:
    """Tests for SqlGraphReader.can_read()."""

    def test_directory_with_matching_sql(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql_file = tmp_path / "createOHRM.sql"
        sql_file.write_text("CREATE TABLE NODES(id varchar(9), PRIMARY KEY (id));")
        data_file = tmp_path / "data.sql"
        data_file.write_text("INSERT INTO NODES (id) VALUES ('N1');")
        reader = SqlGraphReader(node_tables=[NodeDef("NODES", id_col="ID")])
        assert reader.can_read(str(tmp_path))

    def test_directory_without_sql(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        (tmp_path / "data.csv").write_text("id\n1")
        reader = SqlGraphReader(node_tables=[NodeDef("NODES", id_col="ID")])
        assert not reader.can_read(str(tmp_path))

    def test_nonexistent_path(self):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        reader = SqlGraphReader(node_tables=[NodeDef("NODES", id_col="ID")])
        assert not reader.can_read("/nonexistent/path")


class TestSqlGraphReaderRead:
    """Tests for SqlGraphReader.read() with simple SQL fixtures."""

    def _write_sql(self, tmp_path, sql):
        """Write SQL to a file and return the directory path string."""
        (tmp_path / "data.sql").write_text(sql)
        return str(tmp_path)

    def test_loads_nodes(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = """
        CREATE TABLE ITEMS(ID varchar(9), NAME varchar(50), PRIMARY KEY (ID));
        INSERT INTO ITEMS (ID, NAME) VALUES ('I1', 'First');
        INSERT INTO ITEMS (ID, NAME) VALUES ('I2', 'Second');
        """
        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        graph = reader.read(self._write_sql(tmp_path, sql))
        assert len(graph.entities) == 2
        assert "I1" in graph._entities
        assert "I2" in graph._entities

    def test_node_has_properties(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = """
        CREATE TABLE ITEMS(ID varchar(9), NAME varchar(50), PRIMARY KEY (ID));
        INSERT INTO ITEMS (ID, NAME) VALUES ('I1', 'First');
        """
        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        graph = reader.read(self._write_sql(tmp_path, sql))
        entity = graph._entities["I1"]
        assert entity.properties["NAME"] == "First"
        assert entity.properties["source_table"] == "ITEMS"

    def test_null_values_excluded_from_properties(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = """
        CREATE TABLE ITEMS(ID varchar(9), NAME varchar(50), PRIMARY KEY (ID));
        INSERT INTO ITEMS (ID, NAME) VALUES ('I1', NULL);
        """
        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        graph = reader.read(self._write_sql(tmp_path, sql))
        entity = graph._entities["I1"]
        assert "NAME" not in entity.properties

    def test_loads_edges(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = """
        CREATE TABLE NODES(ID varchar(9), PRIMARY KEY (ID));
        INSERT INTO NODES (ID) VALUES ('N1');
        INSERT INTO NODES (ID) VALUES ('N2');
        CREATE TABLE LINKS(SRC varchar(9), TGT varchar(9));
        INSERT INTO LINKS (SRC, TGT) VALUES ('N1', 'N2');
        """
        reader = SqlGraphReader(
            node_tables=[NodeDef("NODES", id_col="ID", fixed_types=["Node"])],
            edge_tables=[EdgeDef("LINKS", source_col="SRC", target_col="TGT")],
        )
        graph = reader.read(self._write_sql(tmp_path, sql))
        assert len(graph.relationships) == 1
        assert graph.relationships[0].source == "N1"
        assert graph.relationships[0].target == "N2"

    def test_column_names_case_insensitive(self, tmp_path):
        """SQL columns are lowercase but NodeDef uses uppercase — reader must normalise."""
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = """
        CREATE TABLE items(id varchar(9), name varchar(50), PRIMARY KEY (id));
        INSERT INTO items (id, name) VALUES ('I1', 'First');
        """
        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        graph = reader.read(self._write_sql(tmp_path, sql))
        assert "I1" in graph._entities

    def test_postgresql_e_strings_decoded(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = """
        CREATE TABLE ITEMS(ID varchar(9), NAME varchar(50), PRIMARY KEY (ID));
        INSERT INTO ITEMS (ID, NAME) VALUES (E'I1', E'Hello World');
        """
        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        graph = reader.read(self._write_sql(tmp_path, sql))
        assert graph._entities["I1"].properties["NAME"] == "Hello World"

    def test_resolves_backslash_i_includes(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        schema = tmp_path / "schema.sql"
        schema.write_text("CREATE TABLE ITEMS(ID varchar(9), PRIMARY KEY (ID));")
        data = tmp_path / "data.sql"
        data.write_text("INSERT INTO ITEMS (ID) VALUES ('I1');")
        init = tmp_path / "initialise.sql"
        init.write_text("\\i schema.sql\n\\i data.sql")

        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        graph = reader.read(str(tmp_path))
        assert "I1" in graph._entities

    def test_rejects_include_outside_root(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        outside = tmp_path.parent / "outside.sql"
        outside.write_text("CREATE TABLE ITEMS(ID varchar(9), PRIMARY KEY (ID));")
        init = tmp_path / "initialise.sql"
        init.write_text("\\i ../outside.sql")

        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        with pytest.raises(ValueError, match="outside the import root"):
            reader.read(str(tmp_path))

    def test_rejects_recursive_includes(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        first = tmp_path / "initialise.sql"
        second = tmp_path / "nested.sql"
        first.write_text("\\i nested.sql")
        second.write_text("\\i initialise.sql")

        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        with pytest.raises(ValueError, match="Recursive SQL include detected"):
            reader.read(str(tmp_path))

    def test_authoriser_blocks_attach(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = """
        CREATE TABLE ITEMS(ID varchar(9), PRIMARY KEY (ID));
        ATTACH DATABASE ':memory:' AS evil;
        """
        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        with pytest.raises(sqlite3.DatabaseError):
            reader.read(self._write_sql(tmp_path, sql))

    def test_missing_table_warns(self, tmp_path):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        sql = "CREATE TABLE OTHER(ID varchar(9), PRIMARY KEY (ID));"
        reader = SqlGraphReader(node_tables=[NodeDef("ITEMS", id_col="ID", fixed_types=["Item"])])
        with pytest.warns(UserWarning, match="ITEMS"):
            reader.read(self._write_sql(tmp_path, sql))
