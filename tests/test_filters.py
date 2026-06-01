"""Unit tests for the panflute filter functions used by texmark.

These exercise the in-memory transforms without needing pandoc or LaTeX.
"""
import panflute as pf
import pytest

from texmark.filters.__main__ import (
    strip_leading_slash,
    ResolveImagePathsFilter,
    tag_figures,
    force_cite,
    apacite_cite,
    header_to_paragraph,
    header_to_unnumbered,
    extract_table_identifier,
    apply_figure_defaults,
)
from texmark.sectiontracker import SectionFilter


def make_doc():
    return pf.Doc()


# ---- strip_leading_slash --------------------------------------------------


class TestStripLeadingSlash:
    def test_strips_leading_slash_on_image(self):
        img = pf.Image(pf.Str("caption"), url="/images/x.png")
        strip_leading_slash(img, make_doc())
        assert img.url == "images/x.png"

    def test_strips_leading_slash_on_link(self):
        link = pf.Link(pf.Str("text"), url="/page")
        strip_leading_slash(link, make_doc())
        assert link.url == "page"

    def test_leaves_remote_urls_alone(self):
        img = pf.Image(pf.Str("caption"), url="https://example.com/x.png")
        strip_leading_slash(img, make_doc())
        assert img.url == "https://example.com/x.png"

    def test_leaves_relative_urls_alone(self):
        img = pf.Image(pf.Str("caption"), url="images/x.png")
        strip_leading_slash(img, make_doc())
        assert img.url == "images/x.png"


# ---- ResolveImagePathsFilter ---------------------------------------------


def _make_doc_with_images(source_dir, build_dir, image_urls, copy_figures=False):
    """Build a pf.Doc whose body contains an Image per url, plus metadata."""
    blocks = [pf.Para(pf.Image(pf.Str("c"), url=u)) for u in image_urls]
    return pf.Doc(
        *blocks,
        metadata={
            'source_dir': str(source_dir),
            'build_dir': str(build_dir),
            'copy_figures': copy_figures,
        },
    )


def _run_filter(f, doc):
    """Drive prepare/action/finalize the same way pf.run_filter would."""
    f.prepare(doc)
    doc.walk(f.action, doc=doc)
    f.finalize(doc)


def _image_urls(doc):
    urls = []
    def _collect(elem, _d):
        if isinstance(elem, pf.Image):
            urls.append(elem.url)
    doc.walk(_collect, doc=doc)
    return urls


class TestResolveImagePathsDefaultMode:
    """copy_figures=False — rewrite to point at the original on disk."""

    def test_rewrites_local_url_relative_to_build_dir(self, tmp_path):
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "fig.png").write_bytes(b"x")

        doc = _make_doc_with_images(tmp_path, build_dir, ["images/fig.png"])
        _run_filter(ResolveImagePathsFilter(), doc)
        assert _image_urls(doc) == ["../images/fig.png"]

    def test_leaves_remote_urls_alone(self, tmp_path):
        doc = _make_doc_with_images(tmp_path, tmp_path / "build",
                                    ["https://example.com/x.png"])
        _run_filter(ResolveImagePathsFilter(), doc)
        assert _image_urls(doc) == ["https://example.com/x.png"]

    def test_leaves_missing_files_alone(self, tmp_path):
        # Could be a path already rewritten by texmark-download-images;
        # the filter must not second-guess it.
        doc = _make_doc_with_images(tmp_path, tmp_path / "build",
                                    ["images/abc/downloaded.png"])
        _run_filter(ResolveImagePathsFilter(), doc)
        assert _image_urls(doc) == ["images/abc/downloaded.png"]


