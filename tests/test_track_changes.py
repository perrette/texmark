"""Track changes: the ``changes`` option, resolved once for a master
document and its chapters, and the ``changes`` package in the preamble."""
import sys
from pathlib import Path

import pytest

from texmark.build import _resolve_changes, build_tex, main
from texmark.filters.changes import changes_preamble
from tests import pandoc_available

pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")


@pytest.mark.parametrize("value, texts, expected", [
    ("auto", ["plain"], False),
    ("auto", ["plain", "a {++ b ++}"], True),
    ("auto", ["only `{++ code ++}`"], False),
    ("", ["a {-- b --}"], True),
    (True, [], True),
    ("on", [], True),
    (False, ["a {++ b ++}"], False),
    ("off", ["a {++ b ++}"], False),
])
def test_resolve_changes(value, texts, expected):
    assert _resolve_changes(value, texts) == expected


def test_changes_preamble():
    assert changes_preamble(False) == ''
    pre = changes_preamble(True)
    assert '\\usepackage[commandnameprefix=ifneeded]{changes}' in pre
    assert '\\providecommand{\\chcomment}{\\comment}' in pre


def _build(tmp_path, body, front=""):
    md = tmp_path / "doc.md"
    md.write_text(f"---\ntitle: T\n{front}---\n\n{body}\n")
    out = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"))
    return out.read_text()


def test_auto_loads_package_when_marked(tmp_path):
    tex = _build(tmp_path, "A {++ new ++} and {-- old --}.")
    assert "{changes}" in tex
    assert "\\chadded{new}" in tex and "\\chdeleted{old}" in tex


def test_auto_without_marks_loads_nothing(tmp_path):
    tex = _build(tmp_path, "Plain text.")
    assert "{changes}" not in tex


def test_off_gives_accepted_text(tmp_path):
    tex = _build(tmp_path, "A {++ new ++}{>> why <<} and {-- old --}.", "changes: false\n")
    assert "{changes}" not in tex and "\\chadded" not in tex
    assert "A new and ." in tex


def test_chapter_marks_turn_auto_on_for_master(tmp_path, monkeypatch):
    """Marks only in an embedded chapter: the master's preamble loads the
    package, and the chapter uses its commands."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "root.md").write_text("---\ntitle: R\n---\n\n![](chapter.md)\n")
    (src / "chapter.md").write_text("# Chapter\n\nText {++ added ++}.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["texmark", str(src / "root.md"), "-d", str(build_dir)])
    main()
    assert "{changes}" in (build_dir / "root.tex").read_text()
    assert "\\chadded{added}" in (build_dir / "chapter.tex").read_text()


def test_master_off_applies_to_chapters(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "root.md").write_text("---\ntitle: R\nchanges: false\n---\n\n![](chapter.md)\n")
    (src / "chapter.md").write_text("---\nchanges: true\n---\n\n# Chapter\n\nText {++ added ++}.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["texmark", str(src / "root.md"), "-d", str(build_dir)])
    main()
    assert "{changes}" not in (build_dir / "root.tex").read_text()
    chapter = (build_dir / "chapter.tex").read_text()
    assert "\\chadded" not in chapter and "Text added." in chapter


def test_preamble_loads_ulem_only_when_needed():
    assert changes_preamble(False, False) == ''
    guard = '\\@ifpackageloaded{ulem}{}{\\usepackage[normalem]{ulem}}'
    assert guard in changes_preamble(False, True)
    assert guard in changes_preamble(True)


def test_strikeout_without_changes_is_sout(tmp_path):
    tex = _build(tmp_path, "A ~~old~~ word.", "changes: false\n")
    assert "\\sout{old}" in tex and "normalem]{ulem}" in tex
    assert "{changes}" not in tex

