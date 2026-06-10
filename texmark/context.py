"""BuildContext: the internal values build_tex threads to the filters.

These are texmark-internal (build directory layout, effective figure
settings, cross-reference peer lists), not document content. They travel
under the single reserved ``texmark`` metadata key because document
metadata is the only channel that survives the JSON AST round-trip to
subprocess filters (pandoc ``--filter``); in-process filters read the same
key, so there is one code path for both.

Keeping everything under one key means the user's metadata namespace and
the Jinja template context see a single ``texmark`` entry instead of a
dozen loose internal keys that could collide with user YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


METADATA_KEY = 'texmark'


@dataclass
class BuildContext:
    # Directory in which pdflatex will run.
    build_dir: str = 'build'
    # Directory of the input markdown; relative figure URLs resolve here.
    source_dir: str = '.'
    # texmark's invocation directory.
    cwd: str = '.'
    # Base for GitHub-style leading-slash figure URLs. Resolved by
    # texmark.project (kwarg > yaml > git toplevel > cwd); None means the
    # resolve_image_paths filter falls back to cwd.
    project_root: str | None = None
    # Bundle figures into <build_dir>/figures/ vs reference them in place.
    copy_figures: bool = False
    # Absolute paths fed to LaTeX's \graphicspath (non-copy mode only).
    figure_folders: list = field(default_factory=list)
    # Peer document stems for cross-document references (texmark-crossref).
    crossref_companion_stems: list = field(default_factory=list)
    crossref_embed_stems: list = field(default_factory=list)
    crossref_own_stem: str = ''
    # Multi-file build: the figure-bundle manifest accumulates across the
    # per-chunk filter runs instead of being replaced by each one.
    figure_manifest_accumulate: bool = False
    # 0 for the master document, 1 for body-only embed chunks (controls
    # \input vs \include emitted by texmark-embed).
    embed_depth: int = 0
    # Optional user module that extends the filter registry.
    filters_module: str | None = None

    def to_metadata(self) -> dict:
        """Plain dict to store under ``metadata['texmark']``."""
        return asdict(self)

    @classmethod
    def from_doc(cls, doc) -> 'BuildContext':
        """Read the context back from a panflute doc.

        Values coming through pandoc's metadata are stringly typed (YAML
        scalars become MetaString), so coerce each field explicitly.
        Missing keys take the dataclass defaults, which keeps standalone
        ``pandoc --filter`` invocations (no build_tex upstream) working.
        """
        raw = doc.get_metadata(METADATA_KEY, {}) or {}

        def _as_list(value):
            if value is None:
                return []
            if isinstance(value, str):
                return [value]
            return list(value)

        def _as_int(value, default=0):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            build_dir=str(raw.get('build_dir', 'build')),
            source_dir=str(raw.get('source_dir', '.')),
            cwd=str(raw.get('cwd', '.')),
            project_root=str(raw['project_root']) if raw.get('project_root') else None,
            copy_figures=bool(raw.get('copy_figures', False)),
            figure_folders=[str(p) for p in _as_list(raw.get('figure_folders'))],
            crossref_companion_stems=[str(s) for s in _as_list(raw.get('crossref_companion_stems'))],
            crossref_embed_stems=[str(s) for s in _as_list(raw.get('crossref_embed_stems'))],
            crossref_own_stem=str(raw.get('crossref_own_stem', '') or ''),
            figure_manifest_accumulate=bool(raw.get('figure_manifest_accumulate', False)),
            embed_depth=_as_int(raw.get('embed_depth', 0)),
            filters_module=str(raw['filters_module']) if raw.get('filters_module') else None,
        )
