"""Tests for the gallery renderer and ``Graph.gallery()``."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity
from crategraph.renderers.gallery import GalleryRenderer, _gallery_items


def _png_bytes() -> bytes:
    """A few bytes with a PNG-ish signature (content is never decoded)."""
    return b"\x89PNG\r\n\x1a\n fake image payload"


def _thumbnail_graph(tmp_path: Path) -> Graph:
    """A crate whose objects carry a ``thumbnail`` property."""
    imgs = tmp_path / "files"
    imgs.mkdir()
    (imgs / "a.jpg").write_bytes(_png_bytes())
    (imgs / "b.jpg").write_bytes(_png_bytes())
    (imgs / "c.jpg").write_bytes(_png_bytes())
    g = Graph(source=str(tmp_path))
    g._add_node(
        Entity(
            id="#o1",
            types=["RepositoryObject"],
            properties={
                "name": "Sunrise",
                "place": "Hill",
                "description": "A sunrise",
                "thumbnail": "files/a.jpg",
            },
        )
    )
    g._add_node(
        Entity(
            id="#o2",
            types=["RepositoryObject"],
            properties={
                "name": "Sunset",
                "place": "Vale",
                "description": "A sunset",
                "thumbnail": {"@id": "files/b.jpg"},
            },
        )
    )
    g._add_node(
        Entity(
            id="#o3",
            types=["RepositoryObject"],
            properties={"name": "Noon", "thumbnail": "files/c.jpg"},
        )
    )
    return g


def _image_file_graph(tmp_path: Path) -> Graph:
    """A crate whose images are bare image ``File`` entities (no thumbnails)."""
    (tmp_path / "p.png").write_bytes(_png_bytes())
    (tmp_path / "q.png").write_bytes(_png_bytes())
    (tmp_path / "notes.txt").write_bytes(b"hello")
    g = Graph(source=str(tmp_path))
    g._add_node(
        Entity(
            id="p.png",
            types=["File"],
            properties={"name": "p.png", "encodingFormat": "image/png"},
        )
    )
    g._add_node(
        Entity(
            id="q.png",
            types=["File"],
            properties={"name": "q.png", "encodingFormat": "image/png"},
        )
    )
    g._add_node(
        Entity(
            id="notes.txt",
            types=["File"],
            properties={"name": "notes.txt", "encodingFormat": "text/plain"},
        )
    )
    return g


def _many_thumbnail_graph(tmp_path: Path, n: int) -> Graph:
    """A crate with *n* thumbnail-bearing objects (for limit/warning tests)."""
    imgs = tmp_path / "files"
    imgs.mkdir()
    g = Graph(source=str(tmp_path))
    for i in range(n):
        (imgs / f"{i}.jpg").write_bytes(_png_bytes())
        g._add_node(
            Entity(
                id=f"#o{i}",
                types=["RepositoryObject"],
                properties={"name": f"Photo {i}", "thumbnail": f"files/{i}.jpg"},
            )
        )
    return g


class TestGalleryItems:
    def test_finds_thumbnail_entities(self, tmp_path):
        items = _gallery_items(_thumbnail_graph(tmp_path))
        assert len(items) == 3
        assert all(path.is_file() for _, path, _ in items)
        assert all(media.startswith("image/") for _, _, media in items)

    def test_falls_back_to_image_files(self, tmp_path):
        items = _gallery_items(_image_file_graph(tmp_path))
        ids = {entity.id for entity, _, _ in items}
        assert ids == {"p.png", "q.png"}  # the text file is excluded

    def test_collects_all_candidates(self, tmp_path):
        # _gallery_items no longer caps; the limit lives at the render layer.
        assert len(_gallery_items(_many_thumbnail_graph(tmp_path, 130))) == 130


class TestRender:
    def test_one_img_per_item(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path)).data
        assert html.count("<img ") == 3
        assert html.count("data:image/") == 3
        assert "base64," in html

    def test_columns_in_css(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path), columns=3).data
        assert "repeat(3," in html

    def test_images_not_cropped(self, tmp_path):
        # Tall documents must show whole, not be squared off and cropped.
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path)).data
        assert "object-fit:cover" not in html
        assert "aspect-ratio:1" not in html
        assert "minmax(0,1fr)" in html  # columns divide evenly without overflow
        assert "height:auto" in html

    def test_caption_default_is_label(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path)).data
        assert "Sunrise" in html
        assert "<figcaption" in html

    def test_caption_property(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path), caption="place").data
        assert "Hill" in html
        assert "Vale" in html

    def test_caption_none_omits_figcaption(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path), caption=None).data
        assert "<figcaption" not in html

    def test_hover_shows_overlay(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path), hover="description").data
        assert 'class="cg-hover"' in html
        assert ">A sunrise<" in html

    def test_hover_joins_multiple(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path), hover=["name", "place"]).data
        assert ">Sunrise · Hill<" in html

    def test_hover_default_absent(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path)).data
        assert '<span class="cg-hover">' not in html  # the CSS rule may still define it

    def test_captions_wrap_not_truncated(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path)).data
        assert "white-space:nowrap" not in html
        assert "text-overflow:ellipsis" not in html

    def test_limit(self, tmp_path):
        with pytest.warns(UserWarning, match="1 of 3"):
            html = GalleryRenderer().render(_thumbnail_graph(tmp_path), limit=1).data
        assert html.count("<img ") == 1

    def test_default_limit_caps(self, tmp_path):
        g = _many_thumbnail_graph(tmp_path, 130)
        with pytest.warns(UserWarning, match="first 48 of 130"):
            html = GalleryRenderer().render(g).data
        assert html.count("<img ") == 48

    def test_no_warning_within_limit(self, tmp_path):
        g = _thumbnail_graph(tmp_path)  # 3 items, well under the default cap
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            html = GalleryRenderer().render(g).data
        assert html.count("<img ") == 3

    def test_limit_none_embeds_all_without_warning(self, tmp_path):
        g = _many_thumbnail_graph(tmp_path, 130)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            html = GalleryRenderer().render(g, limit=None).data
        assert html.count("<img ") == 130

    def test_filepath_writes_and_returns_path(self, tmp_path):
        out = tmp_path / "gallery.html"
        result = GalleryRenderer().render(_thumbnail_graph(tmp_path), filepath=str(out))
        assert result == str(out)
        assert out.is_file()
        text = out.read_text()
        assert "<img " in text
        assert "cg-gallery" in text

    def test_empty_graph_placeholder(self, tmp_path):
        html = GalleryRenderer().render(Graph(source=str(tmp_path))).data
        assert "<img " not in html
        assert "No images" in html

    def test_escapes_caption(self, tmp_path):
        g = _thumbnail_graph(tmp_path)
        g._entities["#o1"].properties["name"] = "<b>x</b>"
        html = GalleryRenderer().render(g).data
        assert "<b>x</b>" not in html
        assert "&lt;b&gt;" in html


class TestItemDetectionEdgeCases:
    def test_multicrate_uses_entity_source(self, tmp_path):
        imgs = tmp_path / "files"
        imgs.mkdir()
        (imgs / "a.jpg").write_bytes(_png_bytes())
        g = Graph(source=None)  # multi-crate: no graph-level source
        g._add_node(
            Entity(
                id="#o1",
                types=["RepositoryObject"],
                source=str(tmp_path),
                properties={"name": "X", "thumbnail": "files/a.jpg"},
            )
        )
        items = _gallery_items(g)
        assert len(items) == 1

    def test_thumbnail_list_skips_missing(self, tmp_path):
        (tmp_path / "real.jpg").write_bytes(_png_bytes())
        g = Graph(source=str(tmp_path))
        g._add_node(
            Entity(
                id="#o1",
                types=["RepositoryObject"],
                properties={"name": "X", "thumbnail": ["files/missing.jpg", "real.jpg"]},
            )
        )
        items = _gallery_items(g)
        assert len(items) == 1
        assert items[0][1].name == "real.jpg"

    def test_extensionless_image_file_via_encoding_format(self, tmp_path):
        (tmp_path / "scan").write_bytes(_png_bytes())  # no extension
        g = Graph(source=str(tmp_path))
        g._add_node(
            Entity(
                id="scan",
                types=["File"],
                properties={"name": "scan", "encodingFormat": "image/jpeg"},
            )
        )
        items = _gallery_items(g)
        assert len(items) == 1
        assert items[0][2] == "image/jpeg"

    def test_non_data_entity_not_used_as_image(self, tmp_path):
        (tmp_path / "x.png").write_bytes(_png_bytes())
        g = Graph(source=str(tmp_path))
        # id resolves to an image path, but the entity is not a data entity
        g._add_node(Entity(id="x.png", types=["Place"], properties={"name": "Somewhere"}))
        assert _gallery_items(g) == []

    def test_limit_zero_renders_empty(self, tmp_path):
        g = _thumbnail_graph(tmp_path)
        assert "No images" in GalleryRenderer().render(g, limit=0).data

    def test_columns_clamped_to_one(self, tmp_path):
        html = GalleryRenderer().render(_thumbnail_graph(tmp_path), columns=0).data
        assert "repeat(1," in html

    def test_render_skips_file_that_fails_to_read(self, tmp_path, monkeypatch):
        g = _thumbnail_graph(tmp_path)
        bad = (tmp_path / "files" / "a.jpg").resolve()
        real_read = Path.read_bytes

        def fake_read(self):
            if self.resolve() == bad:
                raise OSError("boom")
            return real_read(self)

        monkeypatch.setattr(Path, "read_bytes", fake_read)
        html = GalleryRenderer().render(g).data
        assert html.count("<img ") == 2


class TestGraphGallery:
    def test_graph_gallery_returns_html(self, tmp_path):
        result = _thumbnail_graph(tmp_path).gallery()
        assert result.data.count("<img ") == 3

    def test_graph_gallery_filepath(self, tmp_path):
        out = tmp_path / "g.html"
        assert _thumbnail_graph(tmp_path).gallery(filepath=str(out)) == str(out)
        assert out.is_file()

    def test_graph_gallery_default_limit(self):
        import inspect

        assert inspect.signature(Graph.gallery).parameters["limit"].default == 48

    def test_graph_gallery_warns_over_limit(self, tmp_path):
        g = _many_thumbnail_graph(tmp_path, 130)
        with pytest.warns(UserWarning, match="first 48 of 130"):
            result = g.gallery()
        assert result.data.count("<img ") == 48
