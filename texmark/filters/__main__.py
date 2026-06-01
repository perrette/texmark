#!/usr/bin/env python3

import os
import sys
import json
import re
import hashlib
import shutil
import subprocess
from pathlib import Path
import importlib
import panflute as pf
from texmark.logs import logger
from texmark.shared import filters
from texmark.sectiontracker import SectionFilter
from texmark.filters.tabular import table_to_latex

def _is_remote_url(url):
    return url.startswith(('http://', 'https://', 'data:'))

def strip_leading_slash(elem, doc):
    # Image URLs are managed by resolve_image_paths, which uses the
    # leading slash as a signal that the path is project-root-relative
    # (GitHub convention). Stripping it here would erase that signal.
    if isinstance(elem, pf.Image):
        return
    if hasattr(elem, 'url'):
        if elem.url.startswith('/'):
            # Remove leading slash to make it repo-root relative (like GitHub)
            elem.url = elem.url.lstrip('/')


class ResolveImagePathsFilter:
    """Rewrite figure URLs based on the ``copy_figures`` metadata flag.

    Default mode (``copy_figures: false``): each local image URL is
    rewritten to a path relative to ``build_dir`` that points back at the
    original file on disk. No files are copied. If the user provides
    ``figure_folders``, a ``\\graphicspath{...}`` block is injected at the
    start of the document and figures that live under any of those folders
    get short URLs (relative to the matching folder); figures elsewhere
    fall back to the relpath-from-build_dir form.

    Bundle mode (``copy_figures: true`` / ``--copy-figures``): every local
    figure referenced by the document is copied flat into
    ``<build_dir>/figures/`` and the URL in the .tex is rewritten
    accordingly. Files keep their basename when unique; when two figures
    share a basename but have different contents they are disambiguated as
    ``<stem>-<short-content-hash><ext>``. Any top-level figure file left in
    ``<build_dir>/figures/`` from a previous build that the current
    document no longer references is removed. ``figure_folders`` is
    ignored in this mode.

    Inputs from metadata:
      - ``build_dir`` — directory in which pdflatex will run.
      - ``source_dir`` — directory of the input markdown; URLs resolve
        relative to it (matching GitHub's preview behaviour).
      - ``copy_figures`` — selects the mode above.
      - ``figure_folders`` — list of absolute paths (resolved upstream by
        ``build_tex``) to feed LaTeX's ``\\graphicspath``.

    Remote URLs (handled upstream by ``texmark-download-images``, which
    drops files under ``<build_dir>/figures/<hash>/<basename>``) are left
    alone in both modes; the cleanup pass only touches top-level files in
    ``<build_dir>/figures/``, so remote-download subdirectories are
    preserved.
    """

    BUNDLE_SUBDIR = "figures"
    MANIFEST_NAME = ".texmark-figures"
    HASH_LEN = 7  # git-style short hash

    def __init__(self):
        self._reset()

    def _reset(self):
        self.copy_mode = False
        self.build_dir = Path("build")
        self.source_dir = Path(".")
        # texmark's invocation directory; last-resort fallback for
        # project_root resolution when no explicit setting and no git
        # repo is detected.
        self.cwd = Path(".")
        # Project root (per the GitHub leading-slash convention):
        # resolved on demand from explicit metadata -> git rev-parse
        # --show-toplevel (run from source_dir) -> cwd.
        self._project_root = None
        # original-url -> bundle-relative path written into the .tex
        self.url_map = {}
        # basenames of files we put under <build_dir>/figures/ this run
        self.copied = set()
        # absolute Paths fed to LaTeX's \graphicspath (non-copy mode only)
        self.figure_folders = []
        # Explicit project_root from metadata, or None to auto-detect.
        self._project_root_explicit = None

    def _detect_project_root(self):
        """Resolve the project_root used to interpret leading-slash URLs.

        Detection order:
          1. Explicit ``project_root`` metadata (yaml or CLI), if set.
          2. ``git rev-parse --show-toplevel`` run from source_dir, so
             submodules / worktrees resolve to their own root rather than
             the outer repo's.
          3. cwd (texmark's invocation directory) as a last resort.

        Result is cached on the instance for the rest of the build.
        """
        if self._project_root is not None:
            return self._project_root
        if self._project_root_explicit:
            self._project_root = Path(self._project_root_explicit).resolve()
            return self._project_root
        try:
            out = subprocess.check_output(
                ['git', 'rev-parse', '--show-toplevel'],
                cwd=self.source_dir,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
            if out:
                self._project_root = Path(out).resolve()
                return self._project_root
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired, OSError):
            pass
        self._project_root = self.cwd
        return self._project_root

    def _resolve_local_url(self, url):
        """Resolve a (local) image URL to an absolute Path on disk.

        Markdown semantics:
          - Leading slash → strip and resolve against ``project_root``
            (GitHub convention: ``/foo`` means "<repo>/foo"). The
            ``project_root`` detection chain handles git submodules
            (rev-parse runs from source_dir) and non-git projects (falls
            back to cwd).
          - No leading slash → resolve against source_dir only, per the
            markdown spec (paths are relative to the document).

        Returns None when the resolved path doesn't exist — pdflatex
        will surface the missing-figure error at compile time, and
        texmark-download-images output (already build_dir-relative)
        falls through to None too.
        """
        if url.startswith('/'):
            stripped = url.lstrip('/')
            p = (self._detect_project_root() / stripped).resolve()
            if p.exists():
                return p
            return None
        p = (self.source_dir / url).resolve()
        if p.exists():
            return p
        return None

    @staticmethod
    def _content_hash(path, length=HASH_LEN):
        h = hashlib.sha1()
        h.update(Path(path).read_bytes())
        return h.hexdigest()[:length]

    def _copy_into_bundle(self, src, safe_name):
        dst = self.build_dir / self.BUNDLE_SUBDIR / safe_name
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Match sync_tree's size+mtime quick-check so rebuilds don't
        # needlessly bump mtimes (PDF viewers like evince care).
        if dst.exists():
            s, d = src.stat(), dst.stat()
            if s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime):
                self.copied.add(safe_name)
                return
        shutil.copy2(src, dst)
        self.copied.add(safe_name)

    def _plan_and_copy(self, seen):
        """Decide bundle name for each url, copy files, populate url_map.

        ``seen`` is ``{url: resolved_abs_path}`` for every distinct local
        URL in the document whose file exists on disk.
        """
        by_basename = {}
        for url, p in seen.items():
            by_basename.setdefault(p.name, []).append((url, p))

        for basename, members in by_basename.items():
            # Group members by content hash to detect real collisions
            # (same basename + different content). Same-content references
            # collapse to a single bundled copy.
            contents = {}
            for url, p in members:
                contents.setdefault(self._content_hash(p), []).append((url, p))

            if len(contents) == 1:
                safe = basename
                _, src = members[0]
                self._copy_into_bundle(src, safe)
                for url, _ in members:
                    self.url_map[url] = f"{self.BUNDLE_SUBDIR}/{safe}"
                continue

            stem = Path(basename).stem
            ext = Path(basename).suffix
            for h, group in contents.items():
                safe = f"{stem}-{h}{ext}"
                _, src = group[0]
                self._copy_into_bundle(src, safe)
                for url, _ in group:
                    self.url_map[url] = f"{self.BUNDLE_SUBDIR}/{safe}"

    def _short_url_via_folder(self, abs_path):
        """If ``abs_path`` lives under any figure_folders entry, return the
        path written into the .tex (relative to that folder), else None.

        Folder order matters: matches the search order pdflatex will use
        when resolving via ``\\graphicspath``.
        """
        for folder in self.figure_folders:
            try:
                return str(abs_path.relative_to(folder))
            except ValueError:
                continue
        return None

    def _emit_graphicspath_block(self):
        """Return a ``\\graphicspath{...}`` RawBlock built from the
        configured figure_folders, with each entry expressed relative to
        build_dir (so the .tex stays portable as long as the build/source
        tree moves together)."""
        parts = []
        for folder in self.figure_folders:
            rel = os.path.relpath(folder, self.build_dir)
            # LaTeX requires a trailing slash on each \graphicspath entry.
            parts.append(f"{{{rel}/}}")
        latex = "\\graphicspath{" + "".join(parts) + "}"
        return pf.RawBlock(latex, format='latex')

    def prepare(self, doc):
        self._reset()
        self.copy_mode = bool(doc.get_metadata('copy_figures', False))
        self.build_dir = Path(doc.get_metadata('build_dir', 'build')).resolve()
        self.source_dir = Path(doc.get_metadata('source_dir', '.')).resolve()
        self.cwd = Path(doc.get_metadata('cwd', '.')).resolve()
        self._project_root_explicit = doc.get_metadata('project_root', None) or None
        # figure_folders only have meaning in non-copy mode; ignored
        # silently otherwise so users can keep them set in yaml without
        # toggling.
        if not self.copy_mode:
            self.figure_folders = [
                Path(p) for p in (doc.get_metadata('figure_folders', []) or [])
            ]
            if self.figure_folders:
                doc.content.insert(0, self._emit_graphicspath_block())
            return

        seen = {}
        def _collect(elem, _doc):
            if isinstance(elem, pf.Image) and elem.url and not _is_remote_url(elem.url):
                if elem.url not in seen:
                    p = self._resolve_local_url(elem.url)
                    if p is not None:
                        seen[elem.url] = p
            return None

        doc.walk(_collect, doc=doc)
        if seen:
            self._plan_and_copy(seen)

    def action(self, elem, doc):
        if not isinstance(elem, pf.Image):
            return
        url = elem.url
        if not url or _is_remote_url(url):
            return

        if self.copy_mode:
            new = self.url_map.get(url)
            if new:
                elem.url = new
            return

        candidate = self._resolve_local_url(url)
        if candidate is None:
            # Could be a path already rewritten by texmark-download-images
            # (build-dir relative) or a missing file we'll let pdflatex
            # complain about. Either way, don't second-guess it here.
            return

        short = self._short_url_via_folder(candidate)
        if short is not None:
            elem.url = short
        else:
            elem.url = os.path.relpath(candidate, self.build_dir)

    def _read_manifest(self):
        """Return the set of basenames this filter put in the bundle on
        the previous build. On the first build (manifest absent) fall
        back to the current top-level listing so pre-manifest cruft also
        gets cleaned up — after that the manifest is authoritative."""
        bundle = self.build_dir / self.BUNDLE_SUBDIR
        manifest = bundle / self.MANIFEST_NAME
        if manifest.exists():
            return {line for line in manifest.read_text().splitlines() if line}
        if not bundle.is_dir():
            return set()
        return {p.name for p in bundle.iterdir() if p.is_file()}

    def finalize(self, doc):
        if not self.copy_mode:
            return
        bundle = self.build_dir / self.BUNDLE_SUBDIR
        if not bundle.is_dir():
            return
        previous = self._read_manifest()
        for name in previous - self.copied:
            p = bundle / name
            if p.is_file():
                logger.info(f"removing stale bundled figure: {p}")
                p.unlink()
        # Persist the new manifest (sorted for stable, diffable output).
        manifest = bundle / self.MANIFEST_NAME
        manifest.write_text("\n".join(sorted(self.copied)) + "\n")


