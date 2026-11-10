"""texmark.walk gives the same document as panflute's own walk."""
import json
from pathlib import Path

import panflute as pf
import pytest

from texmark import journals, walk
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")


def _doc(template):
    doc = pf.convert_text((REPO_ROOT / "example.md").read_text(), standalone=True)
    doc.metadata["journal"] = pf.MetaMap(template=pf.MetaString(template))
    return doc


@pytest.mark.parametrize("template", ["default", "copernicus", "science", "agujournal", "book"])
def test_journal_chain_same_as_panflute(template, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    fast = journals.run_filters(_doc(template))
    monkeypatch.setattr(journals._walk, "run_filter", pf.run_filter)
    slow = journals.run_filters(_doc(template))
    assert json.dumps(fast.to_json()) == json.dumps(slow.to_json())


def _actions():
    """Actions exercising replacement, splicing, deletion and in-place edits."""
    def upper(elem, doc):
        if isinstance(elem, pf.Str):
            return pf.Str(elem.text.upper())

    def split_words(elem, doc):
        if isinstance(elem, pf.Str) and len(elem.text) > 3:
            return [pf.Str(elem.text[:2]), pf.Str(elem.text[2:])]

    def drop_emph(elem, doc):
        if isinstance(elem, pf.Emph):
            return []

    def insert_sibling(elem, doc):
        if isinstance(elem, pf.Para) and elem.index == 0 and isinstance(elem.parent, pf.Doc):
            elem.parent.content.insert(1, pf.Para(pf.Str("inserted")))

    def noop(elem, doc):
        return None

    return [noop, upper, split_words, drop_emph, insert_sibling]


@pytest.mark.parametrize("action", _actions(), ids=lambda a: a.__name__)
def test_walk_same_as_panflute(action):
    src = "# T\n\nSome *emph* text and **strong words**.\n\n- item one\n- item two\n\n> quote\n"
    a = pf.convert_text(src, standalone=True)
    b = pf.convert_text(src, standalone=True)
    a = walk.run_filter(action, doc=a)
    b = pf.run_filter(action, doc=b)
    assert json.dumps(a.to_json()) == json.dumps(b.to_json())
