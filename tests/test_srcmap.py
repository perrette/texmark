"""The source map <pdf-stem>.srcmap.json (texmark.srcmap): the heading scan,
the units and sections of a multi-file book, publishing with the PDF, and
the caches (docs/synctex-design.md).

The build tests skip when pandoc, latexmk or pdflatex is missing.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

import texmark.build as B
from texmark import srcmap
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synctex"

needs_latex = pytest.mark.skipif(
    not pandoc_available() or shutil.which("latexmk") is None
    or shutil.which("pdflatex") is None,
    reason="pandoc, latexmk or pdflatex missing",
)


@pytest.fixture(autouse=True)
def _local_texmark_on_pythonpath(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + (os.pathsep + existing if existing else ""))


def _texmark(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["texmark", *map(str, argv)])
    B.main()


def _project(tmp_path):
    """The fixture project, in a directory with a non-ASCII name, reached
    through a symlink (the map has the paths with symlinks resolved)."""
    real = tmp_path / "réel"
    shutil.copytree(FIXTURE, real)
    link = tmp_path / "link"
    link.symlink_to(real)
    return real, link


def _line(path, text):
    return next(i for i, l in enumerate(Path(path).read_text().splitlines(), 1) if text in l)


# ---------------------------------------------------------------------------
# heading scan
# ---------------------------------------------------------------------------

def test_scan_headings():
    text = ("---\ntitle: x\n# not: a heading\n---\n\n# One {#one}\n\npara\n# not after a blank\n\n"
            "```\n# code\n```\n\n<!--\n# comment\n-->\n\nTwo\n===\n\n    # indented code\n\n"
            "## Three ##\n")
    assert srcmap.scan_headings(text) == [(6, "One {#one}"), (19, "Two"), (24, "Three ##")]
    assert srcmap.body_start(text) == 5


def test_match_headings_by_text_when_counts_differ():
    scanned = [(3, "Intro"), (9, "Methods {-}")]
    headers = [("intro", "Intro"), ("quoted", "In a block quote"), ("methods", "Methods")]
    assert srcmap.match_headings(scanned, headers) == [
        (3, "intro", "Intro"), (9, "methods", "Methods")]


# ---------------------------------------------------------------------------
# builds
# ---------------------------------------------------------------------------

def _build(monkeypatch, root, *extra):
    monkeypatch.chdir(root)
    _texmark(monkeypatch, "thesis.md", "--pdf", "-d", "build", *extra)
    return json.loads((root / "build" / "thesis.srcmap.json").read_text())


@needs_latex
def test_units_and_sections(tmp_path, monkeypatch):
    real, link = _project(tmp_path)
    m = _build(monkeypatch, link)
    pdf = real / "build" / "thesis.pdf"
    assert m["version"] == 1 and m["pdf"] == "thesis.pdf"
    assert m["pdf_size"] == pdf.stat().st_size
    assert m["build"] == "sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert m["generated"].endswith("Z")

    units = {Path(u["md"]).name: u for u in m["units"]}
    assert list(units) == ["thesis.md", "intro.md", "results.md"]
    for u in m["units"]:
        assert u["md"] == os.path.realpath(u["md"]) and u["md"].startswith(str(real.resolve()))
        assert u["tex"] == os.path.realpath(u["tex"])

    root = units["thesis.md"]
    assert root["line"][0] == _line(real / "thesis.md", "  - results.md") + 2  # after the closing ---
    assert root["sections"] == []  # the heading in the HTML comment is not one
    tex = (real / "build" / "thesis.tex").read_text().splitlines()
    first, last = root["texline"]
    assert "\\include{intro}" in tex[first - 1:last]
    assert "\\include{results}" in tex[first - 1:last]

    intro = units["intro.md"]
    assert intro["tex"] == str((real / "build" / "intro.tex").resolve())
    md = real / "intro.md"
    itex = (real / "build" / "intro.tex").read_text().splitlines()
    assert [(s["title"], s["line"]) for s in intro["sections"]] == [
        ("Introduction", _line(md, "# Introduction")),
        ("Background", _line(md, "## Background")),
        ("Background", _line(md, "==========") - 1),  # setext
    ]
    for s, cmd in zip(intro["sections"], ["\\chapter", "\\section", "\\chapter"]):
        assert itex[s["texline"] - 1].startswith(cmd + "{" + s["title"])

    res = units["results.md"]
    assert [s["title"] for s in res["sections"]] == ["Résultats", "Discussion des résultats"]


@needs_latex
def test_map_published_with_renamed_pdf(tmp_path, monkeypatch):
    """With -o, the map is published next to the output PDF, between the
    synctex file and the PDF."""
    real, _ = _project(tmp_path)
    monkeypatch.chdir(real)
    order = []
    real_file, real_map = B.publish_file, srcmap.write_map
    monkeypatch.setattr(B, "publish_file",
                        lambda src, dst: (order.append(Path(dst).name), real_file(src, dst)))
    monkeypatch.setattr(srcmap, "write_map",
                        lambda dst, *a: (order.append(Path(dst).name), real_map(dst, *a)))
    out = real / "out" / "paper.pdf"
    out.parent.mkdir()
    _texmark(monkeypatch, "thesis.md", "--pdf", "-d", "build", "-o", out)
    assert order == ["paper.synctex.gz", "paper.srcmap.json", "paper.pdf"]
    m = json.loads((out.parent / "paper.srcmap.json").read_text())
    assert m["pdf"] == "paper.pdf" and m["pdf_size"] == out.stat().st_size
    assert m["build"] == "sha256:" + hashlib.sha256(out.read_bytes()).hexdigest()


@needs_latex
def test_progressive_stages_publish_their_map(tmp_path, monkeypatch):
    """Each stage of --progressive publishes a map whose build is that of
    the PDF it publishes."""
    real, _ = _project(tmp_path)
    monkeypatch.chdir(real)
    builds = []
    real_pdf = B.publish_pdf

    def recording(src, dst):
        m = json.loads(srcmap.map_file(dst).read_text())
        builds.append(m["build"] == srcmap.pdf_digest(src))
        real_pdf(src, dst)

    monkeypatch.setattr(B, "publish_pdf", recording)
    _texmark(monkeypatch, "thesis.md", "--pdf", "--progressive", "-d", "build",
             "-o", real / "paper.pdf")
    assert builds == [True, True]


@needs_latex
def test_only_lists_typeset_chapters(tmp_path, monkeypatch):
    real, _ = _project(tmp_path)
    m = _build(monkeypatch, real, "--only", "intro.md")
    assert [Path(u["md"]).name for u in m["units"]] == ["thesis.md", "intro.md"]


@needs_latex
def test_map_same_from_caches(tmp_path, monkeypatch):
    """The map is the same whether a chapter came from texcache, blockcache
    or a full conversion: build, edit one paragraph, build again; compare
    with a build without the caches."""
    real, _ = _project(tmp_path)
    strip = lambda m: m["units"]
    first = _build(monkeypatch, real)
    again = _build(monkeypatch, real)  # texcache: no chapter rebuilt
    assert strip(again) == strip(first)
    md = real / "intro.md"
    md.write_text(md.read_text().replace(
        "It\ncites nothing yet", "It\ncites nothing yet, and now has\na longer sentence that"))
    edited = _build(monkeypatch, real)  # blockcache: one paragraph converted
    shutil.rmtree(real / "build")
    full = _build(monkeypatch, real, "--no-cache")
    assert strip(edited) == strip(full)
    assert strip(edited) != strip(first)  # the later headings moved down


@needs_latex
def test_watch_publishes_matching_map(tmp_path, monkeypatch):
    """--watch --progressive: after a change, the published PDF, its synctex
    file and its map belong together (the map's build is the PDF's hash,
    and the map has the new heading)."""
    from tests.test_watch_staged import Watcher, wait_for
    real, _ = _project(tmp_path)
    monkeypatch.chdir(real)
    out = real / "paper.pdf"
    published = []
    real_pdf = B.publish_pdf

    def recording(src, dst):
        real_pdf(src, dst)
        published.append(Path(src).name)

    monkeypatch.setattr(B, "publish_pdf", recording)
    with Watcher(["thesis.md", "-d", "build", "-o", out, "--progressive",
                  "--no-preamble-format", "--watch"]) as w:
        assert w.idle()
        n = len(published)
        md = real / "intro.md"
        md.write_text(md.read_text() + "\n## Added later\n\nNew text.\n")
        assert wait_for(lambda: len(published) >= n + 2, 120)
        assert w.idle()
    m = json.loads((real / "paper.srcmap.json").read_text())
    assert m["build"] == srcmap.pdf_digest(out) and m["pdf_size"] == out.stat().st_size
    intro = next(u for u in m["units"] if u["md"].endswith("intro.md"))
    assert intro["sections"][-1]["title"] == "Added later"
    assert (real / "paper.synctex.gz").read_bytes() == (real / "build" / "thesis.synctex.gz").read_bytes()