resolve_image_paths = ResolveImagePathsFilter()

def tag_figures(elem, doc):
    if isinstance(elem, pf.Figure):
        # if it does not already exist, add an identifier to the figure so that it can be referenced
        # in the text using \ref{fig:figure-id}
        # use the content image url as the identifier, e.g. /image/figure.png -> fig:figure
        if not elem.identifier:
            # Generate a unique identifier for the figure
            image = elem.content[0].content[0]
            tag = f'fig:{Path(image.url).stem}'
            logger.info(fr"Tagging figure: {tag}")
            elem.identifier = tag
    return elem


ATTR_RE = re.compile(r'\s*\{([^}]+)\}\s*$')

def parse_attr_string(attr_string):
    identifier = ''
    classes = []
    attributes = {}
    for token in attr_string.split():
        if token.startswith('#'):
            identifier = token[1:]
        elif token.startswith('.'):
            classes.append(token[1:])
        elif '=' in token:
            key, val = token.split('=', 1)
            attributes[key] = val
    return identifier, classes, attributes

def extract_table_identifier(elem, doc):
    if not isinstance(elem, pf.Table):
        return

    cap = elem.caption
    if not cap or not cap.content:
        return

    # at the time of writing, the caption is ListContainer(Plain(...))
    if not (
        cap.content
        and len(cap.content) == 1
        and isinstance(cap.content[0], pf.Plain)
    ):
        logger.warning(f"Caption content is not a Plain block: {cap.content}")
        return

    inlines = cap.content[0].content

    last = inlines[-1]
    if not isinstance(last, pf.Str):
        return

    last_text = pf.stringify(last).strip()
    match = ATTR_RE.search(last_text)
    if not match:
        return

    attr_string = match.group(1)
    identifier, classes, attributes = parse_attr_string(attr_string)

    cap.content[:] = [pf.Plain(*inlines[:-1])]

    if identifier:
        elem.identifier = identifier
    if classes:
        elem.classes.extend(classes)
    if attributes:
        elem.attributes.update(attributes)