class TestResolveImagePathsBundleMode:
    """copy_figures=True — bundle into <build>/images/ flat, dedup, cleanup."""

    def _bundle_files(self, build_dir):
        bundle = build_dir / "images"
        if not bundle.is_dir():
            return set()
        return {p.name for p in bundle.iterdir() if p.is_file()}

    def test_simple_copy_and_rewrite(self, tmp_path):
        build_dir = tmp_path / "build"
        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "fig.png").write_bytes(b"content-A")

        doc = _make_doc_with_images(tmp_path, build_dir, ["images/fig.png"],
                                    copy_figures=True)
        _run_filter(ResolveImagePathsFilter(), doc)

        assert _image_urls(doc) == ["images/fig.png"]
        assert self._bundle_files(build_dir) == {"fig.png"}
        assert (build_dir / "images" / "fig.png").read_bytes() == b"content-A"

    def test_basename_collision_with_different_content_gets_hash_suffix(self, tmp_path):
        build_dir = tmp_path / "build"
        (tmp_path / "A").mkdir()
        (tmp_path / "B").mkdir()
        (tmp_path / "A" / "fig.png").write_bytes(b"content-A")
        (tmp_path / "B" / "fig.png").write_bytes(b"content-B")

        doc = _make_doc_with_images(tmp_path, build_dir,
                                    ["A/fig.png", "B/fig.png"],
                                    copy_figures=True)
        _run_filter(ResolveImagePathsFilter(), doc)

        urls = _image_urls(doc)
        # Both rewrites must land under images/, both must use stem-hash
        # form, and they must be distinct (different content -> different
        # hashes).
        assert all(u.startswith("images/fig-") and u.endswith(".png") for u in urls)
        assert urls[0] != urls[1]
        # Both files exist in the bundle, content preserved
        bundled = self._bundle_files(build_dir)
        assert len(bundled) == 2
        a_url, b_url = urls
        assert (build_dir / a_url).read_bytes() == b"content-A"
        assert (build_dir / b_url).read_bytes() == b"content-B"

    def test_same_file_referenced_twice_copied_once(self, tmp_path):
        build_dir = tmp_path / "build"
        (tmp_path / "A").mkdir()
        (tmp_path / "B").mkdir()
        (tmp_path / "A" / "fig.png").write_bytes(b"same")
        (tmp_path / "B" / "fig.png").write_bytes(b"same")

        doc = _make_doc_with_images(tmp_path, build_dir,
                                    ["A/fig.png", "B/fig.png"],
                                    copy_figures=True)
        _run_filter(ResolveImagePathsFilter(), doc)

        urls = _image_urls(doc)
        # Same content under same basename -> single bundled copy, both URLs collapse
        assert urls == ["images/fig.png", "images/fig.png"]
        assert self._bundle_files(build_dir) == {"fig.png"}

    def test_stale_top_level_figures_removed(self, tmp_path):
        build_dir = tmp_path / "build"
        bundle = build_dir / "images"
        bundle.mkdir(parents=True)
        # Leftover from a previous build — current doc does not reference it.
        (bundle / "stale.png").write_bytes(b"old")

        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "fig.png").write_bytes(b"new")

        doc = _make_doc_with_images(tmp_path, build_dir, ["images/fig.png"],
                                    copy_figures=True)
        _run_filter(ResolveImagePathsFilter(), doc)

        assert self._bundle_files(build_dir) == {"fig.png"}
        assert not (bundle / "stale.png").exists()

    def test_cleanup_skips_subdirectories(self, tmp_path):
        # texmark-download-images puts remote downloads under
        # build/images/<hash>/<name>. The cleanup pass must leave those
        # directories alone.
        build_dir = tmp_path / "build"
        bundle = build_dir / "images"
        (bundle / "abc123").mkdir(parents=True)
        (bundle / "abc123" / "remote.png").write_bytes(b"remote")

        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "fig.png").write_bytes(b"local")

        doc = _make_doc_with_images(tmp_path, build_dir, ["images/fig.png"],
                                    copy_figures=True)
        _run_filter(ResolveImagePathsFilter(), doc)

        assert (bundle / "abc123" / "remote.png").exists()
        assert (bundle / "fig.png").exists()

    def test_cleanup_preserves_non_figure_extensions(self, tmp_path):
        # A hand-managed README in build/images/ should not be deleted.
        build_dir = tmp_path / "build"
        bundle = build_dir / "images"
        bundle.mkdir(parents=True)
        (bundle / "NOTES.md").write_text("hand-written")

        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "fig.png").write_bytes(b"new")

        doc = _make_doc_with_images(tmp_path, build_dir, ["images/fig.png"],
                                    copy_figures=True)
        _run_filter(ResolveImagePathsFilter(), doc)

        assert (bundle / "NOTES.md").exists()


# ---- tag_figures ----------------------------------------------------------


class TestTagFigures:
    def test_tags_figure_by_image_stem(self):
        img = pf.Image(pf.Str("caption"), url="images/myfig.png")
        fig = pf.Figure(pf.Plain(img))
        tag_figures(fig, make_doc())
        assert fig.identifier == "fig:myfig"

    def test_preserves_existing_identifier(self):
        img = pf.Image(pf.Str("caption"), url="images/myfig.png")
        fig = pf.Figure(pf.Plain(img), identifier="fig:custom")
        tag_figures(fig, make_doc())
        assert fig.identifier == "fig:custom"

    def test_ignores_non_figure(self):
        img = pf.Image(pf.Str("caption"), url="images/myfig.png")
        para = pf.Para(img)
        # Should not crash and should not modify para.identifier
        tag_figures(para, make_doc())


# ---- force_cite -----------------------------------------------------------


