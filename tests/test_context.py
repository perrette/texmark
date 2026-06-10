"""Tests for texmark/context.py — BuildContext metadata round-trip."""

import io

import panflute as pf
import pytest

from texmark.context import BuildContext, METADATA_KEY
from tests import pandoc_available


def test_defaults_without_metadata():
    ctx = BuildContext.from_doc(pf.Doc())
    assert ctx.build_dir == 'build'
    assert ctx.project_root is None
    assert ctx.copy_figures is False
    assert ctx.embed_depth == 0
    assert ctx.crossref_companion_stems == []


def test_from_doc_reads_plain_dict_metadata():
    ctx_in = BuildContext(
        build_dir='/tmp/b', source_dir='/tmp/s', cwd='/tmp',
        project_root='/tmp/root', copy_figures=True,
        figure_folders=['/tmp/figs'],
        crossref_companion_stems=['si'], crossref_own_stem='main',
        figure_manifest_accumulate=True, embed_depth=1,
        filters_module='my_filters',
    )
    doc = pf.Doc(metadata={METADATA_KEY: ctx_in.to_metadata()})
    ctx_out = BuildContext.from_doc(doc)
    assert ctx_out == ctx_in


@pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")
def test_round_trip_through_pandoc_json():
    """The context must survive the YAML -> pandoc -> JSON AST round-trip
    that subprocess filters see (where every scalar arrives stringly)."""
    import frontmatter
    import pypandoc

    ctx_in = BuildContext(
        build_dir='/tmp/b', source_dir='/tmp/s', cwd='/tmp',
        project_root='/tmp/root', copy_figures=True,
        figure_folders=['/tmp/figs1', '/tmp/figs2'],
        crossref_companion_stems=['si'], crossref_embed_stems=['ch1', 'ch2'],
        crossref_own_stem='main',
        figure_manifest_accumulate=False, embed_depth=1,
    )
    post = frontmatter.Post("Body text.", **{METADATA_KEY: ctx_in.to_metadata()})
    ast_json = pypandoc.convert_text(
        frontmatter.dumps(post), format="markdown", to="json")
    doc = pf.load(io.StringIO(ast_json))
    ctx_out = BuildContext.from_doc(doc)
    assert ctx_out == ctx_in