def stringify_captions(elem, doc):

    if isinstance(elem, (pf.Table)):
        extract_table_identifier(elem, doc)

    if isinstance(elem, (pf.Figure, pf.Table)):
        # Safely extract caption
        if elem.caption:
            caption_text = pf.convert_text(elem.caption.content,
                input_format='panflute',
                output_format='latex',
                extra_args=['--natbib']
            )

            # Science template: make the first sentence bold
            if doc.get_metadata('journal', {}).get("template") == "science":
                caption_parts = caption_text.split(".")
                caption_parts[0] = r"\textbf{" + caption_parts[0] + r"}"
                caption_text = ".".join(caption_parts)

            elem.caption.content = [pf.RawBlock(caption_text, format='latex')]


def apply_figure_defaults(elem, doc):
    """Apply global figure-width and figure-span metadata to figures.

    - `figure-width` (default `100%`) sets the default image width when none is
      given on the figure itself. Percent values are interpreted by pandoc as a
      fraction of `\\linewidth`, which inside `figure*` automatically expands
      to the full text width.
    - `figure-span` (default `column`) — when set to `full`, wrap the figure in
      a `figure*` environment so it spans both columns in two-column layouts.
      Can be set globally via document metadata or per-figure via the image's
      attribute syntax: ``![cap](img){figure-span=full}``.
    """
    if not isinstance(elem, pf.Figure):
        return

    target = elem.content[0].content[0]
    if "width" not in target.attributes:
        target.attributes['width'] = doc.get_metadata('figure-width', '100%')

    # Pandoc puts ``#id`` on the Figure but other ``{...}`` attributes on the
    # inner Image, so check both before falling back to the document default.
    span = (
        target.attributes.pop('figure-span', None)
        or elem.attributes.pop('figure-span', None)
        or doc.get_metadata('figure-span', 'column')
    )

    if span == 'full':
        latex = pf.convert_text(
            elem,
            input_format='panflute',
            output_format='latex',
            extra_args=['--natbib'],
        )
        latex = latex.replace(r'\begin{figure}', r'\begin{figure*}')
        latex = latex.replace(r'\end{figure}', r'\end{figure*}')
        return pf.RawBlock(latex, format='latex')

