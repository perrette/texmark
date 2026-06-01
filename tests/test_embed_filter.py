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


def test_include_link_rewritten_to_input():
    link = pf.Link(pf.Str('Chapter 1'), url='chapter1.md', classes=['include'])
    doc = pf.Doc(pf.Para(link))
    doc = run_filter(doc)
    block = doc.content[0]
    assert isinstance(block, pf.RawBlock)
    assert block.text == '\\input{chapter1}\n'
    assert block.format == 'latex'


def test_include_link_matches_image_output():
    img_doc = pf.Doc(pf.Para(pf.Image(url='chapter1.md')))
    img_doc = run_filter(img_doc)
    link_doc = pf.Doc(pf.Para(pf.Link(pf.Str('X'), url='chapter1.md', classes=['include'])))
    link_doc = run_filter(link_doc)
    assert img_doc.content[0].text == link_doc.content[0].text


def test_include_link_subpath_stem():
    link = pf.Link(pf.Str('Intro'), url='chapters/intro.md', classes=['include'])
    doc = pf.Doc(pf.Para(link))
    doc = run_filter(doc)
    assert doc.content[0].text == '\\input{intro}\n'


def test_link_without_include_class_not_rewritten():
    link = pf.Link(pf.Str('Chapter 1'), url='chapter1.md')
    doc = pf.Doc(pf.Para(link))
    doc = run_filter(doc)
    assert isinstance(doc.content[0], pf.Para)
    assert isinstance(doc.content[0].content[0], pf.Link)


def test_include_link_non_md_not_rewritten():
    link = pf.Link(pf.Str('Sheet'), url='data.csv', classes=['include'])
    doc = pf.Doc(pf.Para(link))
    doc = run_filter(doc)
    assert isinstance(doc.content[0], pf.Para)
    assert isinstance(doc.content[0].content[0], pf.Link)


def test_include_class_exact_match():
    link = pf.Link(pf.Str('X'), url='chapter1.md', classes=['includes'])
    doc = pf.Doc(pf.Para(link))
    doc = run_filter(doc)
    assert isinstance(doc.content[0], pf.Para)
