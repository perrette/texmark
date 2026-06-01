"""Tests for the multi-pass build loop with companions (Item 6).

These tests mock ``compile_pdf`` so they exercise the orchestration logic
in ``main()`` without invoking a real LaTeX engine.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from texmark.build import _aux_files_snapshot, MAX_PASSES
from texmark.project import resolve_project
from tests import pandoc_available


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "companions"
REPO_ROOT = Path(__file__).parent.parent


pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


@pytest.fixture(autouse=True)
def _subprocess_finds_local_texmark(monkeypatch):
    """Ensure pandoc-launched filter subprocesses import this checkout's texmark."""
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


def _copy_companions_fixture(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    for name in ("main.md", "si.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())
    return src


def _aux_paths(build_dir: Path) -> tuple[Path, Path]:
    return build_dir / "main.aux", build_dir / "si.aux"


def test_aux_snapshot_returns_bytes_per_doc(tmp_path):
    src = _copy_companions_fixture(tmp_path)
    project = resolve_project([src / "main.md"])
    build_dir = tmp_path / "build"
    build_dir.mkdir()

    # Missing files → empty bytes
    snap0 = _aux_files_snapshot(project, build_dir)
    assert snap0 == {"main": b"", "si": b""}

    (build_dir / "main.aux").write_bytes(b"main-aux")
    (build_dir / "si.aux").write_bytes(b"si-aux")
    snap1 = _aux_files_snapshot(project, build_dir)
    assert snap1 == {"main": b"main-aux", "si": b"si-aux"}


def _run_main(src_dir: Path, build_dir: Path, monkeypatch):
    from texmark.build import main as build_main

    monkeypatch.chdir(src_dir.parent)
    argv = ["texmark", str(src_dir / "main.md"), "-d", str(build_dir), "--pdf"]
    monkeypatch.setattr(sys, "argv", argv)
    build_main()


def test_loop_converges_immediately_when_aux_is_stable(tmp_path, monkeypatch):
    """With a no-op compile_pdf (never writes .aux), snapshots stay empty and
    the loop exits after the second pass having detected equality with the
    first. compile_pdf call count = 2 × (1 + 1 companion) = 4."""
    src = _copy_companions_fixture(tmp_path)
    build_dir = tmp_path / "build"

    calls = []

    def fake_compile(input_tex, output_pdf, **kw):
        calls.append(Path(input_tex).name)

    with patch("texmark.build.compile_pdf", side_effect=fake_compile):
        _run_main(src, build_dir, monkeypatch)

    assert calls.count("main.tex") == 2
    assert calls.count("si.tex") == 2
    assert len(calls) == 4


def test_loop_exits_when_pass_n_matches_pass_n_minus_one(tmp_path, monkeypatch):
    """Pass 1 writes A1, pass 2 onward write A2 (stable). Pass 3's snapshot
    matches pass 2's → exit after 3 passes. compile_pdf calls = 3 × 2 = 6."""
    src = _copy_companions_fixture(tmp_path)
    build_dir = tmp_path / "build"

    pass_count = {"n": 0}
    seen_tex_names_per_pass: list[set[str]] = []

    def fake_compile(input_tex, output_pdf, **kw):
        # Each pass invokes compile_pdf once per (root + companion). Track
        # by counting unique tex names since the last "pass boundary".
        name = Path(input_tex).name
        if not seen_tex_names_per_pass or name in seen_tex_names_per_pass[-1]:
            seen_tex_names_per_pass.append({name})
            pass_count["n"] += 1
        else:
            seen_tex_names_per_pass[-1].add(name)

        # Write deterministic aux bytes that change between pass 1 and pass 2,
        # then stay constant from pass 2 onward.
        build = Path(output_pdf).parent
        aux = build / Path(input_tex).with_suffix(".aux").name
        if pass_count["n"] == 1:
            aux.write_bytes(name.encode() + b"-pass1")
        else:
            aux.write_bytes(name.encode() + b"-stable")

    with patch("texmark.build.compile_pdf", side_effect=fake_compile):
        _run_main(src, build_dir, monkeypatch)

    assert pass_count["n"] == 3
    # 3 passes × (root + 1 companion) = 6 compile_pdf calls
    total = sum(len(s) for s in seen_tex_names_per_pass)
    assert total == 6


def test_loop_caps_at_max_passes_and_warns_when_not_converging(tmp_path, monkeypatch, caplog):
    """If aux files keep changing every pass, the loop caps at MAX_PASSES and
    logs a warning."""
    src = _copy_companions_fixture(tmp_path)
    build_dir = tmp_path / "build"

    counter = {"n": 0}

    def fake_compile(input_tex, output_pdf, **kw):
        # Write a unique aux byte sequence per call → snapshots never repeat.
        counter["n"] += 1
        aux = Path(output_pdf).parent / Path(input_tex).with_suffix(".aux").name
        aux.write_bytes(f"unique-{counter['n']}".encode())

    import logging
    caplog.set_level(logging.WARNING, logger="texmark")

    with patch("texmark.build.compile_pdf", side_effect=fake_compile):
        _run_main(src, build_dir, monkeypatch)

    # MAX_PASSES × (root + 1 companion)
    assert counter["n"] == MAX_PASSES * 2
    assert any(
        "did not converge" in rec.message for rec in caplog.records
    ), [rec.message for rec in caplog.records]


def test_single_input_no_companions_is_single_pass(tmp_path, monkeypatch):
    """A solo doc (no companions, no embeds) takes exactly one compile_pdf call."""
    md = tmp_path / "solo.md"
    md.write_text(
        "---\ntitle: Solo\njournal:\n  template: arxiv\n---\n\n# Hello\n\nBody.\n"
    )
    build_dir = tmp_path / "build"

    calls = []

    def fake_compile(input_tex, output_pdf, **kw):
        calls.append(Path(input_tex).name)

    monkeypatch.chdir(tmp_path)
    argv = ["texmark", str(md), "-d", str(build_dir), "--pdf"]
    monkeypatch.setattr(sys, "argv", argv)

    from texmark.build import main as build_main

    with patch("texmark.build.compile_pdf", side_effect=fake_compile):
        build_main()

    assert calls == ["solo.tex"]