basic_filters = [strip_leading_slash, resolve_image_paths, stringify_captions, tag_figures, apply_figure_defaults, table_to_latex ]

default_filters = basic_filters

si_sections = ["appendix", "supplementary-material", "supplementary-information"]
method_sections = ["methods", "materials-and-methods", "methodology"]


copernicus_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=['abstract', 'acknowledgements', 'author-contributions', 'competing-interests'] + si_sections,
        remap_command_sections={
            'introduction': r'\introduction',
            'conclusions': r'\conclusions'
        },
        sections_map={
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

for journal in ["copernicus", "cp", "esd"]:
    filters[journal] = copernicus_filters


def force_cite(elem, doc):
    if isinstance(elem, pf.Cite):
        keys = [c.id for c in elem.citations]
        key_str = ",".join(keys)
        # Build as raw LaTeX \cite{}
        return pf.RawInline(f'\\cite{{{key_str}}}', format='latex')

def header_to_unnumbered(elem, doc):
    if isinstance(elem, pf.Header):
        # Convert header to raw LaTeX \section*{...}
        level = elem.level
        content = pf.stringify(elem)
        latex_cmd = f'\\{"sub" * (level - 1)}section*{{{content}}}'
        return pf.RawBlock(latex_cmd, format='latex')

def header_to_paragraph(elem, doc):
    if isinstance(elem, pf.Header):
        # Convert header to raw LaTeX \section*{...}
        level = elem.level
        content = pf.stringify(elem)
        latex_cmd = f'\\paragraph*{{{content+"."}}}'
        return pf.RawBlock(latex_cmd, format='latex')


science_filters = [
    *basic_filters,
    force_cite,
    SectionFilter(
        extract_sections=['abstract', 'acknowledgements', 'author-contributions',
                            'competing-interests', 'methods', 'materials-and-methods'] + si_sections,
        sections_map={
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'materialandmethods' for section in method_sections},
            **{section: 'appendix' for section in si_sections},
        },
    ),
    header_to_paragraph,
        ]

