"""Tests for texmark/project.py — Project model and resolve_project()."""

import shutil
import textwrap
from pathlib import Path

import pytest

from texmark.project import Project, resolve_project


pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc binary not available on PATH",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Basic Project dataclass
# ---------------------------------------------------------------------------

def test_project_fields(tmp_path):
    root = write(tmp_path, "root.md", """\
        ---
        title: Root
        companions: [si.md]
        ---
        Body text.
        """)
    si = write(tmp_path, "si.md", "---\ntitle: SI\n---\nSI body.\n")

    project = resolve_project([root])

    assert project.root_file == root.resolve()
    assert project.embedded_files == []
    assert project.companion_files == [si.resolve()]
    assert project.metadata["title"] == "Root"
    assert "root.md" in repr(project)


def test_project_repr_informative(tmp_path):
    root = write(tmp_path, "root.md", "---\ntitle: Root\n---\nBody.\n")
    project = resolve_project([root])
    r = repr(project)
    assert "root.md" in r
    assert "embedded" in r
    assert "companions" in r


# ---------------------------------------------------------------------------
# Embed discovery from Image nodes
# ---------------------------------------------------------------------------

def test_single_embed(tmp_path):
    ch = write(tmp_path, "chapter.md", "---\ntitle: Chapter\n---\nChapter body.\n")
    root = write(tmp_path, "root.md", """\
        ---
        title: Root
        ---
        ![](chapter.md)
        """)

    project = resolve_project([root])

    assert project.embedded_files == [ch.resolve()]
    assert project.companion_files == []


def test_remote_url_not_embedded(tmp_path):
    root = write(tmp_path, "root.md", """\
        ---
        title: Root
        ---
        ![remote](https://example.com/chapter.md)
        """)

    project = resolve_project([root])
    assert project.embedded_files == []


def test_non_md_image_not_embedded(tmp_path):
    root = write(tmp_path, "root.md", """\
        ---
        title: Root
        ---
        ![Figure](figure.png)
        """)

    project = resolve_project([root])
    assert project.embedded_files == []


def test_embeds_deduped_preserves_first_occurrence(tmp_path):
    ch1 = write(tmp_path, "ch1.md", "---\ntitle: Ch1\n---\nBody.\n")
    ch2 = write(tmp_path, "ch2.md", "---\ntitle: Ch2\n---\nBody.\n")
    root = write(tmp_path, "root.md", """\
        ---
        title: Root
        ---
        ![](ch1.md)

        Some text.

        ![](ch2.md)

        Some more text.

        ![](ch1.md)
        """)

    project = resolve_project([root])

    assert project.embedded_files == [ch1.resolve(), ch2.resolve()]


def test_multiple_inputs_embeds_union(tmp_path):
    ch1 = write(tmp_path, "ch1.md", "---\ntitle: Ch1\n---\nBody.\n")
    ch2 = write(tmp_path, "ch2.md", "---\ntitle: Ch2\n---\nBody.\n")
    root = write(tmp_path, "root.md", """\
        ---
        title: Root
        ---
        ![](ch1.md)
        """)
    extra = write(tmp_path, "extra.md", """\
        ---
        title: Extra
        ---
        ![](ch2.md)
        """)

    project = resolve_project([root, extra])

    assert project.embedded_files == [ch1.resolve(), ch2.resolve()]
    # Only root companions are honoured
    assert project.companion_files == []


def test_multiple_inputs_only_root_companions(tmp_path):
    si = write(tmp_path, "si.md", "---\ntitle: SI\n---\n")
    root = write(tmp_path, "root.md", "---\ncompanions: [si.md]\n---\n")
    extra = write(tmp_path, "extra.md", "---\ncompanions: [other.md]\n---\n")

    project = resolve_project([root, extra])

    assert project.companion_files == [si.resolve()]


# ---------------------------------------------------------------------------
# Root metadata
# ---------------------------------------------------------------------------

def test_root_metadata_is_first_input(tmp_path):
    root = write(tmp_path, "root.md", "---\ntitle: Root Title\nbibliography: refs.bib\n---\nBody.\n")
    project = resolve_project([root])
    assert project.metadata["title"] == "Root Title"
    assert project.metadata["bibliography"] == "refs.bib"


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------

def test_embed_companion_overlap_raises(tmp_path):
    shared = write(tmp_path, "shared.md", "---\ntitle: Shared\n---\nBody.\n")
    root = write(tmp_path, "root.md", """\
        ---
        title: Root
        companions: [shared.md]
        ---
        ![](shared.md)
        """)

    with pytest.raises(ValueError, match="companions and embeds"):
        resolve_project([root])


def test_cycle_detection_raises(tmp_path):
    a = write(tmp_path, "a.md", """\
        ---
        title: A
        ---
        ![](b.md)
        """)
    b = write(tmp_path, "b.md", """\
        ---
        title: B
        ---
        ![](a.md)
        """)

    with pytest.raises(ValueError, match="cycle"):
        resolve_project([a])


def test_no_inputs_raises():
    with pytest.raises((ValueError, IndexError)):
        resolve_project([])
