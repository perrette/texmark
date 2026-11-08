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
