"""texmark sync forward|backward (texmark.sync) on the fixture project of
tests/fixtures/synctex (docs/synctex-design.md, section 6).

Skips when pandoc, latexmk, pdflatex or synctex is missing.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import texmark.build as B
from texmark import sync
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "synctex"

pytestmark = pytest.mark.skipif(
    not pandoc_available() or shutil.which("latexmk") is None
    or shutil.which("pdflatex") is None or shutil.which("synctex") is None,
    reason="pandoc, latexmk, pdflatex or synctex missing",
)


@pytest.fixture(autouse=True)
def _local_texmark_on_pythonpath(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + (os.pathsep + existing if existing else ""))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The fixture project in a directory with a non-ASCII name, built once."""
    root = tmp_path_factory.mktemp("sync") / "projét"
    shutil.copytree(FIXTURE, root)
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    subprocess.run([sys.executable, "-m", "texmark.cli", "thesis.md", "--pdf", "-d", "build"],
                   cwd=root, env=env, check=True, capture_output=True)
    return root


def _line(path, text):
    return next(i for i, l in enumerate(Path(path).read_text().splitlines(), 1) if text in l)


# Markdown lines of each kind of block, by a piece of their text.
SAMPLES = {
    "intro.md": ["# Introduction", "The first paragraph", "source, so that",
                 "cites nothing yet", "## Background", "A second paragraph",
                 "lines in the source", "A first list item", "A second list item",
                 "A third list item", "# a comment in code", "==========",
                 "Text under a setext"],
    "results.md": ["# Résultats", "![A figure caption.]", "The figure above",
                   "E = m c^2", "$$ {#eq:energy}", "A paragraph after the equation",
                   "two lines of source", "## Discussion des résultats",
                   "The last paragraph"],
}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_forward_then_backward(built, name):
    """For a sample of lines of each block, forward then backward gives the
    same file and a line within ±1."""
    pdf = built / "build" / "thesis.pdf"
    md = built / name
    for text in SAMPLES[name]:
        line = _line(md, text)
        place = sync.forward(md, line, pdf=pdf)[0]
        assert set(place) == {"page", "x", "y", "width", "height"}
        back = sync.backward(pdf, place["page"], place["x"], place["y"])
        assert back["file"] == os.path.realpath(md), text
        assert abs(back["line"] - line) <= 1, (text, line, back["line"])
        assert back["column"] is None


def test_headings_exact(built):
    pdf = built / "build" / "thesis.pdf"
    md = built / "results.md"
    for text in ("# Résultats", "## Discussion des résultats"):
        line = _line(md, text)
        place = sync.forward(md, line, pdf=pdf)[0]
        assert sync.backward(pdf, place["page"], place["x"], place["y"])["line"] == line


def test_footnote_maps_to_paragraph_or_definition(built):
    pdf = built / "build" / "thesis.pdf"
    md = built / "intro.md"
    place = sync.forward(md, _line(md, "[^note]:"), pdf=pdf)[0]
    line = sync.backward(pdf, place["page"], place["x"], place["y"])["line"]
    assert line in (_line(md, "A second paragraph"), _line(md, "[^note]:"))


def test_cli_json_and_pdf_lookup(built):
    """The CLI prints JSON; without --pdf, forward finds the PDF from the
    map in the build folder."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    run = lambda *a: subprocess.run([sys.executable, "-m", "texmark.cli", "sync", *a],
                                    cwd=built, env=env, capture_output=True, text=True)
    line = _line(built / "intro.md", "The first paragraph")
    r = run("forward", f"intro.md:{line}")
    assert r.returncode == 0, r.stdout + r.stderr
    place = json.loads(r.stdout)
    place = place[0] if isinstance(place, list) else place
    r = run("backward", "--pdf", "build/thesis.pdf", str(place["page"]),
            str(place["x"]), str(place["y"]))
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout) == {"file": os.path.realpath(built / "intro.md"),
                                    "line": line, "column": None}
    r = run("forward", "nowhere.md:3")
    assert r.returncode == 1 and json.loads(r.stdout)["code"] == "no-map"


def test_errors(built, tmp_path):
    pdf = tmp_path / "x.pdf"
    shutil.copy(built / "build" / "thesis.pdf", pdf)
    with pytest.raises(sync.SyncError) as e:
        sync.backward(pdf, 1, 100, 100)
    assert e.value.code == "no-map"

    shutil.copy(built / "build" / "thesis.srcmap.json", tmp_path / "x.srcmap.json")
    with pytest.raises(sync.SyncError) as e:
        sync.backward(pdf, 1, 100, 100)
    assert e.value.code == "no-synctex"

    shutil.copy(built / "build" / "thesis.synctex.gz", tmp_path / "x.synctex.gz")
    with open(pdf, "ab") as f:
        f.write(b"\n%% appended\n")
    with pytest.raises(sync.SyncError) as e:
        sync.backward(pdf, 1, 100, 100)
    assert e.value.code == "stale"

    with pytest.raises(sync.SyncError) as e:
        sync.forward(tmp_path / "other.md", 1, pdf=built / "build" / "thesis.pdf")
    assert e.value.code == "not-in-map"


def test_build_entry_point_forwards_sync(built, monkeypatch, capsys):
    """An install whose `texmark` script still runs texmark.build:main."""
    monkeypatch.chdir(built)
    line = _line(built / "intro.md", "The first paragraph")
    monkeypatch.setattr(sys, "argv", ["texmark", "sync", "forward", f"intro.md:{line}",
                                      "--pdf", "build/thesis.pdf"])
    with pytest.raises(SystemExit) as e:
        B.main()
    assert e.value.code == 0
    assert "page" in capsys.readouterr().out
