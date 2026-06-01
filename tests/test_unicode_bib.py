"""Tests for texmark.unicode_bib — rewriting .bib files so pdflatex's 8-bit
font stack doesn't drop non-ASCII characters."""
from pathlib import Path

import pytest

pylatexenc = pytest.importorskip("pylatexenc")

from texmark.unicode_bib import (
    rewrite_text,
    stage_bib,
    _entry_at_offset,
    _NON_ASCII_RE,
)


def test_ascii_only_text_unchanged():
    text = "@article{key, title = {Plain ASCII title}}"
    out, unmapped = rewrite_text(text)
    assert out == text
    assert unmapped == []


def test_delta_translated_to_ensuremath():
    text = "@article{vetter2019, title = {Calibration of δ18O}}"
    out, unmapped = rewrite_text(text)
    assert "δ" not in out
    assert r"\ensuremath{\delta}" in out
    assert unmapped == []


def test_thin_space_translated():
    text = "@article{key, title = {30 kyr}}"
    out, _ = rewrite_text(text)
    assert " " not in out
    assert r"\," in out


def test_smart_quotes_translated():
    text = "@article{key, title = {“quoted”}}"
    out, _ = rewrite_text(text)
    assert "“" not in out and "”" not in out
    assert r"\textquotedblleft" in out
    assert r"\textquotedblright" in out


def test_unmapped_codepoint_left_in_place_and_reported():
    # U+1F4A9 (pile of poo) — definitively no LaTeX representation.
    text = "@article{joke, title = {Something \U0001F4A9 weird}}"
    out, unmapped = rewrite_text(text)
    assert "\U0001F4A9" in out  # char is preserved, not silently dropped
    assert len(unmapped) == 1
    cp, line, entry = unmapped[0]
    assert cp == 0x1F4A9
    assert line == 1
    assert entry == "joke"


def test_unmapped_reports_correct_line_and_entry():
    text = (
        "@article{first, title = {Plain}}\n"
        "\n"
        "@misc{second,\n"
        "  note = {Unknown char \U0001F4A9}\n"
        "}\n"
    )
    _, unmapped = rewrite_text(text)
    assert len(unmapped) == 1
    cp, line, entry = unmapped[0]
    assert line == 4
    assert entry == "second"


def test_multiple_distinct_chars_all_translated():
    text = "@a{k, title = {δ and ° and ±}}"
    out, unmapped = rewrite_text(text)
    assert "δ" not in out
    assert "°" not in out
    assert "±" not in out
    assert unmapped == []


def test_entry_at_offset_picks_nearest_preceding():
    text = "@one{first}\nstuff\n@two{second}\nmoar\n"
    # Offset inside "stuff" → 'first'
    assert _entry_at_offset(text, text.index("stuff")) == "first"
    # Offset inside "moar" → 'second'
    assert _entry_at_offset(text, text.index("moar")) == "second"


def test_entry_at_offset_returns_none_before_any_entry():
    text = "% header comment\n@one{key}\n"
    assert _entry_at_offset(text, 5) is None


def test_stage_bib_writes_converted_file(tmp_path: Path):
    src = tmp_path / "refs.bib"
    src.write_text("@a{k, title = {δ test}}", encoding="utf-8")
    dst_dir = tmp_path / "build"
    dst_path = stage_bib(src, dst_dir)
    assert dst_path == dst_dir / "refs.bib"
    contents = dst_path.read_text(encoding="utf-8")
    assert "δ" not in contents
    assert r"\ensuremath{\delta}" in contents


def test_stage_bib_pure_ascii_preserves_mtime(tmp_path: Path):
    """An ASCII-only bib should be a byte-identical copy so latexmk's
    file-fingerprint cache isn't invalidated on every build."""
    src = tmp_path / "refs.bib"
    src.write_text("@a{k, title = {Plain title}}", encoding="utf-8")
    src_stat = src.stat()
    dst_dir = tmp_path / "build"
    dst_path = stage_bib(src, dst_dir)
    assert dst_path.read_bytes() == src.read_bytes()
    # shutil.copy2 preserves mtime; check it survived.
    assert int(dst_path.stat().st_mtime) == int(src_stat.st_mtime)


def test_stage_bib_missing_source_returns_none(tmp_path: Path):
    dst = stage_bib(tmp_path / "nope.bib", tmp_path / "build")
    assert dst is None


def test_stage_bib_creates_missing_dst_dir(tmp_path: Path):
    src = tmp_path / "refs.bib"
    src.write_text("@a{k, title = {ok}}", encoding="utf-8")
    dst_dir = tmp_path / "deeply" / "nested" / "build"
    dst_path = stage_bib(src, dst_dir)
    assert dst_path is not None
    assert dst_path.exists()
