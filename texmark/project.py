"""Project model: discover embedded files and companions from a list of input markdowns."""

from __future__ import annotations

import io
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
import panflute as pf
import pypandoc


@dataclass
class Project:
    root_file: Path
    embedded_files: list[Path]
    companion_files: list[Path]
    metadata: dict
    project_root: Path = field(default=None)

    def __repr__(self) -> str:
        return (
            f"Project(root={self.root_file.name!r}, "
            f"embedded={[p.name for p in self.embedded_files]}, "
            f"companions={[p.name for p in self.companion_files]}, "
            f"project_root={str(self.project_root)!r})"
        )


def _detect_git_root(directory: Path) -> Path | None:
    """Return the git repo root containing directory, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def _scan_ast_for_embeds(markdown_path: Path) -> list[Path]:
    """Parse a markdown file's body via pandoc AST and return Image URLs ending in .md."""
    text = markdown_path.read_text()
    post = frontmatter.loads(text)

    ast_json = pypandoc.convert_text(
        frontmatter.dumps(post),
        format="markdown+footnotes",
        to="json",
    )
    doc = pf.load(io.StringIO(ast_json))

    found: list[Path] = []

    def collect(elem, doc):
        url = None
        if isinstance(elem, pf.Image):
            url = elem.url
        elif (isinstance(elem, pf.Link)
              and 'include' in elem.classes):
            url = elem.url
        if url and url.lower().endswith(".md") and not url.startswith(("http://", "https://")):
            found.append((markdown_path.parent / url).resolve())

    doc.walk(collect)
    return found


def _detect_cycle(root: Path, edges: dict[Path, list[Path]]) -> None:
    """Raise ValueError if there is a cycle reachable from root."""
    visited: set[Path] = set()
    stack: list[Path] = [root]
    path: list[Path] = []

    def dfs(node: Path) -> None:
        if node in path:
            cycle = " -> ".join(str(p) for p in path[path.index(node):] + [node])
            raise ValueError(f"Embed cycle detected: {cycle}")
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        for child in edges.get(node, []):
            dfs(child)
        path.pop()

    dfs(root)


def resolve_project(inputs: list[Path], project_root: Path | None = None) -> Project:
    """Discover embedded files and companions from a list of input markdowns.

    The first input is the root document. Its YAML frontmatter provides
    ``metadata`` and the ``companions:`` key. Each input's body is scanned
    for ``Image`` nodes whose URL ends in ``.md`` (embed syntax).

    ``project_root`` sets the base path for leading-slash image URLs. When
    omitted, it is resolved from (in order): root YAML ``project_root`` key,
    git toplevel of the root's directory, fallback to the root's parent dir.
    """
    if not inputs:
        raise ValueError("resolve_project requires at least one input file")

    root = Path(inputs[0]).resolve()

    # Load root metadata
    root_text = root.read_text()
    root_post = frontmatter.loads(root_text)
    metadata = dict(root_post.metadata)

    # Resolve companion files (root YAML only)
    raw_companions = metadata.get("companions", []) or []
    if isinstance(raw_companions, str):
        raw_companions = [raw_companions]
    companion_files: list[Path] = [(root.parent / p).resolve() for p in raw_companions]

    # Collect embedded files across all inputs (deduped, first-occurrence order).
    # Also scan discovered embeds recursively to enable full cycle detection.
    embed_edges: dict[Path, list[Path]] = {}
    embedded_files: list[Path] = []
    seen_embeds: set[Path] = set()

    scan_queue: list[Path] = [Path(inp).resolve() for inp in inputs]
    scanned: set[Path] = set()

    # First pass: scan all inputs and record their direct embeds
    for inp in inputs:
        src = Path(inp).resolve()
        children = _scan_ast_for_embeds(src)
        embed_edges[src] = children
        scanned.add(src)
        for child in children:
            if child not in seen_embeds:
                seen_embeds.add(child)
                embedded_files.append(child)

    # Second pass: recursively scan discovered embeds to build the full graph
    # for cycle detection (but don't add further-nested embeds to embedded_files)
    pending = list(embedded_files)
    while pending:
        src = pending.pop(0)
        if src in scanned:
            continue
        scanned.add(src)
        if src.exists():
            children = _scan_ast_for_embeds(src)
            embed_edges[src] = children
            for child in children:
                if child not in scanned:
                    pending.append(child)

    # Cycle detection (starting from root)
    _detect_cycle(root, embed_edges)

    # Embeds and companions must be mutually exclusive
    companion_set = set(companion_files)
    overlap = companion_set & seen_embeds
    if overlap:
        names = ", ".join(str(p) for p in overlap)
        raise ValueError(
            f"These files appear as both companions and embeds, which is not allowed: {names}"
        )

    # Resolve project_root with precedence: kwarg > YAML > git > fallback
    if project_root is not None:
        resolved_root = Path(project_root).resolve()
    elif "project_root" in metadata:
        resolved_root = (root.parent / metadata["project_root"]).resolve()
    else:
        git_root = _detect_git_root(root.parent)
        resolved_root = git_root if git_root is not None else root.parent

    return Project(
        root_file=root,
        embedded_files=embedded_files,
        companion_files=companion_files,
        metadata=metadata,
        project_root=resolved_root,
    )
