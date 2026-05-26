"""Unit tests for the panflute filter functions used by texmark.

These exercise the in-memory transforms without needing pandoc or LaTeX.
"""
import panflute as pf
import pytest

from texmark.filters.__main__ import (
    strip_leading_slash,
    tag_figures,
    force_cite,
    apacite_cite,
    header_to_paragraph,
    header_to_unnumbered,
    extract_table_identifier,
)


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
