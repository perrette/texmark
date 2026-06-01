"""Tests for the `preamble:` YAML field (Item 11)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def _subprocess_finds_local_texmark(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


pytestmark_pandoc = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


def _build(tmp_path, md_content, journal_template="arxiv"):
    from texmark.build import build_tex
    md = tmp_path / "doc.md"
    md.write_text(md_content)
    out = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"),
              journal_template=journal_template)
    return out.read_text()


# ---------------------------------------------------------------------------
# Integration tests (require pandoc)
# ---------------------------------------------------------------------------

@pytestmark_pandoc
def test_preamble_inline_block_scalar(tmp_path, _subprocess_finds_local_texmark):
    """Multiline block scalar is included verbatim."""
    tex = _build(tmp_path,
        "---\ntitle: T\npreamble: |\n  \\newcommand{\\degC}{\\,^\\circ\\!C}\n---\n\nBody.\n")
    assert "\\newcommand{\\degC}" in tex


@pytestmark_pandoc
def test_preamble_single_file(tmp_path, _subprocess_finds_local_texmark):
    """Single file path: file contents are read and emitted."""
    macros = tmp_path / "macros.tex"
    macros.write_text("\\newcommand{\\myMacro}{hello}\n")
    tex = _build(tmp_path,
        "---\ntitle: T\npreamble: macros.tex\n---\n\nBody.\n")
    assert "\\newcommand{\\myMacro}" in tex


@pytestmark_pandoc
def test_preamble_list_of_files(tmp_path, _subprocess_finds_local_texmark):
    """List of file paths: all files concatenated."""
    (tmp_path / "macros.tex").write_text("\\newcommand{\\macroA}{A}\n")
    (tmp_path / "theorems.tex").write_text("\\newcommand{\\macroB}{B}\n")
    tex = _build(tmp_path,
        "---\ntitle: T\npreamble:\n  - macros.tex\n  - theorems.tex\n---\n\nBody.\n")
    assert "\\newcommand{\\macroA}" in tex
    assert "\\newcommand{\\macroB}" in tex


@pytestmark_pandoc
def test_preamble_mixed_list(tmp_path, _subprocess_finds_local_texmark):
    """List mixing file path and inline LaTeX."""
    (tmp_path / "macros.tex").write_text("\\newcommand{\\fileCmd}{x}\n")
    tex = _build(tmp_path,
        '---\ntitle: T\npreamble:\n  - macros.tex\n  - "\\\\newcommand{\\\\inlineCmd}{y}"\n---\n\nBody.\n')
    assert "\\newcommand{\\fileCmd}" in tex
    assert "\\newcommand{\\inlineCmd}" in tex


@pytestmark_pandoc
def test_preamble_absent_no_change(tmp_path, _subprocess_finds_local_texmark):
    """No preamble key: output should not contain user_preamble artefacts."""
    tex = _build(tmp_path, "---\ntitle: T\n---\n\nBody.\n")
    # user_preamble renders as empty string; the template variable itself must
    # not appear verbatim in the output.
    assert "user_preamble" not in tex


@pytestmark_pandoc
def test_preamble_placed_after_xr_preamble(tmp_path, _subprocess_finds_local_texmark):
    """user_preamble appears after xr_preamble in the rendered .tex."""
    from texmark.build import build_tex
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: T\npreamble: |\n  \\newcommand{\\myCmd}{z}\n"
        "companions:\n  - si.md\n---\n\nBody.\n"
    )
    si = tmp_path / "si.md"
    si.write_text("---\ntitle: SI\n---\n\nSI body.\n")
    out = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"),
              journal_template="arxiv", companion_stems=["si"], own_stem="doc")
    tex = out.read_text()
    xr_pos = tex.find("\\externaldocument")
    cmd_pos = tex.find("\\newcommand{\\myCmd}")
    assert xr_pos != -1, "xr_preamble content not found"
    assert cmd_pos != -1, "user_preamble content not found"
    assert xr_pos < cmd_pos, "user_preamble should appear after xr_preamble"
