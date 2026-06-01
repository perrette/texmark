#!/usr/bin/env python3
import subprocess
import shutil
from pathlib import Path
import os
import sys
import pypandoc
import json
import yaml
import jinja2
import frontmatter
import argparse
import texmark
import json
import panflute as pf
import io
from texmark.logs import logger

rootpath = Path(texmark.__file__).resolve().parent

def run(cmd, shell=False, check=True, **kwargs):
    print(cmd if shell else ' '.join(cmd))
    return subprocess.run(cmd, shell=shell, check=check, **kwargs)


def sync_tree(src, dst):
    """Copy src into dst recursively, skipping files whose size + mtime already match.

    Mimics rsync's default quick-check heuristic so rebuilds don't re-copy a large
    images tree on every run. Files only — no symlink preservation, no deletions.
    """
    src, dst = Path(src), Path(dst)
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            s, d = path.stat(), target.stat()
            if s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime):
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def normalize_metadata(meta):
    """
    Recursively convert panflute metadata into plain JSON-serializable Python dict.
    (Plain strings, lists, dicts, no MetaInlines etc.)
    """
    if isinstance(meta, pf.MetaInlines) or isinstance(meta, pf.MetaBlocks):
        return pf.stringify(meta)
    elif isinstance(meta, pf.MetaString):
        return meta.text
    elif isinstance(meta, pf.MetaBool):
        return meta.boolean
    elif isinstance(meta, pf.MetaList):
        return [normalize_metadata(item) for item in meta]
    elif isinstance(meta, pf.MetaMap):
        return {key: normalize_metadata(value) for key, value in meta.items()}
    else:
        # Primitive types (str, int, etc.) or unknown - return as is
        return meta


def join_if_list(value, sep='\n\n'):
    if isinstance(value, list):
        return sep.join(value)
    return value


