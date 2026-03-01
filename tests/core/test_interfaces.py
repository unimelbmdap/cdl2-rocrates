"""Tests for crategraph.core.interfaces — plugin ABCs."""

from __future__ import annotations

import pytest

from crategraph.core.interfaces import Reader, Renderer, Validator, Writer


class TestReaderABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Reader()  # type: ignore[abstract]

    def test_subclass_must_implement_methods(self):
        class IncompleteReader(Reader):
            pass

        with pytest.raises(TypeError):
            IncompleteReader()  # type: ignore[abstract]

    def test_complete_subclass(self):
        class DummyReader(Reader):
            def can_read(self, path: str) -> bool:
                return path.endswith(".json")

            def read(self, path: str):
                return None

        reader = DummyReader()
        assert reader.can_read("test.json") is True
        assert reader.can_read("test.csv") is False


class TestWriterABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Writer()  # type: ignore[abstract]

    def test_complete_subclass(self):
        class DummyWriter(Writer):
            def write(self, graph, path: str, **kwargs) -> None:
                pass

        writer = DummyWriter()
        writer.write(None, "out.json")  # should not raise


class TestValidatorABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Validator()  # type: ignore[abstract]

    def test_complete_subclass(self):
        from crategraph.core.models import ValidationReport

        class DummyValidator(Validator):
            def validate(self, graph) -> ValidationReport:
                return ValidationReport(issues=[])

        validator = DummyValidator()
        report = validator.validate(None)
        assert report.is_valid is True


class TestRendererABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Renderer()  # type: ignore[abstract]

    def test_complete_subclass(self):
        class DummyRenderer(Renderer):
            def render(self, graph, **kwargs):
                return "<html>graph</html>"

        renderer = DummyRenderer()
        assert renderer.render(None) == "<html>graph</html>"