filters['science'] = science_filters


ametsoc_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=[
            'abstract', 'acknowledgements', 'acknowledgments',
            'significance', 'significance-statement', 'capsule',
            'data-availability', 'data-availability-statement',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'significance-statement': 'significance',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            **{section: 'appendix' for section in si_sections},
        },
        drop_sections=['author-contributions'],
    ),
]

for journal in ["ametsoc", "amsoc", "jclim", "jas", "mwr", "jamc", "jhm", "jpo", "jtech", "waf", "bams"]:
    filters[journal] = ametsoc_filters


arxiv_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions', 'competing-interests',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

filters['arxiv'] = arxiv_filters
filters['preprint'] = arxiv_filters


elsarticle_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords', 'highlights',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions', 'credit', 'competing-interests',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'credit': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

filters['elsarticle'] = elsarticle_filters
filters['elsevier'] = elsarticle_filters


def apacite_cite(elem, doc):
    """Rewrite natbib-style citations to apacite (used by agujournal2019).

    Markdown ``@key`` becomes panflute Cite(mode=AuthorInText) which pandoc's
    natbib emitter would render as ``\\citet{key}``. apacite uses ``\\citeA``
    for the same in-text form. Bracketed ``[@key]`` (NormalCitation) maps to
    apacite's plain ``\\cite``.
    """
    if isinstance(elem, pf.Cite):
        keys = ",".join(c.id for c in elem.citations)
        first_mode = elem.citations[0].mode if elem.citations else 'NormalCitation'
        cmd = r'\citeA' if first_mode == 'AuthorInText' else r'\cite'
        return pf.RawInline(f'{cmd}{{{keys}}}', format='latex')


agu_filters = [
    *basic_filters,
    apacite_cite,
    SectionFilter(
        extract_sections=[
            'abstract', 'plain-language-summary', 'keypoints', 'key-points',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'plain-language-summary': 'plainlanguagesummary',
            'key-points': 'keypoints',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            **{section: 'appendix' for section in si_sections},
        },
        drop_sections=['author-contributions'],
    ),
]

for journal in ["agujournal", "agu", "jgr", "grl", "james", "earthsfuture", "wrr", "rog"]:
    filters[journal] = agu_filters


springernature_filters = [
    *basic_filters,
    force_cite,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'funding', 'ethics', 'ethics-approval',
            'author-contributions', 'competing-interests',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            'ethics-approval': 'ethics',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

for journal in ["springernature", "springer", "nature", "naturecomms", "natclimchange", "natgeoscience", "scirep"]:
    filters[journal] = springernature_filters


pnas_filters = [
    *basic_filters,
    force_cite,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords',
            'significance', 'significance-statement',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions',
            'competing-interests', 'declaration', 'author-declaration',
            'equal-authors',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'significance-statement': 'significance',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            'declaration': 'competinginterests',
            'author-declaration': 'competinginterests',
            'equal-authors': 'equalauthors',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

filters['pnas'] = pnas_filters


def run_filters(doc):

    if doc is not None:
        journal = doc.get_metadata('journal')
    else:
        logger.warning(f'doc is None')
        journal = {'template': 'default'}

    if doc.get_metadata('filters_module'):
        filters_module = doc.get_metadata('filters_module')
        logger.info(f"Loading filters module: {filters_module}")
        importlib.import_module(filters_module)


    if journal.get("template") is None:
        logger.warning(f'doc is None')

    filters_ = filters.get(journal.get("template"))
    if filters_ is None:
        logger.warning(f'No filters found for journal template: {journal.get("template")}. Using default filter.')
        filters_ = default_filters


    for filter in filters_:
        logger.info(f'Running filter: {filter} on {doc}')
        doc = pf.run_filter(action=filter.action if hasattr(filter, 'action') else filter,
                   prepare=filter.prepare if hasattr(filter, 'prepare') else None,
                   finalize=filter.finalize if hasattr(filter, 'finalize') else None,
                   doc=doc)
        assert isinstance(doc, pf.Doc), f"Filter {filter} did not return a valid doc object"

    return doc


def main(doc=None):
    doc = pf.load(sys.stdin)
    doc = run_filters(doc)
    return pf.dump(doc)


if __name__ == '__main__':
    main()