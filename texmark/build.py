#!/usr/bin/env python3
import subprocess
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
        return bool(meta)
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


def build_tex(input_md, output_tex, template='', bib_file='', build_dir='build', filters=None, journal_template=None, filters_module=None):
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
        "texmark-filter",
        ] + (filters or metadata.get('filters', []))

    # Step 1: Run pandoc to get JSON AST with filters applied, and updated metadata
    cmd_json = []
    for f in filters:
        cmd_json.extend(['--filter', f])
    cmd_json.extend(args)

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


def compile_pdf(input_tex, output_pdf, engine='pdflatex', build_dir='build', images_dir='images', bib_file='references.bib', resource_path=''):
    """
    Step 2: Compile LaTeX source into PDF.
    """
    if resource_path:
        print(f"Resource path: {resource_path}")
        run(f"rsync -r {resource_path}/ {build_dir}/", shell=True)
        # os.environ['TEXINPUTS'] = f"{resource_path}:" + os.environ.get('TEXINPUTS', '')

    run(f"rsync -r {Path(images_dir)} {build_dir}/", shell=True)
    run(f"rsync {input_tex} {build_dir}/", shell=True)
    run(f"rsync {bib_file} {build_dir}/", shell=True)
    cmd = [engine, '-interaction=nonstopmode', Path(input_tex).name]
    run(cmd, cwd=build_dir, check=False)
    bibcmd = ["bibtex", Path(input_tex).with_suffix(".aux").name]
    run(bibcmd, cwd=build_dir, check=False)
    run(cmd, cwd=build_dir, check=False)
    run(cmd, cwd=build_dir, check=False)
    # Rename/move the generated PDF if needed
    actual_pdf = Path(build_dir) / Path(input_tex).with_suffix(".pdf").name
    if Path(output_pdf) != actual_pdf:
        run(['mv', str(actual_pdf), output_pdf])


def main():

    parser = argparse.ArgumentParser(description='Two-step build: Markdown → LaTeX → PDF')
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
    parser.add_argument('--images', default='images', help='images directory')
    args = parser.parse_args()

    # Derive filenames
    build_dir = Path(args.build)
    tex_file = args.tex or build_dir / Path(args.input).with_suffix(".tex").name
    pdf_file = args.output or build_dir / Path(args.input).with_suffix(".pdf").name

    metadata = build_tex(args.input, tex_file, template=args.template, bib_file=args.bib, filters=args.filters, journal_template=args.journal_template, filters_module=args.filters_module)

    if args.pdf:
        compile_pdf(tex_file, pdf_file, args.engine, args.build, args.images, bib_file=metadata.get('bibliography'), resource_path=metadata.get('resource_path'))


if __name__ == '__main__':
    main()