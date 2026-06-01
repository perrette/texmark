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


def test_unicode_superscript_eight_overridden():
    """U+2078 (⁸) is unmapped in pylatexenc — our override fills the gap."""
    text = "@a{k, title = {⁸}}"
    out, unmapped = rewrite_text(text)
    assert "⁸" not in out
    assert r"\textsuperscript{8}" in out
    assert unmapped == []


def test_delta_18o_renders_consistently_and_merges():
    """The malevich_vetter2019-style δ¹⁸O should produce \\ensuremath{\\delta}
    followed by a single merged \\textsuperscript{18}, not two adjacent
    \\textsuperscript blocks or \\textonesuperior + \\textsuperscript."""
    text = "@a{k, title = {δ¹⁸O}}"
    out, unmapped = rewrite_text(text)
    assert r"\ensuremath{\delta}" in out
    assert r"\textsuperscript{18}" in out
    # No mismatched sibling commands.
    assert r"\textonesuperior" not in out
    assert r"\textsuperscript{1}\textsuperscript{8}" not in out
    assert unmapped == []


def test_subscript_digits_overridden():
    text = "@a{k, title = {H₂O}}"
    out, unmapped = rewrite_text(text)
    assert "₂" not in out
    assert r"\textsubscript{2}" in out
    assert unmapped == []


def test_super_sub_merge_in_isolation():
    """The merge step is also exposed indirectly by rewriting input that
    contains a long superscript run."""
    text = "@a{k, title = {x¹²³⁴⁵y}}"
    out, _ = rewrite_text(text)
    assert r"\textsuperscript{12345}" in out


def test_html_italic_tag_to_textit():
    text = "@a{k, title = {Global <i>D</i> calibration}}"
    out, _ = rewrite_text(text)
    assert "<i>" not in out and "</i>" not in out
    assert r"\textit{D}" in out


def test_html_sup_sub_tags_to_textsuperscript_subscript():
    text = "@a{k, title = {H<sub>2</sub>O and <sup>18</sup>O}}"
    out, _ = rewrite_text(text)
    assert "<sub>" not in out and "<sup>" not in out
    assert r"\textsubscript{2}" in out
    assert r"\textsuperscript{18}" in out


def test_crossref_style_malevich_title_round_trip():
    """The actual CrossRef-exported malevich_vetter2019 title: combines
    HTML <i> + <sup> with a Unicode δ. Should produce
    \\textit{\\ensuremath{\\delta}}\\textsuperscript{18}O — no stray
    angle brackets, no orphaned Unicode."""
    text = (
        "@article{malevich_vetter2019,\n"
        "  title = {Global Core Top Calibration of "
        "<i>δ</i><sup>18</sup>O in Planktic Foraminifera}\n"
        "}\n"
    )
    out, unmapped = rewrite_text(text)
    assert "<" not in out and ">" not in out.replace("\\>", "")  # no stray HTML
    assert "δ" not in out
    assert r"\textit{\ensuremath{\delta}}" in out
    assert r"\textsuperscript{18}" in out
    assert unmapped == []


def test_html_strong_b_em_tags():
    text = "@a{k, title = {<b>bold</b> <strong>strong</strong> <em>emph</em>}}"
    out, _ = rewrite_text(text)
    assert r"\textbf{bold}" in out
    assert r"\textbf{strong}" in out
    assert r"\emph{emph}" in out


def test_html_nested_same_tag_inside_out():
    text = "@a{k, title = {<i>outer <i>inner</i> tail</i>}}"
    out, _ = rewrite_text(text)
    assert r"\textit{outer \textit{inner} tail}" in out


def test_html_unknown_tag_left_alone():
    """Future-proof: tags not in our table stay intact so a future
    custom-tag user isn't silently rewritten."""
    text = "@a{k, title = {<custom>x</custom>}}"
    out, _ = rewrite_text(text)
    assert "<custom>" in out
    assert "</custom>" in out


def test_html_orphan_open_tag_left_alone():
    """A `<i>` with no closing tag should not be touched."""
    text = "@a{k, title = {This is <i>broken}}"
    out, _ = rewrite_text(text)
    assert "<i>" in out


def test_html_only_no_unicode_still_merges_adjacent_superscripts():
    """Even when pylatexenc isn't invoked (no non-ASCII chars),
    adjacent superscript blocks created by HTML tag conversion should
    still merge so the result is one block."""
    text = "@a{k, title = {<sup>1</sup><sup>8</sup>O}}"
    out, _ = rewrite_text(text)
    assert r"\textsuperscript{18}" in out
    assert r"\textsuperscript{1}\textsuperscript{8}" not in out


def test_rewrite_in_place_converts_tex_body(tmp_path: Path):
    """The same rewrite applies to .tex bodies generated by pandoc, since
    pandoc passes most scientific Unicode through raw."""
    from texmark.unicode_bib import rewrite_in_place
    tex = tmp_path / "main.tex"
    tex.write_text("Calibration of δ¹⁸O at 30°C.", encoding="utf-8")
    rewrite_in_place(tex)
    out = tex.read_text(encoding="utf-8")
    assert r"\ensuremath{\delta}" in out
    assert r"\textsuperscript{18}" in out
    assert r"{\textdegree}" in out


def test_rewrite_in_place_skips_write_when_ascii_only(tmp_path: Path):
    """When nothing to rewrite, the file's mtime must survive so
    latexmk's fingerprint cache doesn't see an artificial change."""
    from texmark.unicode_bib import rewrite_in_place
    tex = tmp_path / "main.tex"
    tex.write_text("Plain ASCII content only.", encoding="utf-8")
    before = tex.stat().st_mtime_ns
    rewrite_in_place(tex)
    after = tex.stat().st_mtime_ns
    assert before == after, "mtime changed on a no-op rewrite"


def test_rewrite_in_place_missing_file_returns_empty(tmp_path: Path):
    from texmark.unicode_bib import rewrite_in_place
    assert rewrite_in_place(tmp_path / "nope.tex") == []
