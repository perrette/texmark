"""Per-author ``corresponding`` and ``equalcontrib`` front-matter keys (issue #2)."""
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

try:
    import pypdf
except ImportError:
    pypdf = None

from texmark.build import build_tex, main
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)

AUTHORS = [
    {"firstname": "Ann", "lastname": "One", "email": "ann@x.org", "affiliation": 1},
    {"firstname": "Bob", "lastname": "Two", "email": "bob@x.org", "affiliation": 2},
    {"firstname": "Cy", "lastname": "Three", "affiliation": 1},
]


def _md(roles=None, extra=""):
    """Front matter with three authors; ``roles`` maps author index -> extra keys."""
    roles = roles or {}
    lines = ["---", "title: T", "authors:"]
    for i, author in enumerate(AUTHORS):
        keys = dict(author, **roles.get(i, {}))
        first = True
        for k, v in keys.items():
            if isinstance(v, bool):
                v = "true" if v else "false"
            lines.append(("  - " if first else "    ") + f"{k}: {v}")
            first = False
    lines += ["affiliations:", "  - Inst A", "  - Inst B"]
    if extra:
        lines.append(extra)
    lines += ["---", "", "# Introduction", "", "Hello.", ""]
    return "\n".join(lines)


def _build(tmp_path, monkeypatch, template, md_text, name="doc"):
    monkeypatch.chdir(tmp_path)
    # Same document stem for every name: the stem appears in the .tex (the
    # draft-job switch), and the tests compare .tex files across names.
    (tmp_path / name).mkdir(exist_ok=True)
    md = tmp_path / name / "doc.md"
    md.write_text(md_text)
    build_dir = tmp_path / f"build-{name}"
    tex_path = build_dir / "doc.tex"
    build_tex(str(md), str(tex_path), build_dir=str(build_dir), journal_template=template)
    return tex_path.read_text()


# Strings that mark Ann (author 1) or Bob (author 2) as corresponding author.
CORR_MARKERS = {
    "copernicus": (r"\Author[1][ann@x.org]{ Ann }{ One }", r"\Author[2][bob@x.org]{ Bob }{ Two }"),
    "arxiv": (r"Ann~One\thanks{Corresponding author:", r"Bob~Two\thanks{Corresponding author:"),
    "agujournal": (r"\correspondingauthor{ Ann~One }{ ann@x.org }", r"\correspondingauthor{ Bob~Two }{ bob@x.org }"),
    "ametsoc": (r"\correspondingauthor{ Ann~One, ann@x.org }", r"\correspondingauthor{ Bob~Two, bob@x.org }"),
    "elsarticle": (r"Ann~One\corref{cor1} }" "\n" r"\ead{ ann@x.org }", r"Bob~Two\corref{cor1} }" "\n" r"\ead{ bob@x.org }"),
    "springernature": (r"\author*[1]{\fnm{ Ann }", r"\author*[2]{\fnm{ Bob }"),
    "science": (r"Ann~One$^{ 1\ast }$", r"Bob~Two$^{ 2\ast }$"),
    "pnas": (r"\author[a,1]{ Ann~One }", r"\author[b,1]{ Bob~Two }"),
}

# Email line of the corresponding author, for templates that print it separately.
CORR_EMAIL = {
    "science": ("Corresponding author. Email: ann@x.org", "Corresponding author. Email: bob@x.org"),
    "pnas": ("addressed. E-mail: ann@x.org }", "addressed. E-mail: bob@x.org }"),
}

TEMPLATES = sorted(CORR_MARKERS)


@pytest.mark.parametrize("template", TEMPLATES)
def test_corresponding_defaults_to_first_author(tmp_path, monkeypatch, template):
    tex = _build(tmp_path, monkeypatch, template, _md())
    ann, bob = CORR_MARKERS[template]
    assert ann in tex
    assert bob not in tex
    if template in CORR_EMAIL:
        assert CORR_EMAIL[template][0] in tex


@pytest.mark.parametrize("template", TEMPLATES)
def test_marking_first_author_is_same_as_default(tmp_path, monkeypatch, template):
    default = _build(tmp_path, monkeypatch, template, _md(), name="a")
    marked = _build(tmp_path, monkeypatch, template, _md({0: {"corresponding": True}}), name="b")
    assert marked == default


@pytest.mark.parametrize("template", TEMPLATES)
def test_corresponding_moves_to_marked_author(tmp_path, monkeypatch, template):
    tex = _build(tmp_path, monkeypatch, template, _md({1: {"corresponding": True}}))
    ann, bob = CORR_MARKERS[template]
    assert bob in tex
    assert ann not in tex
    if template in CORR_EMAIL:
        assert CORR_EMAIL[template][1] in tex
        assert CORR_EMAIL[template][0] not in tex


def test_science_marks_only_corresponding_author(tmp_path, monkeypatch):
    tex = _build(tmp_path, monkeypatch, "science", _md())
    assert r"Bob~Two$^{ 2 }$" in tex
    assert r"Cy~Three$^{ 1 }$" in tex


@pytest.mark.parametrize("template", ["copernicus", "arxiv", "ametsoc", "elsarticle", "springernature"])
def test_several_corresponding_authors(tmp_path, monkeypatch, template):
    roles = {0: {"corresponding": True}, 1: {"corresponding": True}}
    tex = _build(tmp_path, monkeypatch, template, _md(roles))
    ann, bob = CORR_MARKERS[template]
    assert ann in tex and bob in tex


