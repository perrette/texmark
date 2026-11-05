"""``\\bibliographystyle{...}`` must not contain whitespace: bibtex rejects it
("White space in argument") and the bibliography silently fails."""
import os
import sys
from pathlib import Path

import pytest

from texmark.build import main
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent


@pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")
@pytest.mark.parametrize("style, expected", [(None, "plainnat"), ("abbrvnat", "abbrvnat")])
def test_arxiv_bibliographystyle_rendered_without_spaces(tmp_path, monkeypatch, style, expected):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    extra = f"biblio_style: {style}\n" if style else ""
    (tmp_path / "doc.md").write_text(
        f"---\ntitle: T\njournal:\n  template: arxiv\nbibliography: refs.bib\n{extra}---\n\n# Intro\n\nText.\n")
    (tmp_path / "refs.bib").write_text("@article{k,\n author={X, Y}, title={Z}, journal={J}, year={2020}\n}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["texmark", "doc.md", "-d", "build"])
    main()
    assert f"\\bibliographystyle{{{expected}}}" in (tmp_path / "build" / "doc.tex").read_text()
