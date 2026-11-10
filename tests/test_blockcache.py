"""Tests for the reuse of unchanged paragraphs' LaTeX (texmark/blockcache.py).

Each build of the cached project is compared with a --no-cache build of the
same sources in another build directory: the .tex must be the same, byte
for byte, whichever path the block cache took.
"""
import json
import logging
import random
import re
import sys
from pathlib import Path

import pypandoc
import pytest

import texmark.build as build
from texmark import blockcache, texcache
from texmark.project import parse_markdown
from tests import pandoc_available


pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
       b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
       b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')

CHAPTER = """\
# One {#sec:one}

Alpha paragraph with a citation [@smith2020, p. 3] and @jones2019.

Beta paragraph with a footnote.^[A note with *emphasis*.] And \\aiedit{a marker}.

Gamma paragraph, just before an equation:

$$
E = m c^2
$$

{#eq:one}
and the text after it.

Delta paragraph, after the equation paragraph.

![A caption](images/fig.png){#fig:one}

1. First item.
2. Second item with a [link](https://example.org).

> A quote.

| a | b |
|---|---|
| 1 | 2 |

: A table {#tbl:one}

Epsilon paragraph refers to @fig:one and [the section](#sec:one).

## Two

Zeta paragraph, the last one.
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "images").mkdir(parents=True)
    (src / "root.md").write_text(
        "---\ntitle: Root\njournal:\n  template: book\n---\n\nRoot text.\n\n![](ch1.md)\n")
    (src / "ch1.md").write_text(CHAPTER)
    (src / "images" / "fig.png").write_bytes(PNG)
    (src / "images" / "fig2.png").write_bytes(PNG + b"2")
    monkeypatch.chdir(tmp_path)
    return src


COPERNICUS = ("template: copernicus\nauthors:\n  - firstname: A\n    lastname: B\n"
              "    affiliation: 1\naffiliations:\n  - X")


def run(src, monkeypatch, *extra, build_dir="build"):
    """One texmark run, as a new process would see it. Returns the sources
    of the JSON -> LaTeX writer calls."""
    parse_markdown.cache_clear()
    texcache._environment.cache_clear()
    writes = []
    convert = pypandoc.convert_text

    def spy(source, *a, **k):
        if k.get("format") == "json" and k.get("to") == "latex":
            writes.append(source)
        return convert(source, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(pypandoc, "convert_text", spy)
        m.setattr(sys, "argv", ["texmark", str(src / "root.md"), "-d", build_dir, *extra])
        build.main()
    return writes


@pytest.fixture
def check(project, monkeypatch, caplog):
    """Build with the cache, then without in build-ref; assert the chapter's
    .tex is the same and return the block cache log messages."""
    caplog.set_level(logging.DEBUG, logger="texmark")

    def check(*extra):
        caplog.clear()
        writes = run(project, monkeypatch, *extra)
        logs = [r.getMessage() for r in caplog.records if r.getMessage().startswith("block cache")]
        run(project, monkeypatch, *extra, "--no-cache", build_dir="build-ref")
        assert Path("build/ch1.tex").read_bytes() == Path("build-ref/ch1.tex").read_bytes()
        return logs, writes
    return check


def edit(src, old, new):
    path = src / "ch1.md"
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))


def chapter_writes(writes):
    """The writer calls for the chapter (the root's has 'Root text')."""
    return [w for w in writes if "Root" not in w]


def test_first_build_is_full(check):
    logs, _ = check()
    assert logs == ["block cache: full conversion because there is no previous run to reuse"]


@pytest.mark.parametrize("old, new", [
    ("Alpha paragraph", "Alpha edited paragraph"),
    (" And \\aiedit{a marker}.", ""),
    ("@jones2019.", "@jones2019. A new sentence citing [@doe2021]."),
    ("with a footnote.", "with a footnote[^x].\n\n[^x]: A new footnote."),
    ("Second item", "Second edited item"),
    ("> A quote.", "> A quote, edited."),
    ("Epsilon paragraph", "Epsilon [new link](#sec:one) paragraph"),
    ("Zeta paragraph, the last one.", "Zeta paragraph, the last one.\n\nEta, a new last paragraph."),
    ("Delta paragraph", "Delta edited paragraph"),
    ("A caption", "An edited caption"),
    ("![A caption](images/fig.png){#fig:one}", "![A caption](images/fig.png){#fig:one width=50%}"),
    ("A table {#tbl:one}", "An edited table {#tbl:one}"),
    ("| 1 | 2 |", "| 1 | 3 |"),
    ("Beta paragraph", "New paragraph.\n\nBeta paragraph"),
])
def test_only_the_edited_block_is_converted(project, check, old, new):
    check()
    edit(project, old, new)
    logs, writes = check()
    assert logs[-1].startswith("block cache: converted 1 of")
    write, = chapter_writes(writes)
    # the writer saw one block (and separators), not the others
    blocks = json.loads(write)["blocks"]
    texts = [b for b in blocks if "TEXMARKBLOCK" not in json.dumps(b)]
    assert len(texts) == 1


def test_deleted_paragraph_needs_no_conversion(project, check):
    check()
    edit(project, "Beta paragraph with a footnote.^[A note with *emphasis*.] And \\aiedit{a marker}.\n\n", "")
    logs, writes = check()
    assert logs[-1].startswith("block cache: converted 0 of")
    assert chapter_writes(writes) == []


def test_unchanged_paragraphs_moved(project, check):
    check()
    edit(project, "Alpha paragraph with a citation [@smith2020, p. 3] and @jones2019.\n\n"
         "Beta paragraph with a footnote.^[A note with *emphasis*.] And \\aiedit{a marker}.",
         "Beta paragraph with a footnote.^[A note with *emphasis*.] And \\aiedit{a marker}.\n\n"
         "Alpha paragraph with a citation [@smith2020, p. 3] and @jones2019.\n\n"
         "Alpha paragraph with a citation [@smith2020, p. 3] and @jones2019.")
    logs, _ = check()
    assert logs[-1].startswith("block cache: converted 0 of")


@pytest.mark.parametrize("old, new, reason", [
    ("# One {#sec:one}", "# One edited {#sec:one}", "blocks other than self-contained"),
    ("## Two", "## Two\n\nNew.\n\n## Three", "blocks other than self-contained"),
    ("A caption](images/fig.png)", "A caption](images/fig2.png)", "images were added"),
    ("> A quote.", "> A quote.\n\n![New](images/fig2.png)", "images were added"),
    ("Gamma paragraph", "Gamma edited paragraph", "blocks other than self-contained"),
    ("and the text after it", "and the edited text after it", "blocks other than self-contained"),
    ("Second item", "Second item, see [](other.md){.include}", "blocks other than self-contained"),
    ("Zeta paragraph, the last one.", "Zeta paragraph.\n\n# Last header", "blocks other than self-contained"),
    ("# One {#sec:one}", "---\ntitle: Ch\n---\n\n# One {#sec:one}", "build settings, front matter"),
    ("> A quote.", "> A quote.\n\n---\nfoo: bar\n...", "the document metadata changed"),
])
def test_fallbacks(project, check, old, new, reason):
    check()
    edit(project, old, new)
    logs, _ = check()
    assert logs[-1].startswith("block cache: full conversion because " + reason), logs


def test_figure_caption_with_copy_figures(project, check):
    check("--copy-figures")
    edit(project, "A caption", "An edited caption")
    logs, writes = check("--copy-figures")
    assert logs[-1].startswith("block cache: converted 1 of")
    write, = chapter_writes(writes)
    assert "figures/fig.png" in write
    assert Path("build/figures/fig.png").exists()


def test_collect_figures_and_tables(project, check):
    """Figures and Tables moved to the end are never self-contained."""
    edit(project, "# One {#sec:one}",
         "---\ncollect_figures_and_tables: true\n---\n\n# One {#sec:one}")
    root = project / "root.md"
    root.write_text(root.read_text().replace("template: book", COPERNICUS))
    check()
    edit(project, "A caption", "An edited caption")
    logs, _ = check()
    assert logs[-1].startswith("block cache: full conversion because blocks other than")
    edit(project, "Alpha paragraph", "Alpha edited paragraph")
    logs, _ = check()
    assert logs[-1].startswith("block cache: converted 1 of")


def test_figure_file_change_falls_back(project, check):
    check("--copy-figures")
    edit(project, "Alpha paragraph", "Alpha edited paragraph")
    (project / "images" / "fig.png").write_bytes(PNG + b"\0")
    logs, _ = check("--copy-figures")
    assert logs[-1] == "block cache: full conversion because figure files changed"
    assert Path("build/figures/fig.png").read_bytes() == PNG + b"\0"


def test_copy_figures_incremental_keeps_outputs(project, check):
    check("--copy-figures")
    entry = json.loads(Path("build/.texmark-cache/ch1.json").read_text())
    edit(project, "Alpha paragraph", "Alpha edited paragraph")
    logs, _ = check("--copy-figures")
    assert logs[-1].startswith("block cache: converted 1 of")
    new = json.loads(Path("build/.texmark-cache/ch1.json").read_text())
    assert new["outputs"]["files"] == entry["outputs"]["files"] == {"figures/fig.png": len(PNG)}
    # and the bundled figure was not deleted (the image filters did not run)
    assert Path("build/figures/fig.png").exists()


def test_extracted_section_keeps_no_blocks(project, check):
    """A section moved into metadata (here the abstract, by copernicus) takes
    its separators with it: plain conversion, nothing recorded."""
    root = project / "root.md"
    root.write_text(root.read_text().replace(
        "template: book", COPERNICUS))
    edit(project, "# One {#sec:one}", "# Abstract\n\nThe abstract.\n\n# One {#sec:one}")
    logs, _ = check()
    assert logs[-1] == ("block cache: separators not kept by the conversion; "
                        "converting again without them")
    edit(project, "Alpha paragraph", "Alpha edited paragraph")
    logs, _ = check()
    assert logs[0] == "block cache: full conversion because the previous run recorded no blocks"


def test_metadata_from_the_document_falls_back(project, check):
    """A section of N blocks only is extracted without separators; the
    metadata then differs from that of a document of S blocks."""
    root = project / "root.md"
    root.write_text(root.read_text().replace(
        "template: book", COPERNICUS))
    edit(project, "# One {#sec:one}", "# Abstract\n\n$$x$$\n\n# One {#sec:one}")
    logs, _ = check()
    assert logs == ["block cache: full conversion because there is no previous run to reuse"]
    edit(project, "Alpha paragraph", "Alpha edited paragraph")
    logs, _ = check()
    assert logs[-1] == ("block cache: full conversion because the filters "
                        "changed the metadata differently")


def test_pandoc_args_disable(project, check):
    edit(project, "# One {#sec:one}", "---\npandoc_args: ['--wrap=none']\n---\n\n# One {#sec:one}")
    logs, _ = check()
    assert logs == ["block cache: not used because of pandoc_args"]


def test_unreadable_entry(project, check):
    check()
    path = Path("build/.texmark-cache/ch1.json")
    entry = json.loads(path.read_text())
    entry["blocks"]["nruns"] = 3
    path.write_text(json.dumps(entry))
    edit(project, "Alpha paragraph", "Alpha edited paragraph")
    logs, _ = check()
    assert logs[-1] == "block cache: full conversion because the previous entry is unreadable"


def test_no_cache_does_not_use_blocks(project, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="texmark")
    run(project, monkeypatch, "--no-cache")
    assert not any(r.getMessage().startswith("block cache") for r in caplog.records)
    assert not Path("build/.texmark-cache/ch1.json").exists()


def _classify(md):
    ast = json.loads(parse_markdown(md))
    return blockcache.classify(ast["blocks"])[1]


@pytest.mark.parametrize("md, expected", [
    ("Text.", [True]),
    ("Text [@a] and a note.^[Note.] \\raw{x}", [True]),
    ("- a\n- b\n\n> q\n\n```\ncode\n```\n\n<!-- c -->\n\n---", [True] * 5),
    ("# H\n\nText.", [False, True]),
    ("![c](a.png)\n\nText ![i](b.png).", [True, True]),
    ("![c](http://x.org/a.png)\n\n![c](a.md)\n\n[](x.md){.include}", [False] * 3),
    ("| a |\n|---|\n| 1 |", [True]),
    ("Aa.\n\nBb.\n\n$$x$$\n\nCc.\n\nDd.", [True, False, False, False, True]),
    ("Aa.\n\n- item with $$x$$\n\nBb.", [False, False, False]),
    ("[](x.md){.include}\n\n[x](x.md)", [False, True]),
    ("::: {#d}\nText.\n:::\n\n::: d\n# H\n:::", [True, False]),
])
def test_classify(md, expected):
    assert _classify(md) == expected


def test_classify_images_and_collected_figures():
    ast = json.loads(parse_markdown("![c](b.png)\n\nText ![i](a.png).\n\n| a |\n|---|\n| 1 |"))
    _, sc, images = blockcache.classify(ast["blocks"])
    assert sc == [True] * 3 and images == ["a.png", "b.png"]
    _, sc, images = blockcache.classify(ast["blocks"], figures=False)
    assert sc == [False, True, False] and images == ["a.png"]


def test_split():
    t = blockcache._TOKEN + "abcx"
    body = f"{t}0\n\nA\n\n{t}1\n\n{t}2\n\nB\nC\n\n{t}3"
    assert blockcache.split(body, t, 4) == ["", "A", "", "B\nC", ""]
    assert blockcache.join(["", "A", "", "B\nC", ""]) == "A\n\nB\nC"
    assert blockcache.split(f"A {t}0\n\nB", t, 1) is None  # not on its own
    assert blockcache.split(f"A\n\n{t}10\n\nB", t, 2) is None  # wrong number
    assert blockcache.split(f"A\n\n{t}1\n\n{t}0", t, 2) is None  # wrong order


WORDS = "sea level ocean model the of and projection uncertainty glacier".split()


def _random_edit(rng, text):
    chunks = text.split("\n\n")
    i = rng.randrange(len(chunks))
    kind = rng.choice(["word", "word", "insert", "delete", "marker", "cite", "note",
                       "dup", "swap", "math", "header", "caption"])
    if kind == "word":
        words = list(re.finditer(r"[A-Za-z]{3,}", chunks[i]))
        if words:
            m = rng.choice(words)
            chunks[i] = chunks[i][:m.start()] + rng.choice(WORDS) + chunks[i][m.end():]
    elif kind == "insert":
        chunks.insert(i + 1, " ".join(rng.choice(WORDS) for _ in range(8)).capitalize() + ".")
    elif kind == "delete" and len(chunks) > 3:
        del chunks[i]
    elif kind == "marker":
        chunks[i] = chunks[i].replace("\\aiedit{a marker}", "")
    elif kind == "cite":
        chunks[i] += " See [@smith2020]."
    elif kind == "note":
        chunks[i] += "^[A random note.]"
    elif kind == "dup":
        chunks.insert(i, chunks[i])
    elif kind == "swap" and i + 1 < len(chunks):
        chunks[i], chunks[i + 1] = chunks[i + 1], chunks[i]
    elif kind == "math":
        chunks.insert(i + 1, "$$\nx = 1\n$$")
    elif kind == "header":
        chunks.insert(i + 1, "## Header %d" % rng.randrange(100))
    elif kind == "caption":
        chunks[i] = chunks[i].replace("](images/", " %s](images/" % rng.choice(WORDS))
    return "\n\n".join(chunks)


def test_random_edits(project, check):
    """Random small edits, each build compared with a --no-cache build."""
    rng = random.Random(0)
    check()
    path = project / "ch1.md"
    incremental = 0
    for _ in range(15):
        path.write_text(_random_edit(rng, path.read_text()))
        logs, _ = check()
        incremental += any(log.startswith("block cache: converted") for log in logs)
    assert incremental >= 5


SEQUENCES = {
    "raw blocks ending in blank lines": [
        "One.\n\n```{=latex}\n\\foo\n\n\n```\n\nTwo.\n\n```{=latex}\n\\bar\n\n```\n",
        "One, edited.\n\n```{=latex}\n\\foo\n\n\n```\n\nTwo.\n\n```{=latex}\n\\bar\n\n```\n",
        "One, edited.\n\n```{=latex}\n\\foo\n\n\n```\n\nTwo.\n\n```{=latex}\n\\baz\n\n```\n",
    ],
    "empty documents and comments": ["", "Text.\n", "<!-- c -->\n", "Text.\n\n<!-- c -->\n",
                                     "Text, edited.\n\n<!-- c -->\n"],
    "last level-1 header": ["Text.\n\n# Refs\n", "Text, edited.\n\n# Refs\n",
                            "Text, edited.\n\n# Refs\n\nMore.\n", "Text.\n\n# Refs\n\nMore.\n"],
    "example list numbers": ["(@) one\n(@) two\n\nText.\n\n(@) three\n",
                             "(@) zero\n\nText 0.\n\n(@) one\n(@) two\n\nText.\n\n(@) three\n"],
    "full-width figure": ["Text.\n\n![Fig](img.png){#fig:x figure-span=full}\n\nEnd.\n",
                          "Text.\n\n![Fig 2](img.png){#fig:x figure-span=full}\n\nEnd.\n",
                          "Text.\n\n![Fig 2](img.png){#fig:x}\n\nEnd.\n"],
}


@pytest.mark.parametrize("copy_figures", [False, True])
@pytest.mark.parametrize("name", list(SEQUENCES))
def test_versions_match_plain_conversion(tmp_path, monkeypatch, name, copy_figures):
    """Each version, converted with the blocks recorded for the previous one,
    gives the .tex of a conversion without block cache. figure_folders adds a
    \\graphicspath block at the start (without --copy-figures)."""
    monkeypatch.chdir(tmp_path)
    Path("img.png").write_bytes(PNG)
    kw = dict(build_dir="b", body_only=True, embed_depth=1, figure_folders=["."],
              copy_figures=copy_figures)
    previous = None
    for text in SEQUENCES[name]:
        Path("ch.md").write_text(text)
        state = blockcache.BlockCache(previous)
        build.build_tex("ch.md", "b/ch.tex", block_cache=state, **kw)
        previous = state.entry
        build.build_tex("ch.md", "r/ch.tex", **kw)
        assert Path("b/ch.tex").read_bytes() == Path("r/ch.tex").read_bytes()
