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
              copy_figures=None, figure_folders=None, project_root=None):
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
    if bib_file:
        bib_args = ['--bibliography', bib_file]
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

    # Step 2. Render Jinja2 Template
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(resource_path))
    env.filters['join_if_list'] = join_if_list
    template = env.get_template(template_name)

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
        f.write(template.render(body=body, **metadata))  # Includes authors/abstract

    metadata["resource_path"] = str(resource_path)
    return metadata


def compile_pdf(input_tex, output_pdf, engine='pdflatex', build_dir='build', bib_file='references.bib', resource_path=''):
    """
    Step 2: Compile LaTeX source into PDF.
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
        src = Path(f)
        if src.parent.resolve() != build_dir.resolve():
            shutil.copy2(src, build_dir)
    cmd = [engine, '-interaction=nonstopmode', Path(input_tex).name]
    run(cmd, cwd=build_dir, check=False)
    bibcmd = ["bibtex", Path(input_tex).with_suffix(".aux").name]
    run(bibcmd, cwd=build_dir, check=False)
    run(cmd, cwd=build_dir, check=False)
    run(cmd, cwd=build_dir, check=False)
    actual_pdf = Path(build_dir) / Path(input_tex).with_suffix(".pdf").name
    if Path(output_pdf) != actual_pdf:
        # copy (not move) so the destination inode is preserved across rebuilds —
        # PDF viewers like evince keep scroll position when content changes in place.
        shutil.copyfile(actual_pdf, output_pdf)


def main():

    parser = argparse.ArgumentParser(description='Two-step build: Markdown → LaTeX → PDF')
    parser.add_argument('--version', action='version', version=f'%(prog)s {texmark.__version__}')
    parser.add_argument('input', help='Input markdown file')
    parser.add_argument('-j', '--journal-template', help='Pandoc LaTeX + filter template family. Update journal -> template yaml field)')
    parser.add_argument('-t', '--template', help='Pandoc LaTeX template. Update template yaml field)')
    parser.add_argument('-f', '--filters', nargs='*', help='Additional, custom filters. By default the pre-defined, custom filters for the journal are used via the `texmark-filter` utility.')
    parser.add_argument('--filters-module', help='Load a custom filter module. This is a Python module that may extend the filters dict defined in the `texmark.shared` module.')
    parser.add_argument('-o', '--output', help='Final PDF output filename')
    parser.add_argument('-e', '--engine', default='pdflatex', help='LaTeX engine (e.g. pdflatex, xelatex)')
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

    # Derive filenames
    build_dir = Path(args.build)
    tex_file = args.tex or build_dir / Path(args.input).with_suffix(".tex").name
    pdf_file = args.output or build_dir / Path(args.input).with_suffix(".pdf").name

    metadata = build_tex(args.input, tex_file, template=args.template, bib_file=args.bib,
                         build_dir=args.build,
                         filters=args.filters, journal_template=args.journal_template,
                         filters_module=args.filters_module, packages=args.packages,
                         copy_figures=args.copy_figures,
                         figure_folders=args.figure_folders,
                         project_root=args.project_root)

    if args.pdf:
        compile_pdf(tex_file, pdf_file, args.engine, args.build,
                    bib_file=metadata.get('bibliography'),
                    resource_path=metadata.get('resource_path'))


if __name__ == '__main__':
    main()