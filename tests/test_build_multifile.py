"""Integration tests for multi-file build orchestration (Item 3)."""
import os
import sys
from pathlib import Path

import pytest

from texmark.build import build_tex, main
from tests import pandoc_available


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "multifile"
REPO_ROOT = Path(__file__).parent.parent


pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


@pytest.fixture(autouse=True)
def _subprocess_finds_local_texmark(monkeypatch):
    """Ensure pandoc subprocess filters import this checkout's texmark.

    The pandoc filter chain runs `texmark-journal` in a subprocess; without
    PYTHONPATH the subprocess resolves `import texmark` via the editable
    install, which may point at a different checkout (e.g. the main
    worktree). Prepending the repo root ensures the in-tree changes are
    exercised by the integration test.
    """
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


def test_body_only_writes_raw_body(tmp_path):
    """body_only=True writes the pandoc body output (no Jinja master template)."""
    chapter = tmp_path / "chapter.md"
    chapter.write_text(FIXTURE_DIR.joinpath("chapter.md").read_text())

    out_tex = tmp_path / "build" / "chapter.tex"
    build_tex(
        str(chapter),
        str(out_tex),
        build_dir=str(tmp_path / "build"),
        journal_template="arxiv",
        body_only=True,
    )

    text = out_tex.read_text()
    assert "Chapter body text" in text
    # body-only must not contain master-template scaffolding
    assert r"\documentclass" not in text
    assert r"\begin{document}" not in text


def test_multifile_main_writes_master_and_embed(tmp_path, monkeypatch):
    """Running main() against root.md + ![](chapter.md) produces both .tex files."""
    src = tmp_path / "src"
    src.mkdir()
    for name in ("root.md", "chapter.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())

    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(src / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    root_tex = build_dir / "root.tex"
    chapter_tex = build_dir / "chapter.tex"
    assert root_tex.exists(), f"master .tex not written: {root_tex}"
    assert chapter_tex.exists(), f"embed .tex not written: {chapter_tex}"
    assert r"\input{chapter}" in root_tex.read_text()


def test_single_input_no_embeds_skips_orchestration(tmp_path, monkeypatch):
    """A lone single-file invocation (no embeds, no companions) writes only the master."""
    md = tmp_path / "solo.md"
    md.write_text(
        "---\ntitle: Solo\njournal:\n  template: arxiv\n---\n\n# Hello\n\nBody.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    assert (build_dir / "solo.tex").exists()
    # no stray body-only artefacts
    assert not (build_dir / "chapter.tex").exists()