class TestForceCite:
    def _cite(self, *keys, mode="NormalCitation"):
        citations = [pf.Citation(k, mode=mode) for k in keys]
        return pf.Cite(pf.Str(",".join(keys)), citations=citations)

    def test_single_key(self):
        out = force_cite(self._cite("knutti2008"), make_doc())
        assert isinstance(out, pf.RawInline)
        assert out.format == "latex"
        assert out.text == r"\cite{knutti2008}"

    def test_multiple_keys(self):
        out = force_cite(self._cite("a", "b", "c"), make_doc())
        assert out.text == r"\cite{a,b,c}"

    def test_force_cite_ignores_intext_mode(self):
        # force_cite always emits \cite{}, regardless of natbib mode
        out = force_cite(self._cite("k", mode="AuthorInText"), make_doc())
        assert out.text == r"\cite{k}"

    def test_non_cite_returns_none(self):
        assert force_cite(pf.Str("hello"), make_doc()) is None


# ---- apacite_cite ---------------------------------------------------------


class TestApaciteCite:
    def _cite(self, *keys, mode="NormalCitation"):
        citations = [pf.Citation(k, mode=mode) for k in keys]
        return pf.Cite(pf.Str(",".join(keys)), citations=citations)

    def test_parenthetical_maps_to_cite(self):
        # [@key] -> NormalCitation -> \cite{}
        out = apacite_cite(self._cite("k", mode="NormalCitation"), make_doc())
        assert out.text == r"\cite{k}"

    def test_intext_maps_to_citeA(self):
        # @key -> AuthorInText -> \citeA{}
        out = apacite_cite(self._cite("k", mode="AuthorInText"), make_doc())
        assert out.text == r"\citeA{k}"

    def test_multiple_keys_preserve_comma_join(self):
        out = apacite_cite(self._cite("a", "b"), make_doc())
        assert out.text == r"\cite{a,b}"

    def test_non_cite_returns_none(self):
        assert apacite_cite(pf.Str("hello"), make_doc()) is None


# ---- header_to_paragraph / header_to_unnumbered ---------------------------


class TestHeaderRewrites:
    def test_level1_to_paragraph(self):
        h = pf.Header(pf.Str("Methods"), level=1)
        out = header_to_paragraph(h, make_doc())
        assert isinstance(out, pf.RawBlock)
        assert r"\paragraph*{Methods.}" in out.text

    def test_level2_to_paragraph_too(self):
        # All header levels collapse to paragraph in Science style
        h = pf.Header(pf.Str("Sub"), level=2)
        out = header_to_paragraph(h, make_doc())
        assert r"\paragraph*{Sub.}" in out.text

    def test_unnumbered_level1_is_section(self):
        h = pf.Header(pf.Str("Intro"), level=1)
        out = header_to_unnumbered(h, make_doc())
        assert out.text == r"\section*{Intro}"

    def test_unnumbered_level2_is_subsection(self):
        h = pf.Header(pf.Str("Sub"), level=2)
        out = header_to_unnumbered(h, make_doc())
        assert out.text == r"\subsection*{Sub}"

    def test_unnumbered_level3_is_subsubsection(self):
        h = pf.Header(pf.Str("Deeper"), level=3)
        out = header_to_unnumbered(h, make_doc())
        assert out.text == r"\subsubsection*{Deeper}"


# ---- extract_table_identifier --------------------------------------------


def _table_with_caption_text(text):
    """Build a minimal panflute Table whose caption is a single Plain block of inlines."""
    inlines = []
    for i, word in enumerate(text.split()):
        if i:
            inlines.append(pf.Space())
        inlines.append(pf.Str(word))
    caption = pf.Caption(pf.Plain(*inlines))
    head = pf.TableHead(pf.TableRow(pf.TableCell(pf.Plain(pf.Str("c1")))))
    body = pf.TableBody(pf.TableRow(pf.TableCell(pf.Plain(pf.Str("v1")))))
    return pf.Table(body, head=head, caption=caption)


class TestExtractTableIdentifier:
    def test_pulls_identifier_from_caption_trailer(self):
        t = _table_with_caption_text("Caption text {#tab:gulf}")
        extract_table_identifier(t, make_doc())
        assert t.identifier == "tab:gulf"

    def test_pulls_single_class_from_caption_trailer(self):
        t = _table_with_caption_text("Caption text {.narrow}")
        extract_table_identifier(t, make_doc())
        assert "narrow" in t.classes

    def test_pulls_single_attribute_from_caption_trailer(self):
        t = _table_with_caption_text("Caption text {width=50%}")
        extract_table_identifier(t, make_doc())
        assert t.attributes.get("width") == "50%"

    @pytest.mark.xfail(
        reason=(
            "extract_table_identifier currently only inspects the last Str "
            "inline; pandoc splits attr trailers with internal whitespace "
            "across multiple Strs (e.g. {#tab:1 width=50%}), so multi-token "
            "attrs are not picked up. Known limitation."
        ),
        strict=True,
    )
    def test_pulls_multi_token_attribute_trailer(self):
        t = _table_with_caption_text("Caption text {#tab:1 width=50%}")
        extract_table_identifier(t, make_doc())
        assert t.identifier == "tab:1"
        assert t.attributes.get("width") == "50%"

    def test_caption_without_attr_unchanged(self):
        t = _table_with_caption_text("Just a caption no attrs")
        original = t.identifier
        extract_table_identifier(t, make_doc())
        assert t.identifier == original

    def test_no_caption_no_crash(self):
        head = pf.TableHead(pf.TableRow(pf.TableCell(pf.Plain(pf.Str("c1")))))
        body = pf.TableBody(pf.TableRow(pf.TableCell(pf.Plain(pf.Str("v1")))))
        t = pf.Table(body, head=head)
        extract_table_identifier(t, make_doc())  # should not raise