def test_agujournal_uses_first_marked_author_only(tmp_path, monkeypatch):
    roles = {1: {"corresponding": True}, 2: {"corresponding": True}}
    tex = _build(tmp_path, monkeypatch, "agujournal", _md(roles))
    assert tex.count(r"\correspondingauthor{") == 1
    assert CORR_MARKERS["agujournal"][1] in tex


def test_science_and_pnas_several_corresponding_emails(tmp_path, monkeypatch):
    roles = {0: {"corresponding": True}, 1: {"corresponding": True}}
    sci = _build(tmp_path, monkeypatch, "science", _md(roles), name="sci")
    assert "Corresponding authors. Email: ann@x.org, bob@x.org" in sci
    pnas = _build(tmp_path, monkeypatch, "pnas", _md(roles), name="pnas")
    assert "E-mail: ann@x.org, bob@x.org }" in pnas
    assert r"\author[a,1]{ Ann~One }" in pnas and r"\author[b,1]{ Bob~Two }" in pnas


EQUAL = {1: {"equalcontrib": True}, 2: {"equalcontrib": True}}


def test_copernicus_equalcontrib(tmp_path, monkeypatch):
    assert r"\equalcontrib" not in _build(tmp_path, monkeypatch, "copernicus", _md(), name="a")
    tex = _build(tmp_path, monkeypatch, "copernicus", _md(EQUAL), name="b")
    assert r"\equalcontrib{2,3}" in tex
    # after the affiliations: the class appends its note to the affiliation list
    assert tex.index(r"\affil[2]") < tex.index(r"\equalcontrib{2,3}")


def test_springernature_equalcont(tmp_path, monkeypatch):
    note = r"\equalcont{These authors contributed equally to this work.}"
    assert r"\equalcont" not in _build(tmp_path, monkeypatch, "springernature", _md(), name="a")
    tex = _build(tmp_path, monkeypatch, "springernature", _md(EQUAL), name="b")
    assert tex.count(note) == 2
    assert re.search(r"\\author\[2\]\{\\fnm\{ Bob \}.*\n" + re.escape(note), tex)
    assert re.search(r"\\author\[1\]\{\\fnm\{ Cy \}.*\n" + re.escape(note), tex)


def test_science_equalcontrib(tmp_path, monkeypatch):
    line = r"\small$^\dagger$These authors contributed equally to this work."
    tex = _build(tmp_path, monkeypatch, "science", _md(), name="a")
    assert "\t% " + line in tex
    assert r"\dagger }$" not in tex
    tex = _build(tmp_path, monkeypatch, "science", _md(EQUAL), name="b")
    assert r"Bob~Two$^{ 2\dagger }$" in tex
    assert r"Cy~Three$^{ 1\dagger }$" in tex
    assert r"Ann~One$^{ 1\ast }$" in tex
    assert "Email: ann@x.org\\and\n\t" + line in tex


def test_pnas_equalcontrib(tmp_path, monkeypatch):
    tex = _build(tmp_path, monkeypatch, "pnas", _md(), name="a")
    assert r"\equalauthors" not in tex
    tex = _build(tmp_path, monkeypatch, "pnas", _md(EQUAL), name="b")
    assert r"\equalauthors{\textsuperscript{1}These authors contributed equally to this work.}" in tex
    # equal-contribution note takes marker 1, the corresponding-author note moves to 2
    assert r"\author[a,2]{ Ann~One }" in tex
    assert r"\author[b,1]{ Bob~Two }" in tex
    assert r"\author[a,1]{ Cy~Three }" in tex
    assert r"\correspondingauthor{\textsuperscript{2}To whom" in tex


def test_pnas_equalauthors_field_takes_priority(tmp_path, monkeypatch):
    md = _md(EQUAL, extra="equalauthors: Custom statement.")
    tex = _build(tmp_path, monkeypatch, "pnas", md)
    assert r"\equalauthors{ Custom statement. }" in tex
    assert "These authors contributed equally" not in tex
    assert r"\author[a,1]{ Ann~One }" in tex
    assert r"\author[b]{ Bob~Two }" in tex
    assert r"\correspondingauthor{\textsuperscript{1}To whom" in tex


@pytest.mark.parametrize("template", ["arxiv", "agujournal", "ametsoc", "elsarticle",
                                      "book", "report", "memoir", "classicthesis", "default"])
def test_equalcontrib_ignored_elsewhere(tmp_path, monkeypatch, template):
    plain = _build(tmp_path, monkeypatch, template, _md(), name="a")
    marked = _build(tmp_path, monkeypatch, template, _md(EQUAL), name="b")
    assert marked == plain


@pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                    reason="latexmk/pdflatex not available")
@pytest.mark.parametrize("template", ["copernicus", "science", "springernature", "pnas"])
def test_author_roles_build_pdf(tmp_path, monkeypatch, template):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.chdir(tmp_path)
    roles = {1: {"corresponding": True, "equalcontrib": True}, 2: {"equalcontrib": True}}
    md = tmp_path / "doc.md"
    md.write_text(_md(roles))
    build_dir = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["texmark", str(md), "-j", template, "-d", str(build_dir), "--pdf"])
    main()
    assert (build_dir / "doc.pdf").read_bytes()[:4] == b"%PDF"
    log = (build_dir / "doc.log").read_text(errors="replace")
    errors = re.findall(r"^! .*?^l\.\d+ .*?$", log, re.M | re.S)
    assert not errors, errors
    if pypdf is not None and template != "copernicus":  # copernicus gobbles \equalcontrib locally
        text = "".join(page.extract_text() or "" for page in pypdf.PdfReader(str(build_dir / "doc.pdf")).pages)
        assert "contributed equally" in re.sub(r"\s+", " ", text)
