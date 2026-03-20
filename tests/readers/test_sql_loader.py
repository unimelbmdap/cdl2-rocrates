"""Tests for crategraph.readers.shared.sql_loader — SqlGraphReader."""

from __future__ import annotations


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
