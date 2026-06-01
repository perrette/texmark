import panflute as pf
import pytest
from texmark.filters.embed import embed_filter


def run_filter(doc):
    return pf.run_filter(embed_filter, doc=doc)


def test_image_para_rewritten_to_input():
    doc = pf.Doc(pf.Para(pf.Image(url='chapter1.md')))
    doc = run_filter(doc)
    assert len(doc.content) == 1
    block = doc.content[0]
    assert isinstance(block, pf.RawBlock)
    assert block.text == '\\input{chapter1}\n'
    assert block.format == 'latex'


def test_image_case_insensitive_extension():
    doc = pf.Doc(pf.Para(pf.Image(url='chapter1.MD')))
    doc = run_filter(doc)
    assert isinstance(doc.content[0], pf.RawBlock)
    assert '\\input{chapter1}' in doc.content[0].text


def test_remote_md_url_not_rewritten():
    doc = pf.Doc(pf.Para(pf.Image(url='https://example.com/chapter1.md')))
    doc = run_filter(doc)
    assert isinstance(doc.content[0], pf.Para)
    assert isinstance(doc.content[0].content[0], pf.Image)


def test_non_md_image_not_rewritten():
    doc = pf.Doc(pf.Para(pf.Image(url='figure.png')))
    doc = run_filter(doc)
    assert isinstance(doc.content[0], pf.Para)
    assert isinstance(doc.content[0].content[0], pf.Image)


def test_image_with_other_inlines_not_rewritten():
    doc = pf.Doc(pf.Para(pf.Str('See'), pf.Space(), pf.Image(url='chapter1.md')))
    doc = run_filter(doc)
    assert isinstance(doc.content[0], pf.Para)


def test_stem_extraction_from_subpath():
    doc = pf.Doc(pf.Para(pf.Image(url='chapters/intro.md')))
    doc = run_filter(doc)
    block = doc.content[0]
    assert isinstance(block, pf.RawBlock)
    assert block.text == '\\input{intro}\n'


def test_import_smoke():
    from texmark.filters.embed import embed_filter as ef
    assert callable(ef)
