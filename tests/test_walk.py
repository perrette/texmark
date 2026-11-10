"""texmark.walk and texmark.chain give the same document as panflute's own
walk, one filter at a time."""
import json
from pathlib import Path

import panflute as pf
import pytest

from texmark import chain, journals, walk
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")


# Exercises the filters that share walks: embeds, equations and their
# references, leading-slash links, figures, tables with citations, sections.
FILTER_SAMPLE = r"""---
figure-span: column
---

# Abstract

An abstract citing @smith2020.

# Introduction

See [the methods](/methods.md), @fig:eofmean, [@eq:one; @eq:two] and
[see @tbl:t1, left]. A [link](#sec:intro) and an empty one [](#eq:one).

![](chapter.md)

$$ a = b $$

{#eq:one}
where $a$ is something [@jones2019].

Prose before
$$
\begin{aligned} x &= 1 \\ y &= 2 \end{aligned}
$$

{#eq:two .align}

[![](/images/eof_mean.png)](#fig:eofmean)

[Chapter two](chapter2.md){.include}

![A figure [@smith2020].](/images/eof_mean.png){#fig:eofmean figure-span=full}

![Untagged figure.](images/eof_mean.png)

| Names | Values [@smith2020] |
| - | - |
| Domain | Ocean @jones2019 |
| - | - |
| Era | $x^2$ |

: A caption with $x$ and [@smith2020] {#tbl:t1 width=50%}

A footnote.[^1]

[^1]: Note with [a link](/somewhere) and @eq:one.

# Appendix

Appendix text, see @fig:eofmean.
"""


def _doc(template, text=None):
    if text is None:
        text = (REPO_ROOT / "example.md").read_text()
    doc = pf.convert_text(text, standalone=True)
    doc.metadata["journal"] = pf.MetaMap(template=pf.MetaString(template))
    return doc


TEMPLATES = ["default", "copernicus", "science", "agujournal", "pnas",
             "book", "memoir", "beamer"]


@pytest.mark.parametrize("source", ["example", "sample"])
@pytest.mark.parametrize("template", TEMPLATES)
def test_journal_chain_same_as_panflute(template, source, monkeypatch):
    """The journal chain with shared walks on texmark.walk gives the same
    document as one panflute walk per filter."""
    monkeypatch.chdir(REPO_ROOT)
    text = FILTER_SAMPLE if source == "sample" else None
    fast = journals.run_filters(_doc(template, text))
    monkeypatch.setattr(chain._walk, "run_filter", pf.run_filter)
    doc = _doc(template, text)
    slow = chain.run_chain(journals.filter_chain_for(doc), doc, fuse=False)
    assert json.dumps(fast.to_json()) == json.dumps(slow.to_json())


def _names(steps):
    return [[getattr(f, "__name__", type(f).__name__) for f in step] for step in steps]


def test_plan_groups_basic_chain():
    from texmark.filters import download_images
    steps = chain.plan([download_images.action] + journals.get_filter_chain("science"))
    assert _names(steps) == [
        ["action", "embed_filter"],
        ["CrossrefFilter", "EquationsFilter", "strip_leading_slash"],
        ["ResolveImagePathsFilter", "extract_table_identifier", "stringify_captions",
         "tag_figures", "apply_figure_defaults", "table_to_latex"],
        ["force_cite"],
        ["SectionFilter"],
        ["header_to_paragraph"],
    ]


def test_plan_unknown_and_out_of_order_filters_walk_alone():
    from texmark.filters.figures import tag_figures, apply_figure_defaults
    from texmark.filters.tabular import table_to_latex

    def custom(elem, doc):
        return None

    steps = chain.plan([tag_figures, custom, apply_figure_defaults,
                        table_to_latex, tag_figures])
    assert _names(steps) == [
        ["tag_figures"], ["custom"],
        ["apply_figure_defaults", "table_to_latex"], ["tag_figures"],
    ]


def test_shared_walk_replacement_and_list(monkeypatch):
    """After a replacement, the later filters see the new element; after a
    list, they see nothing more of that element."""
    seen = []

    def to_emph(elem, doc):
        seen.append(("to_emph", type(elem).__name__))
        if elem.text == "a":
            return pf.Emph(pf.Str("x"))

    def on_emph(elem, doc):
        seen.append(("on_emph", type(elem).__name__))
        if isinstance(elem, pf.Emph):
            return [pf.Str("y")]

    def after_list(elem, doc):
        seen.append(("after_list", type(elem).__name__))

    group = ((to_emph, (pf.Str,)), (on_emph, (pf.Emph,)),
             (after_list, (pf.Str, pf.Emph)))
    monkeypatch.setattr(chain, "_LOCAL", {id(f): (0, i, types)
                                          for i, (f, types) in enumerate(group)})
    doc = chain.run_chain([to_emph, on_emph, after_list], pf.Doc(pf.Para(pf.Str("a"))))
    assert pf.stringify(doc).strip() == "y"
    assert seen == [("to_emph", "Str"), ("on_emph", "Emph")]


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
