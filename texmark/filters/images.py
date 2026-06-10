"""Figure-path resolution: rewrite local image URLs for the LaTeX build.

``ResolveImagePathsFilter`` is the single place where markdown image URLs are
mapped to paths pdflatex can resolve, in either of two modes (in-place
referencing or bundling into ``<build>/figures/``). ``strip_leading_slash``
handles the GitHub leading-slash convention for non-image links.
"""

import os
import hashlib
import shutil
from pathlib import Path

import panflute as pf

from texmark.logs import logger


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
        # texmark's invocation directory; fallback for project_root when no
        # explicit value is supplied.
        self.cwd = Path(".")
        # Project root (per the GitHub leading-slash convention). Set in
        # prepare() from explicit metadata, else cwd. Root *detection*
        # (YAML key, git toplevel) is texmark.project's job; build.py
        # threads the resolved value through metadata so this filter never
        # has to detect anything itself.
        self.project_root = Path(".")
        # original-url -> bundle-relative path written into the .tex
        self.url_map = {}
        # basenames of files we put under <build_dir>/figures/ this run
        self.copied = set()
        # absolute Paths fed to LaTeX's \graphicspath (non-copy mode only)
        self.figure_folders = []
        # URLs already warned about this run (one warning per URL)
        self._warned = set()
        # Multi-file build flag: finalize merges into the existing manifest
        # instead of treating self.copied as the canonical set.
        self._manifest_accumulate = False

    def _warn_unresolved(self, url):
        """Log once per URL when a local figure path cannot be resolved.

        Paths that resolve from build_dir are silently accepted: that is
        what texmark-download-images rewrites remote URLs to, and pdflatex
        runs in build_dir so they work as-is.
        """
        if url in self._warned:
            return
        self._warned.add(url)
        if (self.build_dir / url).exists():
            return
        if url.startswith('/'):
            base = f"project root '{self.project_root}'"
            hint = " (set --project-root or the project_root yaml key?)"
        else:
            base = f"source dir '{self.source_dir}'"
            hint = ""
        logger.warning(
            f"texmark: figure '{url}' not found under {base}{hint}; "
            "path left unchanged, LaTeX will not find it."
        )

    def _resolve_local_url(self, url):
        """Resolve a (local) image URL to an absolute Path on disk.

        Markdown semantics:
          - Leading slash → strip and resolve against ``project_root``
            (GitHub convention: ``/foo`` means "<repo>/foo").
          - No leading slash → resolve against source_dir only, per the
            markdown spec (paths are relative to the document).

        Returns None (with a warning) when the resolved path doesn't exist —
        pdflatex will surface the missing-figure error at compile time.
        texmark-download-images output (already build_dir-relative) also
        returns None, silently: it needs no rewriting.
        """
        if url.startswith('/'):
            stripped = url.lstrip('/')
            p = (self.project_root / stripped).resolve()
        else:
            p = (self.source_dir / url).resolve()
        if p.exists():
            return p
        self._warn_unresolved(url)
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
        explicit_root = doc.get_metadata('project_root', None) or None
        self.project_root = Path(explicit_root).resolve() if explicit_root else self.cwd
        self._manifest_accumulate = bool(doc.get_metadata('figure_manifest_accumulate', False))
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
            # Build-dir-relative (texmark-download-images output) or missing
            # (already warned). Either way, leave the URL unchanged.
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
        if self._manifest_accumulate:
            # Multi-file build: each chunk only sees a slice of the figure
            # set; union into the manifest rather than treating self.copied
            # as authoritative. Stale-cleanup is skipped here.
            keep = previous | self.copied
        else:
            for name in previous - self.copied:
                p = bundle / name
                if p.is_file():
                    logger.info(f"removing stale bundled figure: {p}")
                    p.unlink()
            keep = self.copied
        # Persist the new manifest (sorted for stable, diffable output).
        manifest = bundle / self.MANIFEST_NAME
        manifest.write_text("\n".join(sorted(keep)) + "\n")


resolve_image_paths = ResolveImagePathsFilter()
