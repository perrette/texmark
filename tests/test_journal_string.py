"""``journal: <name>`` (a bare string) is shorthand for ``journal: {template: <name>}``."""
import os
import sys
from pathlib import Path

import pytest

from texmark.build import main
from texmark.project import load_markdown, normalize_metadata
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent


def test_string_journal_becomes_template_mapping():
    assert normalize_metadata({"journal": "copernicus"})["journal"] == {"template": "copernicus"}


def test_mapping_journal_is_kept():
    journal = {"template": "science", "short": "Sci"}
    assert normalize_metadata({"journal": dict(journal)})["journal"] == journal


@pytest.mark.parametrize("meta", [{}, {"journal": None}])
def test_missing_or_empty_journal_is_empty_mapping(meta):
    assert normalize_metadata(dict(meta))["journal"] == {}


def test_load_markdown_normalises():
    post = load_markdown("---\ntitle: T\njournal: copernicus\n---\n\nBody.\n")
    assert post.metadata["journal"] == {"template": "copernicus"}


@pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")
def test_build_with_string_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: T\njournal: copernicus\n"
        "authors:\n  - firstname: Test\n    lastname: Author\n    affiliation: 1\n"
        "affiliations:\n  - First Institute\n---\n\n# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["texmark", str(md), "-d", str(build_dir)])
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "\\introduction" in out  # copernicus template + filters were applied


FILTER_DOC = """---
title: T
journal: {journal}
---

# Dedication

For someone.

# Introduction

![A caption. More text.](fig.png){{#fig:a}}

| a | b |
|---|---|
| 1 | 2 |

: Table caption. {{#tbl:a}}
"""


@pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")
@pytest.mark.parametrize("journal", ["science", "copernicus", "book"])
def test_journal_filter_standalone_with_string_journal(journal):
    """The texmark-journal filter, run by pandoc directly (without texmark's
    front-matter normalisation), accepts ``journal: <name>``."""
    import io
    import panflute as pf
    import pypandoc
    from texmark.journals import run_filters
    from texmark.shared import journal_template

    json_text = pypandoc.convert_text(FILTER_DOC.format(journal=journal), "json", format="markdown")
    doc = pf.load(io.StringIO(json_text))
    assert doc.get_metadata("journal") == journal
    assert journal_template(doc) == journal
    doc = run_filters(doc)
    latex = pf.convert_text(doc, input_format="panflute", output_format="latex", standalone=False)
    if journal == "science":
        assert r"\textbf{A caption}." in latex  # science caption munger ran
    if journal == "book":
        assert doc.get_metadata("dedication")  # book front-matter section lifted


def test_journal_alias_uses_the_journal_template(tmp_path):
    """``journal: agu`` builds with the agujournal template directory."""
    from texmark.build import build_tex
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: T\njournal: agu\n---\n\nText.\n")
    out = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"))
    assert "agujournal2019" in out.read_text()


def test_canonical_template():
    from texmark.journals import canonical_template
    assert canonical_template("agu") == "agujournal"
    assert canonical_template("jclim") == "ametsoc"
    assert canonical_template("slides") == "beamer"
    assert canonical_template("agujournal") == "agujournal"
    assert canonical_template("unknown") == "unknown"
