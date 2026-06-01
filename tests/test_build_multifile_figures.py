"""Integration tests for figure resolution across multi-file builds (Item 9)."""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import main


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "multifile_figures"
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


def _copy_fixture(tmp_path):
    """Copy the fixture into tmp_path; return the project root inside tmp_path."""
    dst = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR, dst)
    return dst


def test_chapter_relative_figure_resolves_against_chapter_dir(tmp_path, monkeypatch):
    """An embedded chapter's ``![](images/eof.png)`` resolves under the chapter's own dir."""
    proj = _copy_fixture(tmp_path)
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(proj / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    chapter_tex = (build_dir / "lgm.tex").read_text()
    # The chapter figure must NOT be left as build-dir-relative ``images/eof.png``;
    # that would point at <build>/images/eof.png (wrong). It must resolve back to
    # the chapter's source location.
    assert "images/eof.png" in chapter_tex
    expected = os.path.relpath(proj / "chapters" / "images" / "eof.png", build_dir)
    assert expected in chapter_tex, (
        f"chapter figure path not resolved to chapter-relative source; "
        f"expected substring {expected!r} in:\n{chapter_tex}"
    )


def test_leading_slash_url_resolves_against_project_root(tmp_path, monkeypatch):
    """A leading-slash URL in an embedded chapter resolves against ``Project.project_root``."""
    proj = _copy_fixture(tmp_path)
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(proj / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    chapter_tex = (build_dir / "lgm.tex").read_text()
    expected = os.path.relpath(proj / "repo-images" / "foo.png", build_dir)
    assert expected in chapter_tex, (
        f"leading-slash URL did not resolve against project_root; "
        f"expected substring {expected!r} in:\n{chapter_tex}"
    )


def test_copy_figures_collects_embed_figures(tmp_path, monkeypatch):
    """copy_figures=true bundles figures referenced by embedded chapters."""
    proj = _copy_fixture(tmp_path)
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(proj / "root.md"), "-d", str(build_dir),
            "--copy-figures"]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    bundle = build_dir / "figures"
    assert (bundle / "eof.png").is_file(), (
        f"chapter-local figure not bundled into {bundle}"
    )
    assert (bundle / "foo.png").is_file(), (
        f"leading-slash figure not bundled into {bundle}"
    )
    # Both must survive the master pass's manifest write.
    manifest = (bundle / ".texmark-figures").read_text().splitlines()
    assert "eof.png" in manifest
    assert "foo.png" in manifest
