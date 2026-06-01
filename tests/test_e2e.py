"""PDF-level end-to-end integration tests using tectonic (Item 19).

These tests skip when tectonic or pandoc is not on PATH. They exercise the
full pipeline: markdown → pandoc filters → LaTeX → real PDF via tectonic.
"""
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import main
from tests import pandoc_available


FIXTURE_E2E = Path(__file__).parent / "fixtures" / "e2e"
REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


@pytest.fixture(autouse=True)
def _local_texmark_on_pythonpath(monkeypatch):
    """Ensure pandoc subprocess filters import this checkout's texmark."""
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


def _skip_without_tectonic():
    if shutil.which("tectonic") is None:
        pytest.skip("tectonic not on PATH")


@pytest.mark.e2e
def test_e2e_multifile_pdf(tmp_path, monkeypatch):
    """Two-chapter article builds to a real PDF via tectonic."""
    _skip_without_tectonic()

    src = FIXTURE_E2E / "multifile"
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = [
        "texmark",
        str(src / "root.md"),
        "-d", str(build_dir),
        "--pdf",
        "--backend", "tectonic",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    pdf = build_dir / "root.pdf"
    assert pdf.exists(), f"PDF not produced: {pdf}"
    assert pdf.stat().st_size > 0, "PDF file is empty"
    assert pdf.read_bytes()[:4] == b"%PDF", "File does not start with PDF magic bytes"


@pytest.mark.e2e
def test_e2e_main_si_cross_refs(tmp_path, monkeypatch):
    """Main + SI companion fixture: both PDFs produced, SI label resolves in aux."""
    _skip_without_tectonic()

    # Copy companions fixture so both .md files are co-located in a writable dir.
    src = FIXTURE_E2E / "companions"
    doc_dir = tmp_path / "src"
    shutil.copytree(src, doc_dir)
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = [
        "texmark",
        str(doc_dir / "main.md"),
        "-d", str(build_dir),
        "--pdf",
        "--backend", "tectonic",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    # Both PDFs must exist and carry valid PDF magic.
    for stem in ("main", "si"):
        pdf = build_dir / f"{stem}.pdf"
        assert pdf.exists(), f"{stem}.pdf not produced"
        assert pdf.read_bytes()[:4] == b"%PDF", f"{stem}.pdf lacks PDF magic bytes"

    # SI's aux must contain the label fig:noise with a resolved (non-??) value.
    # tectonic --keep-intermediates retains .aux files alongside the .pdf.
    si_aux = build_dir / "si.aux"
    assert si_aux.exists(), "si.aux not found; tectonic may not have kept intermediates"
    aux_text = si_aux.read_text(errors="replace")
    assert r"\newlabel{fig:noise}" in aux_text, (
        "\\newlabel{fig:noise} missing from si.aux — label not defined in SI"
    )
    m = re.search(r"\\newlabel\{fig:noise\}\{([^}]*)\}", aux_text)
    assert m is not None
    assert "??" not in m.group(1), (
        f"fig:noise still unresolved (??) in si.aux: {m.group(1)!r}"
    )

    # main.log must show xr-hyper importing si.aux and the si:fig:noise
    # reference resolving. xr-hyper imports external labels into LaTeX's
    # in-memory label table, so they don't appear in main.aux directly —
    # we verify resolution through the log instead.
    main_log = build_dir / "main.log"
    assert main_log.exists(), "main.log not found"
    main_log_text = main_log.read_text(errors="replace")
    assert "IMPORTING LABELS FROM si.aux" in main_log_text, (
        "xr-hyper did not attempt to import si.aux"
    )
    assert "Reference `si:fig:noise' on page" not in main_log_text, (
        "si:fig:noise still appears in undefined-reference warnings in main.log"
    )
