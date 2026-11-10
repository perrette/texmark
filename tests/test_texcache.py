"""Tests for the on-disk cache of embedded documents' .tex (texmark/texcache.py)."""
import os
import sys
from pathlib import Path

import pypandoc
import pytest

import texmark.build as build
from texmark import texcache
from texmark.project import parse_markdown
from tests import pandoc_available


pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
       b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
       b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


@pytest.fixture
def project(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "images").mkdir(parents=True)
    (src / "root.md").write_text(
        "---\ntitle: Root\njournal:\n  template: book\n---\n\n"
        "Root text.\n\n![](ch1.md)\n\n![](ch2.md)\n")
    (src / "ch1.md").write_text("# One\n\nZyxwvone text.\n\n![A figure](images/fig.png)\n")
    (src / "ch2.md").write_text("# Two\n\nZyxwvtwo text.\n")
    (src / "images" / "fig.png").write_bytes(PNG)
    monkeypatch.chdir(tmp_path)
    return src


def run(src, monkeypatch, *extra):
    """One texmark run, as a new process would see it. Returns the names of
    the .tex files built and the sources passed to pandoc."""
    parse_markdown.cache_clear()
    texcache._environment.cache_clear()
    calls, built = [], []
    convert = pypandoc.convert_text
    build_tex = build.build_tex

    def spy_convert(source, *a, **k):
        calls.append(source)
        return convert(source, *a, **k)

    def spy_build_tex(input_md, output_tex, **k):
        built.append(Path(output_tex).name)
        return build_tex(input_md, output_tex, **k)

    with monkeypatch.context() as m:
        m.setattr(pypandoc, "convert_text", spy_convert)
        m.setattr(build, "build_tex", spy_build_tex)
        m.setattr(sys, "argv", ["texmark", str(src / "root.md"), "-d", "build", *extra])
        build.main()
    return built, calls


def test_unchanged_rebuild_reuses_chapters(project, monkeypatch):
    built, _ = run(project, monkeypatch)
    assert built == ["ch1.tex", "ch2.tex", "root.tex"]
    tex = Path("build/ch1.tex")
    content, mtime = tex.read_bytes(), tex.stat().st_mtime_ns

    built, calls = run(project, monkeypatch)
    assert built == ["root.tex"]
    # neither the reader (markdown in) nor the render (JSON in) saw a chapter
    assert not any("Zyxwv" in c for c in calls)
    assert tex.read_bytes() == content and tex.stat().st_mtime_ns == mtime


def test_edit_invalidates_only_that_chapter(project, monkeypatch):
    run(project, monkeypatch)
    (project / "ch2.md").write_text("# Two\n\nZyxwvtwo edited.\n")
    built, calls = run(project, monkeypatch)
    assert built == ["ch2.tex", "root.tex"]
    assert not any("Zyxwvone" in c for c in calls)
    assert "edited" in Path("build/ch2.tex").read_text()


@pytest.mark.parametrize("change", ["root_template", "cli_option", "environment",
                                    "figure", "bundled_figure_deleted", "tex_modified"])
def test_change_invalidates(project, monkeypatch, change):
    run(project, monkeypatch, "--copy-figures")
    if change == "root_template":
        root = project / "root.md"
        root.write_text(root.read_text().replace("template: book", "template: report"))
    elif change == "environment":  # texmark, pandoc or panflute changed
        monkeypatch.setattr(texcache.pf, "__version__", "0.0-other")
    elif change == "figure":
        fig = project / "images" / "fig.png"
        fig.write_bytes(PNG + b"\0")
    elif change == "bundled_figure_deleted":
        Path("build/figures/fig.png").unlink()
    elif change == "tex_modified":
        Path("build/ch1.tex").write_text("something else")
    extra = () if change == "cli_option" else ("--copy-figures",)
    built, _ = run(project, monkeypatch, *extra)
    assert "ch1.tex" in built
    if change in ("figure", "bundled_figure_deleted", "tex_modified"):
        assert built == ["ch1.tex", "root.tex"]
        assert Path("build/figures/fig.png").read_bytes() == (project / "images/fig.png").read_bytes()


def test_no_cache_rebuilds_everything(project, monkeypatch):
    run(project, monkeypatch)
    built, calls = run(project, monkeypatch, "--no-cache")
    assert built == ["ch1.tex", "ch2.tex", "root.tex"]
    assert any("Zyxwvone" in c for c in calls)


@pytest.mark.parametrize("garbage", ["{not json", "[]", '{"key": 1}', ""])
def test_corrupt_entry_is_a_miss(project, monkeypatch, garbage):
    run(project, monkeypatch)
    expected = Path("build/ch1.tex").read_bytes()
    for name in ("ch1.json", "ch1.embeds.json"):
        Path("build/.texmark-cache", name).write_text(garbage)
    built, _ = run(project, monkeypatch)
    assert built == ["ch1.tex", "root.tex"]
    assert Path("build/ch1.tex").read_bytes() == expected
    built, _ = run(project, monkeypatch)
    assert built == ["root.tex"]


def test_user_filters_disable_caching(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    md = tmp_path / "ch.md"
    md.write_text("---\npandoc_args: ['--lua-filter=f.lua']\n---\n\ntext\n")
    calls = []

    def fake_build_tex(input_md, output_tex, **kwargs):
        calls.append(kwargs)
        Path(output_tex).parent.mkdir(exist_ok=True)
        Path(output_tex).write_text("tex")

    for _ in range(2):
        texcache.cached_build_tex(fake_build_tex, str(md), "build/ch.tex", build_dir="build")
    md.write_text("text\n")
    for _ in range(2):
        texcache.cached_build_tex(fake_build_tex, str(md), "build/ch.tex", build_dir="build",
                                  filters=["my-filter"])
        texcache.cached_build_tex(fake_build_tex, str(md), "build/ch.tex", build_dir="build",
                                  filters_module="my_filters")
    assert len(calls) == 6
    texcache.cached_build_tex(fake_build_tex, str(md), "build/ch.tex", build_dir="build")
    texcache.cached_build_tex(fake_build_tex, str(md), "build/ch.tex", build_dir="build")
    assert len(calls) == 7