def build_tex(input_md, output_tex, template='', bib_file='', build_dir='build',
              filters=None, journal_template=None, filters_module=None, packages=None,
              copy_figures=None, figure_folders=None, project_root=None, body_only=False,
              companion_stems=None, embed_stems=None, own_stem=None,
              figure_manifest_accumulate=False, embed_depth=0):
    # 1. Parse Markdown
    input_text = open(input_md).read()
    post = frontmatter.loads(input_text)
    metadata = post.metadata
    content = post.content

    if not journal_template:
        journal_template = metadata.get('journal', {}).get('template', 'default')
        if not journal_template:
            journal_template = "default"

    metadata.setdefault('journal', {})['template'] = journal_template
    metadata.setdefault('longtable', False)
    metadata.setdefault('packages', []).extend(packages or [])

    # Make build_dir, source_dir and cwd visible to pandoc filters so they
    # can rewrite figure paths relative to where pdflatex will run.
    # cwd is the texmark invocation directory; figure URLs that don't
    # resolve from source_dir (the markdown's parent) fall back to it, so
    # GitHub-style "/images/foo.png" — which means "<repo>/images/foo.png"
    # — keeps working when the .md lives in a subdirectory like sources/.
    metadata['build_dir'] = str(Path(build_dir).resolve())
    metadata['source_dir'] = str(Path(input_md).resolve().parent)
    metadata['cwd'] = str(Path.cwd().resolve())
    if copy_figures is None:
        copy_figures = metadata.get('copy_figures', False)
    metadata['copy_figures'] = bool(copy_figures)

    # figure-folders feed LaTeX's \graphicspath in non-copy mode. CLI wins
    # over yaml; both are interpreted as CWD-relative and stored as
    # absolute paths so the filter doesn't have to repeat that work.
    if figure_folders is None:
        figure_folders = metadata.get('figure_folders', []) or []
    metadata['figure_folders'] = [str(Path(p).resolve()) for p in figure_folders]

    # project_root is what GitHub-style leading-slash URLs resolve
    # against. When set explicitly (CLI > yaml), the filter uses it
    # verbatim; otherwise the filter auto-detects via `git rev-parse
    # --show-toplevel` (run from source_dir, so submodules behave) and
    # falls back to cwd. We resolve CWD-relative paths here so the
    # filter doesn't have to.
    if project_root is None:
        project_root = metadata.get('project_root', None) or None
    metadata['project_root'] = str(Path(project_root).resolve()) if project_root else None

    # Cross-document references (Item 4): texmark-crossref reads these to
    # rewrite ``[](other.md#label)`` links to ``\ref{<other-stem>:label}``
    # and to emit a ``\usepackage{xr-hyper}`` + ``\externaldocument`` block
    # as the ``xr_preamble`` template variable. Each list is the set of
    # stems the active document can cross-reference; ``own_stem`` is the
    # active document's own stem, excluded from xr_targets.
    metadata['crossref_companion_stems'] = list(companion_stems or [])
    metadata['crossref_embed_stems'] = list(embed_stems or [])
    metadata['crossref_own_stem'] = own_stem or Path(input_md).stem

    # In multi-file builds, each body-only chunk and the master run
    # resolve_image_paths in their own subprocess. The chunk's local
    # ``self.copied`` is just its own slice of the figure set; treating it
    # as authoritative would let each chunk's finalize delete the previous
    # chunk's bundled figures. With this flag, finalize unions the new
    # copies into the on-disk manifest instead of replacing it.
    metadata['figure_manifest_accumulate'] = bool(figure_manifest_accumulate)

    # embed_depth: the texmark-embed filter uses this to pick \input vs
    # \include. Top-level (depth 0) embeds in book-family templates emit
    # \include so \includeonly can scope them; nested embeds (body-only
    # chunks pass embed_depth=1) always emit \input — LaTeX forbids nested
    # \include.
    metadata['embed_depth'] = int(embed_depth)

    # preamble: YAML field — custom LaTeX injected just before \begin{document}.
    # Supports: inline block scalar (starts with \ or contains \n), single
    # file path, or a list mixing both forms. Paths resolve relative to the
    # markdown's directory. Result is stored as `user_preamble` in metadata so
    # every template can emit {{ user_preamble | default("") }}.
    preamble_raw = metadata.get('preamble', None)
    if preamble_raw is not None:
        _src_dir = Path(input_md).resolve().parent
        def _resolve_preamble_item(item: str) -> str:
            if item.startswith('\\') or '\n' in item:
                return item
            return (_src_dir / item).read_text()
        if isinstance(preamble_raw, list):
            metadata['user_preamble'] = '\n'.join(
                _resolve_preamble_item(str(it)) for it in preamble_raw
            )
        else:
            metadata['user_preamble'] = _resolve_preamble_item(str(preamble_raw))
    else:
        metadata['user_preamble'] = ''

     # 2. Apply filters and convert to AST

    if filters_module:
        metadata['filters_module'] = filters_module

    if not template:
        template = metadata.get('template')
        if not template:
            template = f'templates/{journal_template}/template.tex'

    template_folder = Path(template).parent
    template_name = Path(template).name
    resource_path = rootpath / template_folder

    if not bib_file:
        bib_file = metadata.get('bibliography', None)
    bib_args = ['--bibliography', bib_file] if bib_file else []
    args = bib_args + metadata.get('pandoc_args', []) + [
        "--natbib",
    ]

    filters = [
        "texmark-download-images",
        "texmark-journal",
        ] + (filters or metadata.get('filters', []))

    # Step 1: Run pandoc to get JSON AST with filters applied, and updated metadata.
    # Copy `args` so the --filter additions don't leak into the JSON->LaTeX
    # pass below, which would re-run every filter and double any stateful
    # transforms (e.g. resolve_image_paths injecting a \graphicspath block).
    cmd_json = list(args)
    for f in filters:
        cmd_json.extend(['--filter', f])

    post.metadata = metadata

    ast_json_str = pypandoc.convert_text(
        frontmatter.dumps(post),
        format="markdown+footnotes",
        to="json",
        extra_args=cmd_json,
    )

    doc = pf.load(io.StringIO(ast_json_str))  # <-- no input_format argument
    metadata.update(normalize_metadata(doc.metadata))

    # Step 2. Render Jinja2 Template (skipped for body-only chunks).
    if not body_only:
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(resource_path))
        env.filters['join_if_list'] = join_if_list
        master_template = env.get_template(template_name)

    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    Path(output_tex).parent.mkdir(parents=True, exist_ok=True)

    # Step 3: Render AST to LaTeX (filters not needed again)
    body = pypandoc.convert_text(
        ast_json_str,
        format="json",
        to="latex",
        extra_args=['--template', rootpath / "templates" / "body.tex"] + args,
    )

    with open(output_tex, "w") as f:
        if body_only:
            f.write(body)
        else:
            f.write(master_template.render(body=body, **metadata))  # Includes authors/abstract

    metadata["resource_path"] = str(resource_path)
    return metadata


