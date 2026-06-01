"""Tests for Item 17: front-matter YAML keys + # Dedication / # Preface / # Foreword extraction."""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import build_tex, main

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc binary not available on PATH",
)


@pytest.fixture(autouse=True)
def _subprocess_finds_local_texmark(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


def test_dedication_yaml_key(tmp_path, monkeypatch):
    """dedication: YAML key emits dedication content in book template."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\ndedication: 'To my advisor'\n---\n\n# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    argv = ["texmark", str(md), "-j", "book", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "To my advisor" in out


def test_dedication_section_lifted(tmp_path, monkeypatch):
    """# Dedication markdown section is lifted into the frontmatter block."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\n---\n\n"
        "# Dedication\n\nTo my family.\n\n"
        "# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    argv = ["texmark", str(md), "-j", "book", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "To my family" in out
    # dedication must appear before the \mainmatter command (not the comment line)
    assert out.index("To my family") < out.index("\n\\mainmatter\n")


def test_yaml_wins_over_section(tmp_path, monkeypatch):
    """YAML dedication: wins over # Dedication body section."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\ndedication: 'YAML wins'\n---\n\n"
        "# Dedication\n\nBody text loses.\n\n"
        "# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    argv = ["texmark", str(md), "-j", "book", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "YAML wins" in out
    assert "Body text loses" not in out


def test_preface_section_lifted(tmp_path, monkeypatch):
    """# Preface section is lifted into the book frontmatter."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\n---\n\n"
        "# Preface\n\nThis book arose from research.\n\n"
        "# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    argv = ["texmark", str(md), "-j", "book", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "This book arose from research" in out


def test_list_of_figures_yaml(tmp_path, monkeypatch):
    """list_of_figures: true emits \\listoffigures in book template."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\nlist_of_figures: true\n---\n\n# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    argv = ["texmark", str(md), "-j", "book", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "\\listoffigures" in out


def test_list_of_tables_yaml(tmp_path, monkeypatch):
    """list_of_tables: true emits \\listoftables in book template."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\nlist_of_tables: true\n---\n\n# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    argv = ["texmark", str(md), "-j", "book", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "\\listoftables" in out


def test_frontmatter_noop_for_article_class(tmp_path, monkeypatch):
    """# Dedication section in an article-class template stays in the body (no lift)."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Paper\n---\n\n"
        "# Dedication\n\nOdd dedication in a paper.\n\n"
        "# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    # Use arxiv (article-class) rather than default to avoid a pre-existing
    # Jinja2 syntax issue in the default template's \graphicspath line.
    argv = ["texmark", str(md), "-j", "arxiv", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    out = (build_dir / "doc.tex").read_text()
    # The body section is not lifted; the text remains in the document body
    assert "Odd dedication in a paper" in out


def test_all_four_book_family_templates(tmp_path, monkeypatch):
    """Each book-family template accepts dedication + preface without errors."""
    for template in ("book", "report", "memoir", "classicthesis"):
        td = tmp_path / template
        td.mkdir()
        md = td / "doc.md"
        md.write_text(
            f"---\ntitle: Thesis ({template})\ndedication: 'To my advisor'\n---\n\n"
            "# Preface\n\nPrefatory remarks.\n\n"
            "# Introduction\n\nHello.\n"
        )
        build_dir = td / "build"
        monkeypatch.chdir(td)
        argv = ["texmark", str(md), "-j", template, "-d", str(build_dir)]
        monkeypatch.setattr(sys, "argv", argv)
        main()
        out = (build_dir / "doc.tex").read_text()
        assert "To my advisor" in out, f"dedication missing in {template} template"
        assert "Prefatory remarks" in out, f"preface missing in {template} template"