# ---- apply_figure_defaults ------------------------------------------------


def _figure_with_image_attrs(**attrs):
    img = pf.Image(pf.Str("caption"), url="images/x.png", attributes=attrs)
    return pf.Figure(pf.Plain(img))


class TestApplyFigureDefaults:
    def test_per_figure_span_full_wraps_in_figure_star(self):
        # Pandoc puts `figure-span=full` on the inner Image, not the Figure.
        fig = _figure_with_image_attrs(**{"figure-span": "full"})
        out = apply_figure_defaults(fig, make_doc())
        assert isinstance(out, pf.RawBlock)
        assert r"\begin{figure*}" in out.text
        assert r"\end{figure*}" in out.text

    def test_per_figure_span_column_stays_figure(self):
        fig = _figure_with_image_attrs(**{"figure-span": "column"})
        out = apply_figure_defaults(fig, make_doc())
        assert out is None  # unchanged Figure left in place

    def test_no_span_attr_leaves_figure_alone(self):
        fig = _figure_with_image_attrs()
        out = apply_figure_defaults(fig, make_doc())
        assert out is None

    def test_doc_metadata_span_full_applies_globally(self):
        doc = pf.Doc(metadata={"figure-span": "full"})
        fig = _figure_with_image_attrs()
        out = apply_figure_defaults(fig, doc)
        assert isinstance(out, pf.RawBlock)
        assert r"\begin{figure*}" in out.text

    def test_per_figure_overrides_doc_metadata(self):
        # Global says full, but this figure asks for column.
        doc = pf.Doc(metadata={"figure-span": "full"})
        fig = _figure_with_image_attrs(**{"figure-span": "column"})
        out = apply_figure_defaults(fig, doc)
        assert out is None


# ---- SectionFilter drop_sections -----------------------------------------


def _doc_with_author_contributions():
    return pf.Doc(
        pf.Header(pf.Str("Intro"), level=1, identifier="intro"),
        pf.Para(pf.Str("Body.")),
        pf.Header(pf.Str("Author"), pf.Space(), pf.Str("contributions"),
                  level=1, identifier="author-contributions"),
        pf.Para(pf.Str("A.B."), pf.Space(), pf.Str("wrote"), pf.Space(), pf.Str("it.")),
        pf.Header(pf.Str("References"), level=1, identifier="references"),
    )


class TestSectionFilterDrop:
    def test_drop_section_removes_from_body(self):
        doc = _doc_with_author_contributions()
        sf = SectionFilter(extract_sections=[], drop_sections=['author-contributions'])
        sf.prepare(doc)
        sf.finalize(doc)
        identifiers = [b.identifier for b in doc.content if isinstance(b, pf.Header)]
        assert 'author-contributions' not in identifiers
        assert identifiers == ['intro', 'references']

    def test_drop_section_not_injected_into_metadata(self):
        doc = _doc_with_author_contributions()
        sf = SectionFilter(extract_sections=[], drop_sections=['author-contributions'])
        sf.prepare(doc)
        sf.finalize(doc)
        assert 'author-contributions' not in doc.metadata
        assert 'authorcontribution' not in doc.metadata

    def test_drop_section_warns(self, caplog):
        doc = _doc_with_author_contributions()
        sf = SectionFilter(extract_sections=[], drop_sections=['author-contributions'])
        sf.prepare(doc)
        with caplog.at_level("WARNING", logger="texmark"):
            sf.finalize(doc)
        assert any("dropping section" in r.message and "Author contributions" in r.message
                   for r in caplog.records)

    def test_absent_drop_section_does_not_warn(self, caplog):
        doc = pf.Doc(
            pf.Header(pf.Str("Intro"), level=1, identifier="intro"),
            pf.Para(pf.Str("Body.")),
        )
        sf = SectionFilter(extract_sections=[], drop_sections=['author-contributions'])
        sf.prepare(doc)
        with caplog.at_level("WARNING", logger="texmark"):
            sf.finalize(doc)
        assert not any("dropping section" in r.message for r in caplog.records)