def compile_pdf(input_tex, output_pdf, engine='pdflatex', build_dir='build',
                bib_file='references.bib', resource_path='', backend='latexmk'):
    """
    Step 2: Compile LaTeX source into PDF.

    backend selects the driver:
      - 'latexmk' (default): runs latexmk, which skips reruns whose inputs
        (.aux/.bbl/.fls) haven't changed. Typical incremental edit collapses
        to one engine pass instead of three.
      - 'raw': the original pdflatex → bibtex → pdflatex → pdflatex sequence,
        unconditionally. Use when latexmk isn't available.
      - 'tectonic': uses the standalone `tectonic` binary, which bundles
        engine + driver + bibtex-equivalent. `engine` is ignored in this mode.
    """
    build_dir = Path(build_dir)

    if resource_path:
        print(f"Resource path: {resource_path}")
        sync_tree(resource_path, build_dir)
        # os.environ['TEXINPUTS'] = f"{resource_path}:" + os.environ.get('TEXINPUTS', '')

    # Figure bundling (copy_figures mode) is handled inside the
    # resolve_image_paths filter during the pandoc pass, so we don't need
    # to stage anything here.
    for f in (input_tex, bib_file):
        if not f:
            continue
        src = Path(f)
        if not src.exists():
            continue
        if src.parent.resolve() != build_dir.resolve():
            shutil.copy2(src, build_dir)
    tex_name = Path(input_tex).name

    if backend == 'latexmk':
        # -f keeps latexmk going (matching the raw backend's check=False reruns)
        # even when an engine pass returns nonzero, so the .pdf still appears
        # for downstream inspection.
        engine_flag = {
            'pdflatex': '-pdf',
            'xelatex': '-pdfxe',
            'lualatex': '-pdflua',
        }.get(engine, '-pdf')
        cmd = ['latexmk', engine_flag, '-interaction=nonstopmode', '-f', tex_name]
        run(cmd, cwd=build_dir, check=False)
    elif backend == 'tectonic':
        cmd = ['tectonic', '--keep-intermediates', '--keep-logs', tex_name]
        run(cmd, cwd=build_dir, check=False)
    elif backend == 'raw':
        cmd = [engine, '-interaction=nonstopmode', tex_name]
        run(cmd, cwd=build_dir, check=False)
        bibcmd = ["bibtex", Path(input_tex).with_suffix(".aux").name]
        run(bibcmd, cwd=build_dir, check=False)
        run(cmd, cwd=build_dir, check=False)
        run(cmd, cwd=build_dir, check=False)
    else:
        raise ValueError(f"Unknown backend {backend!r}; use 'latexmk', 'raw', or 'tectonic'.")

    actual_pdf = Path(build_dir) / Path(input_tex).with_suffix(".pdf").name
    if Path(output_pdf) != actual_pdf:
        # copy (not move) so the destination inode is preserved across rebuilds —
        # PDF viewers like evince keep scroll position when content changes in place.
        shutil.copyfile(actual_pdf, output_pdf)


MAX_PASSES = 4


def _aux_files_snapshot(project, build_dir):
    """Return a dict mapping each root/companion stem to its current `.aux` bytes.

    Used by the multi-pass companion build loop to detect when cross-doc refs
    have stabilised. Missing files contribute empty bytes so the snapshot is
    well-defined on the very first pass (before any `.aux` exists).
    """
    build_dir = Path(build_dir)
    docs = [project.root_file] + list(project.companion_files)
    snapshot = {}
    for doc in docs:
        aux = build_dir / f"{doc.stem}.aux"
        try:
            snapshot[doc.stem] = aux.read_bytes()
        except FileNotFoundError:
            snapshot[doc.stem] = b""
    return snapshot


