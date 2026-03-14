"""Tests for Corpus — multi-crate profiling."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph.core.analysis import GraphProfile
from crategraph.core.corpus import Corpus, CorpusProfile

FIXTURES = Path(__file__).parents[1] / "fixtures"
MINIMAL = str(FIXTURES / "minimal-crate")
SECOND = str(FIXTURES / "second-crate")
QUIRKY = str(FIXTURES / "quirky-crate")


class TestCorpusFromPaths:
    def test_profiles_single_crate(self):
        corpus = Corpus(MINIMAL)
        result = corpus.profile()
        assert isinstance(result, CorpusProfile)
        assert len(result.profiles) == 1

    def test_profiles_multiple_crates(self):
        corpus = Corpus(MINIMAL, SECOND)
        result = corpus.profile()
        assert len(result.profiles) == 2

    def test_profiles_are_graph_profiles(self):
        corpus = Corpus(MINIMAL)
        result = corpus.profile()
        assert isinstance(result.profiles[0], GraphProfile)

    def test_no_failures_on_valid_crates(self):
        corpus = Corpus(MINIMAL, SECOND)
        result = corpus.profile()
        assert len(result.failures) == 0


class TestCorpusFromGlob:
    def test_glob_finds_crates(self):
        pattern = str(FIXTURES / "*")
        corpus = Corpus(pattern)
        result = corpus.profile()
        assert len(result.profiles) >= 2  # minimal + second + quirky

    def test_empty_glob_raises(self):
        with pytest.raises(ValueError, match="No crates found"):
            Corpus("/nonexistent/path/*")


class TestCorpusFailureHandling:
    def test_failure_recorded_not_raised(self):
        corpus = Corpus(MINIMAL, "/nonexistent/bad-crate")
        result = corpus.profile()
        assert len(result.profiles) == 1
        assert len(result.failures) == 1

    def test_failure_contains_path_and_error(self):
        corpus = Corpus("/nonexistent/bad-crate", MINIMAL)
        result = corpus.profile()
        failure = result.failures[0]
        assert "bad-crate" in failure[0]
        assert isinstance(failure[1], str)


class TestCorpusProfileAggregate:
    def test_crate_count(self):
        corpus = Corpus(MINIMAL, SECOND)
        result = corpus.profile()
        assert result.crate_count == 2

    def test_failure_count(self):
        corpus = Corpus(MINIMAL, "/nonexistent/bad")
        result = corpus.profile()
        assert result.failure_count == 1


class TestCorpusProfileRepr:
    def test_repr_contains_count(self):
        corpus = Corpus(MINIMAL)
        r = repr(corpus.profile())
        assert "1" in r
        assert "crate" in r.lower()

    def test_repr_html_is_pre_block(self):
        corpus = Corpus(MINIMAL)
        html = corpus.profile()._repr_html_()
        assert "<pre" in html


class TestCorpusProfileToDataframe:
    def test_returns_dataframe(self):
        pd = pytest.importorskip("pandas")
        corpus = Corpus(MINIMAL, SECOND)
        df = corpus.profile().to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_dataframe_has_expected_columns(self):
        pytest.importorskip("pandas")
        corpus = Corpus(MINIMAL)
        df = corpus.profile().to_dataframe()
        assert "entity_count" in df.columns
        assert "density" in df.columns
        assert "source" in df.columns

    def test_dataframe_source_column(self):
        pytest.importorskip("pandas")
        corpus = Corpus(MINIMAL)
        df = corpus.profile().to_dataframe()
        assert df.iloc[0]["source"] is not None


class TestCorpusAllFailures:
    def test_all_failures_returns_empty_profiles(self):
        corpus = Corpus("/nonexistent/bad-crate")
        result = corpus.profile()
        assert result.crate_count == 0
        assert result.failure_count == 1


class TestCorpusInit:
    def test_no_args_raises(self):
        with pytest.raises(TypeError):
            Corpus()
