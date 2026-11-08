"""agujournal template: Plain Language Summary placement and Key Points list (issue #3)."""
import re

import pytest

from texmark.build import build_tex
from tests import pandoc_available

pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


def _build(tmp_path, md_text):
    md = tmp_path / "doc.md"
    md.write_text(md_text)
    tex_path = tmp_path / "build" / "doc.tex"
    build_tex(
        str(md),
        str(tex_path),
        build_dir=str(tmp_path / "build"),
        journal_template="agujournal",
    )
    return tex_path.read_text()


def _keypoints_block(tex):
    m = re.search(r"\\begin\{keypoints\}(.*?)\\end\{keypoints\}", tex, re.S)
    assert m, "no keypoints environment in output"
    return m.group(1)


def test_pls_and_keypoints_sections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tex = _build(
        tmp_path,
        "---\ntitle: T\n---\n\n"
        "# Abstract\n\nThe abstract.\n\n"
        "# Plain Language Summary\n\nThe summary.\n\n"
        "# Key Points\n\n- Point one\n- Point two\n- Point three\n\n"
        "# Introduction\n\nHello.\n",
    )

    # PLS: no undefined environment, set as a heading after the abstract
    assert "plainlanguagesummary" not in tex
    end_abs = tex.index(r"\end{abstract}")
    pls = tex.index(r"\section*{Plain Language Summary}")
    assert end_abs < pls < tex.index("The summary.")
    assert tex.index("The abstract.") < end_abs

    # Key Points: one \item per point, no nested itemize
    kp = _keypoints_block(tex)
    assert r"\begin{itemize}" not in kp
    assert r"\end{itemize}" not in kp
    assert r"\tightlist" not in kp
    assert kp.count(r"\item") == 3
    items = [s.strip() for s in kp.split(r"\item")[1:]]
    assert items == ["Point one", "Point two", "Point three"]


@pytest.mark.parametrize("yaml_value,expected", [
    ("\n  - YAML one\n  - YAML two", ["YAML one", "YAML two"]),
    (" A single point", ["A single point"]),
])
def test_keypoints_from_yaml(tmp_path, monkeypatch, yaml_value, expected):
    monkeypatch.chdir(tmp_path)
    tex = _build(
        tmp_path,
        f"---\ntitle: T\nkeypoints:{yaml_value}\n---\n\n# Introduction\n\nHello.\n",
    )
    kp = _keypoints_block(tex)
    items = [s.strip() for s in kp.split(r"\item")[1:]]
    assert items == expected
    assert kp.split(r"\item")[0].strip() == ""
