"""Tests for --watch multi-file path expansion (Item 10).

Patches ``watch_loop`` to capture the path list rather than blocking.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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


def _run_watch(md_path: Path, build_dir: Path, monkeypatch) -> list[Path]:
    from texmark.build import main as build_main

    monkeypatch.chdir(md_path.parent)
    monkeypatch.setattr(sys, "argv", [
        "texmark", str(md_path), "-d", str(build_dir), "--watch",
    ])
    captured: dict = {}

    def fake_watch_loop(do_build, paths, interval=0.5):
        captured["paths"] = list(paths)

    with patch("texmark.build.watch_loop", side_effect=fake_watch_loop), \
         patch("texmark.build.compile_pdf"):
        build_main()

    return [Path(p) for p in captured.get("paths", [])]


def test_watch_single_file(tmp_path, monkeypatch):
    """Single-file invocation: watch list is root + template only (regression)."""
    md = tmp_path / "solo.md"
    md.write_text("---\ntitle: Solo\njournal:\n  template: arxiv\n---\n\n# Hello\n")
    paths = _run_watch(md, tmp_path / "build", monkeypatch)
    assert md in paths
    assert any(p.name == "template.tex" for p in paths)
    assert len(paths) == 2


def test_watch_multi_file_embeds(tmp_path, monkeypatch):
    """Root with 2 embedded chapters: watch list includes all 3 markdown files."""
    root = tmp_path / "root.md"
    ch1 = tmp_path / "ch1.md"
    ch2 = tmp_path / "ch2.md"
    root.write_text(
        "---\ntitle: Root\njournal:\n  template: arxiv\n---\n\n"
        "![](ch1.md)\n\n![](ch2.md)\n"
    )
    ch1.write_text("---\ntitle: Chapter 1\n---\n\n# Ch1\n\nText.\n")
    ch2.write_text("---\ntitle: Chapter 2\n---\n\n# Ch2\n\nText.\n")
    paths = _run_watch(root, tmp_path / "build", monkeypatch)
    assert root in paths
    assert ch1 in paths
    assert ch2 in paths
    # root + ch1 + ch2 + template (1 unique) = 4
    assert len(paths) == 4


def test_watch_main_and_companion(tmp_path, monkeypatch):
    """Main + SI companion: watch list includes companion file and its template."""
    main_md = tmp_path / "main.md"
    si_md = tmp_path / "si.md"
    main_md.write_text(
        "---\ntitle: Main\njournal:\n  template: arxiv\ncompanions:\n  - si.md\n---\n\n# Intro\n"
    )
    si_md.write_text(
        "---\ntitle: SI\njournal:\n  template: elsarticle\n---\n\n# SI\n"
    )
    paths = _run_watch(main_md, tmp_path / "build", monkeypatch)
    assert main_md in paths
    assert si_md in paths
    # arxiv template (root) and default template (si) are different files
    template_paths = [p for p in paths if p.name == "template.tex"]
    assert len(template_paths) == 2
    # main + si + arxiv/template.tex + default/template.tex = 4
    assert len(paths) == 4