def watch_loop(do_build, paths, interval=0.5):
    """Rebuild whenever any of `paths` changes mtime. Loops until Ctrl-C.

    Callers are expected to have run an initial build already, so we prime
    mtimes here and only trigger do_build on subsequent changes.
    """
    import time
    paths = [Path(p) for p in paths if p]
    last = {}
    for p in paths:
        try:
            last[p] = p.stat().st_mtime
        except FileNotFoundError:
            pass
    print(f"texmark: watching {len(paths)} path(s); Ctrl-C to stop.")
    try:
        while True:
            time.sleep(interval)
            changed = False
            for p in paths:
                try:
                    mt = p.stat().st_mtime
                except FileNotFoundError:
                    continue
                if last.get(p) != mt:
                    last[p] = mt
                    changed = True
            if changed:
                try:
                    do_build()
                    print("texmark: build OK; watching for next change.")
                except Exception as e:
                    print(f"texmark: build failed: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\ntexmark: stopped watching.")


def main():

    parser = argparse.ArgumentParser(description='Two-step build: Markdown → LaTeX → PDF')
    parser.add_argument('--version', action='version', version=f'%(prog)s {texmark.__version__}')
    parser.add_argument('inputs', nargs='+', help='Input markdown file(s). The first is the root document.')
    parser.add_argument('-j', '--journal-template', help='Pandoc LaTeX + filter template family. Update journal -> template yaml field)')
    parser.add_argument('-t', '--template', help='Pandoc LaTeX template. Update template yaml field)')
    parser.add_argument('-f', '--filters', nargs='*', help='Additional, custom filters. By default the pre-defined, custom filters for the journal are used via the `texmark-filter` utility.')
    parser.add_argument('--filters-module', help='Load a custom filter module. This is a Python module that may extend the filters dict defined in the `texmark.shared` module.')
    parser.add_argument('-o', '--output', help='Final PDF output filename')
    parser.add_argument('-e', '--engine', default=None,
                        help='LaTeX engine (pdflatex, xelatex, lualatex). Default: pdflatex. '
                             'Ignored when --backend=tectonic. YAML key: engine.')
    parser.add_argument('-b', '--backend', choices=['latexmk', 'raw', 'tectonic'], default=None,
                        help='LaTeX driver. latexmk (default) skips reruns whose inputs haven\'t '
                             'changed — typically 2-3x faster on incremental edits. raw runs the '
                             'pdflatex+bibtex+pdflatex+pdflatex sequence unconditionally (use when '
                             'latexmk is unavailable). tectonic uses the standalone tectonic '
                             'binary. YAML key: backend.')
    parser.add_argument('-w', '--watch', action='store_true',
                        help='Rebuild whenever the input markdown, bibliography, or template '
                             'changes. Combine with an auto-reloading PDF viewer (zathura, '
                             'evince, okular) for live preview. Implies --pdf.')
    parser.add_argument('-d', '--build', default='build', help='build directory')
    parser.add_argument('--bib', help='bibliography file')
    parser.add_argument('--tex', help='LaTeX output filename')
    parser.add_argument('--pdf', action="store_true")
    parser.add_argument('--copy-figures', action='store_true', default=None,
                        help='copy every referenced figure into <build>/figures/ and rewrite paths in the .tex '
                             'so the build directory is self-contained (handy for journal submission). '
                             'The default is to keep figures in place and rewrite paths to point at the originals. '
                             'Yaml equivalent: copy_figures: true.')
    parser.add_argument('--figure-folders', nargs='*', default=None,
                        help='Folders to feed LaTeX\'s \\graphicspath. Paths are interpreted relative to the '
                             'current working directory. In the default (non-copy) mode, figures that live '
                             'under any of these folders get short URLs in the .tex; figures elsewhere fall '
                             'back to a path relative to the build dir. Ignored when --copy-figures is set. '
                             'Yaml equivalent: figure_folders: [<list>].')
    parser.add_argument('--project-root', default=None,
                        help='Project root used to resolve GitHub-style leading-slash figure URLs '
                             '(![](/images/foo.png) -> <project-root>/images/foo.png). Interpreted '
                             'relative to the current working directory. When unset, texmark detects '
                             'via `git rev-parse --show-toplevel` (run from the markdown\'s directory, '
                             'so submodules resolve correctly) and falls back to the current working '
                             'directory for non-git projects. Yaml equivalent: project_root: <path>.')
    parser.add_argument('--packages', nargs='*', help='custom latex packages to include')
    # Deprecated: figures are now discovered from the markdown URLs, and
    # (with --copy-figures) always bundled into <build>/images/. The flag
    # is accepted-and-ignored so existing invocations keep working.
    parser.add_argument('--images', help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.images is not None:
        print("warning: --images is deprecated and ignored; figures are now "
              "auto-detected from the markdown and (with --copy-figures) bundled "
              "into <build>/images/.", file=sys.stderr)

    # Derive filenames (from the root / first input)
    build_dir = Path(args.build)
    primary_input = args.inputs[0]
    tex_file = args.tex or build_dir / Path(primary_input).with_suffix(".tex").name
    pdf_file = args.output or build_dir / Path(primary_input).with_suffix(".pdf").name

    want_pdf = args.pdf or args.watch

    # Resolve the project once up-front: discovers embedded files (via
    # ![](file.md) body syntax) and companions (via `companions:` yaml).
    # When the resolved project has no embeds, no companions, and a
    # single input, downstream behaviour is identical to the historical
    # single-file pipeline.
    from texmark.project import resolve_project
    project = resolve_project([Path(p) for p in args.inputs])

    # Pre-compute the stem lists used by the crossref filter so they don't
    # need to be re-derived on every body-only/master build call below.
    companion_stems = [p.stem for p in project.companion_files]
    embed_stems = [p.stem for p in project.embedded_files]
    root_stem = Path(primary_input).stem

    # Effective project_root used for leading-slash figure URL resolution:
    # CLI override wins; otherwise the value resolved by ``resolve_project``
    # (yaml > git > root.parent) is threaded into every body-only embed and
    # the master build so all chapters interpret ``/foo`` against the same
    # base, instead of each running its own per-file ``git rev-parse``.
    effective_project_root = args.project_root or str(project.project_root)

    # In multi-file copy_figures mode, each body-only chunk runs the bundle
    # filter independently in its own subprocess. The filter's finalize
    # cleanup (which deletes files no longer in self.copied) would otherwise
    # wipe figures the previous chunk just copied. Tell the filter to
    # accumulate the on-disk manifest across chunks rather than treat its
    # local self.copied as authoritative.
    manifest_accumulate = bool(project.embedded_files)

    def do_build():
        # Resolve engine/backend per-build so editing YAML in --watch mode takes effect.
        # Precedence: CLI > YAML > built-in default.
        yaml_meta = frontmatter.loads(open(primary_input).read()).metadata
        engine = str(args.engine or yaml_meta.get('engine') or 'pdflatex')
        backend = str(args.backend or yaml_meta.get('backend') or 'latexmk')

        # Body-only builds for each embedded chapter, written as
        # `<build>/<stem>.tex` so the master's `\input{<stem>}` resolves at
        # LaTeX time. Embeds are not separately compiled.
        for embed_path in project.embedded_files:
            embed_tex = Path(args.build) / f"{embed_path.stem}.tex"
            build_tex(str(embed_path), str(embed_tex),
                      template=args.template, bib_file=args.bib,
                      build_dir=args.build,
                      filters=args.filters, journal_template=args.journal_template,
                      filters_module=args.filters_module, packages=args.packages,
                      copy_figures=args.copy_figures,
                      figure_folders=args.figure_folders,
                      project_root=effective_project_root,
                      body_only=True,
                      companion_stems=companion_stems,
                      embed_stems=embed_stems,
                      own_stem=embed_path.stem,
                      figure_manifest_accumulate=manifest_accumulate,
                      embed_depth=1)

        # Build the master .tex for the root.
        root_metadata = build_tex(
            primary_input, tex_file, template=args.template, bib_file=args.bib,
            build_dir=args.build,
            filters=args.filters, journal_template=args.journal_template,
            filters_module=args.filters_module, packages=args.packages,
            copy_figures=args.copy_figures,
            figure_folders=args.figure_folders,
            project_root=effective_project_root,
            companion_stems=companion_stems,
            embed_stems=embed_stems,
            own_stem=root_stem,
            figure_manifest_accumulate=manifest_accumulate,
        )

        # Build each companion's standalone .tex. Each companion gets the
        # universe of peers (root + sibling companions) minus itself so its
        # crossref filter can wire xr-hyper in both directions. Companions
        # are first-class documents: bibliography, template, and engine come
        # from the companion's own YAML, not the root's CLI overrides.
        companion_builds = []  # (companion_path, tex_path, pdf_path, metadata)
        for comp_path in project.companion_files:
            peers = [root_stem] + [s for s in companion_stems if s != comp_path.stem]
            comp_tex = build_dir / f"{comp_path.stem}.tex"
            comp_pdf = build_dir / f"{comp_path.stem}.pdf"
            comp_meta = build_tex(
                str(comp_path), str(comp_tex),
                build_dir=args.build,
                filters=args.filters,
                filters_module=args.filters_module, packages=args.packages,
                copy_figures=args.copy_figures,
                figure_folders=args.figure_folders,
                project_root=args.project_root,
                companion_stems=peers,
                own_stem=comp_path.stem,
            )
            companion_builds.append((comp_path, comp_tex, comp_pdf, comp_meta))

        if want_pdf:
            # Build target list: (input_tex, output_pdf, bib_file, resource_path).
            # Body-only embeds are inputs to the master, never compile targets.
            targets = [(
                tex_file, pdf_file,
                str(root_metadata.get('bibliography') or ''),
                str(root_metadata.get('resource_path') or ''),
            )]
            for _cp, c_tex, c_pdf, c_meta in companion_builds:
                targets.append((
                    c_tex, c_pdf,
                    str(c_meta.get('bibliography') or ''),
                    str(c_meta.get('resource_path') or ''),
                ))

            # Companions need multi-pass coordination: xr-hyper resolves
            # cross-doc refs by reading peer .aux files, so each pass may
            # change another doc's aux until they all stabilise. With no
            # companions there is nothing to coordinate — single pass.
            if project.companion_files:
                prev_snapshot = None
                for pass_idx in range(1, MAX_PASSES + 1):
                    for in_tex, out_pdf, bib, rp in targets:
                        compile_pdf(in_tex, out_pdf, engine=engine, build_dir=args.build,
                                    bib_file=bib, resource_path=rp, backend=backend)
                    cur_snapshot = _aux_files_snapshot(project, build_dir)
                    if prev_snapshot is not None and cur_snapshot == prev_snapshot:
                        break
                    prev_snapshot = cur_snapshot
                else:
                    logger.warning(
                        "texmark: companion build did not converge after "
                        f"{MAX_PASSES} passes; cross-refs may be stale"
                    )
            else:
                in_tex, out_pdf, bib, rp = targets[0]
                compile_pdf(in_tex, out_pdf, engine=engine, build_dir=args.build,
                            bib_file=bib, resource_path=rp, backend=backend)

        return root_metadata

    if args.watch:
        metadata = do_build()
        bib = metadata.get('bibliography')
        # The journal template lives under texmark's install dir; watching it
        # is convenient when iterating on a new template.
        rp = metadata.get('resource_path')
        tmpl_path = Path(str(rp)) / 'template.tex' if rp else None

        watch_paths: list = [primary_input, bib, tmpl_path]
        watch_paths.extend(project.embedded_files)
        watch_paths.extend(project.companion_files)

        for comp_path in project.companion_files:
            comp_meta = frontmatter.loads(comp_path.read_text()).metadata
            comp_bib = comp_meta.get('bibliography')
            if comp_bib:
                watch_paths.append(Path(comp_path).parent / comp_bib)
            comp_jt = comp_meta.get('journal', {}).get('template') or 'default'
            watch_paths.append(rootpath / f'templates/{comp_jt}/template.tex')

        # Deduplicate preserving first-occurrence order, dropping None/empty.
        seen_resolved: set[str] = set()
        deduped: list = []
        for p in watch_paths:
            if not p:
                continue
            key = str(Path(p).resolve())
            if key not in seen_resolved:
                seen_resolved.add(key)
                deduped.append(p)

        watch_loop(do_build, deduped)
    else:
        do_build()


if __name__ == '__main__':
    main()