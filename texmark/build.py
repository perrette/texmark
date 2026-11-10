#!/usr/bin/env python3
"""Two-step build: Markdown -> LaTeX -> PDF.

``build_tex`` turns one markdown document into a .tex file (pandoc pass with
filters, then a Jinja master template); ``compile_pdf`` drives the LaTeX
toolchain. ``main`` resolves the input files into a ``ProjectPlan`` (embeds,
companions, effective settings) and builds everything, optionally in a
watch loop.
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import frontmatter
import jinja2
import panflute as pf
from texmark import chain as _chain
import pypandoc

import texmark
from texmark.logs import logger
from texmark.shared import BOOK_FAMILY_TEMPLATES, body_formats
from texmark.context import BuildContext, METADATA_KEY as CONTEXT_METADATA_KEY
from texmark.filters import download_images as _filters_download_images
from texmark.filters import embed as _filters_embed
from texmark.filters import crossref as _filters_crossref
from texmark.filters.figures import expand_figstar_sentinels
from texmark import journals as _journals
from texmark import blockcache as _blockcache
from texmark import texcache as _texcache
from texmark.project import (Project, resolve_project, load_markdown, parse_markdown,
                             _scan_ast_for_embeds)


# In-process filters (texmark-journal in particular) call panflute's
# `pf.convert_text`, which looks up pandoc via `shutil.which('pandoc')`. When
# the user installed via `pypandoc_binary`, the bundled pandoc lives outside
# PATH — pypandoc finds it through its own resolver but panflute does not. So
# add the bundled binary's directory to PATH once at import time. Guarded
# because `get_pandoc_path()` raises if pandoc is missing entirely, and we
# want that failure to surface at build time rather than at import.
try:
    _pandoc_dir = os.path.dirname(pypandoc.get_pandoc_path())
except OSError:
    _pandoc_dir = ''
if _pandoc_dir and _pandoc_dir not in os.environ.get('PATH', '').split(os.pathsep):
    os.environ['PATH'] = _pandoc_dir + os.pathsep + os.environ.get('PATH', '')


# Built-in filters that can run inside this Python process instead of via
# pandoc's --filter mechanism. Each --filter spawns a fresh Python interpreter
# that re-imports panflute and round-trips the full AST through JSON; on a
# typical paper that's ~150-470 ms per filter, all of it startup. Routing the
# built-ins in-process saves ~600 ms per build_tex call.
_INPROC_FILTERS = {
    'texmark-download-images',
    'texmark-journal',
    'texmark-embed',
    'texmark-crossref',
}


def _inproc_chain(name, doc):
    """The filters a built-in filter name stands for, as a chain for
    ``texmark.chain.run_chain``."""
    if name == 'texmark-download-images':
        return [_filters_download_images.action]
    if name == 'texmark-journal':
        return _journals.filter_chain_for(doc)
    if name == 'texmark-embed':
        return [_filters_embed.embed_filter]
    if name == 'texmark-crossref':
        return [_filters_crossref.crossref_filter]
    raise ValueError(f"Not a built-in in-process filter: {name!r}")


rootpath = Path(texmark.__file__).resolve().parent


def run(cmd, shell=False, check=True, **kwargs):
    logger.info(cmd if shell else ' '.join(str(c) for c in cmd))
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


def meta_to_python(meta):
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
        return [meta_to_python(item) for item in meta]
    elif isinstance(meta, pf.MetaMap):
        return {key: meta_to_python(value) for key, value in meta.items()}
    else:
        # Primitive types (str, int, etc.) or unknown - return as is
        return meta


def join_if_list(value, sep='\n\n'):
    if isinstance(value, list):
        return sep.join(value)
    return value


def bib_files(value):
    """The ``bibliography`` metadata as a list of paths. Like pandoc, it may
    be a single path or a list of paths."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    return [str(value)]


def _resolve_rewrite_unicode(value, engine: str) -> bool:
    """Resolve ``rewrite_unicode`` (``auto``/``on``/``off`` or a bool) given
    the effective LaTeX engine. ``auto`` is the default and turns on only
    under pdflatex — lualatex/xelatex render UTF-8 natively and the user
    may prefer raw codepoints there for OpenType font shaping. Returns
    ``True`` to run the encoding rewrite, ``False`` to skip it.
    """
    if value is None or value == 'auto':
        return engine == 'pdflatex'
    if value in (True, 'on', 'true', 'yes', '1', 1):
        return True
    if value in (False, 'off', 'false', 'no', '0', 0):
        return False
    raise ValueError(
        f"invalid rewrite_unicode value: {value!r}; expected auto/on/off"
    )


# ---------------------------------------------------------------------------
# build_tex: one markdown document -> one .tex file
# ---------------------------------------------------------------------------

def _resolve_journal_template(metadata, journal_template):
    """Effective journal template (CLI > yaml > 'default'), written back to
    ``metadata['journal']['template']`` where the filters read it."""
    if not journal_template:
        journal_template = metadata['journal'].get('template', 'default')
        if not journal_template:
            journal_template = "default"
    metadata.setdefault('journal', {})['template'] = journal_template
    return journal_template


def _resolve_user_preamble(metadata, src_dir):
    """Resolve the ``preamble`` YAML field — custom LaTeX injected just before
    ``\\begin{document}``.

    Supports: inline block scalar (starts with \\ or contains a newline),
    single file path, or a list mixing both forms. Paths resolve relative to
    the markdown's directory. The result is rendered by every template as
    ``{{ user_preamble | default("") }}``.
    """
    preamble_raw = metadata.get('preamble', None)
    if preamble_raw is None:
        return ''

    def _resolve_item(item: str) -> str:
        if item.startswith('\\') or '\n' in item:
            return item
        return (src_dir / item).read_text()

    if isinstance(preamble_raw, list):
        return '\n'.join(_resolve_item(str(it)) for it in preamble_raw)
    return _resolve_item(str(preamble_raw))


def _set_yaml_metadata(doc, values):
    """Set ``values`` (plain Python) in the metadata of ``doc``, converted the
    way pandoc converts YAML front matter: strings are read as markdown, and
    so become MetaInlines/MetaBlocks. The values are written as a YAML block
    and parsed with ``parse_markdown``, which is cached, so an unchanged set
    of values (--watch rebuilds) costs no pandoc call."""
    yaml_block = frontmatter.dumps(frontmatter.Post('', **values))
    meta = pf.load(io.StringIO(parse_markdown(yaml_block))).metadata
    for key in list(meta.content):
        doc.metadata[key] = meta[key]


def _apply_filters_to_ast(doc, filters):
    """Run all filters on the parsed document.

    Fast path: when every filter is a built-in, walk the AST with in-process
    panflute filters, without any pandoc call. Each
    --filter would otherwise spawn a fresh Python interpreter to re-import
    panflute and round-trip the AST through JSON — ~150-470 ms per filter
    on a typical paper, all startup overhead.

    Mixed path: any user-supplied filter triggers the subprocess pipeline
    (one JSON -> JSON pandoc call with all filters) so custom filters keep
    working unchanged.

    Returns ``(ast_json_str, doc)`` — the filtered AST both as a JSON string
    (input to the body render) and as the loaded panflute doc (so the caller
    can pick up metadata the filters modified).
    """
    if all(f in _INPROC_FILTERS for f in filters):
        # One chain for all the built-ins, so that consecutive element-local
        # filters (e.g. download-images and the journal chain's first
        # filters) share document walks.
        chain = [flt for name in filters for flt in _inproc_chain(name, doc)]
        doc = _chain.run_chain(chain, doc)
        sink = io.StringIO()
        pf.dump(doc, sink)
        return sink.getvalue(), doc

    sink = io.StringIO()
    pf.dump(doc, sink)
    ast_json_str = pypandoc.convert_text(
        sink.getvalue(),
        format="json",
        to="json",
        extra_args=[arg for f in filters for arg in ('--filter', f)],
        verify_format=False,
    )
    return ast_json_str, pf.load(io.StringIO(ast_json_str))


def _render_body(ast_json_str, journal_template, metadata, pandoc_args):
    """Render the filtered AST to the LaTeX (or beamer) body string."""
    return _finish_body(_render_latex(ast_json_str, journal_template, metadata, pandoc_args))


def _finish_body(body):
    """Post-process the writer output (see ``_render_body``)."""
    # Rewrite ``apply_figure_defaults`` sentinels into figure*/end{figure*}.
    # See ``texmark.filters.figures.expand_figstar_sentinels`` for details.
    return expand_figstar_sentinels(body)


def _render_latex(ast_json_str, journal_template, metadata, pandoc_args):
    """The pandoc writer pass of ``_render_body``."""
    body_fmt = body_formats.get(journal_template, body_formats['default'])
    body_args = ['--template', rootpath / "templates" / body_fmt['template']] + pandoc_args
    # Beamer frames are sliced at --slide-level (heading depth that starts a new
    # frame). Surfaced from `beamer.slide_level` (default 2 -> "## Frame" begins a
    # frame); passed explicitly so behavior is deterministic. Only the beamer
    # body-format path takes this arg — article-class renders are untouched.
    if body_fmt['format'] == 'beamer':
        slide_level = (metadata.get('beamer') or {}).get('slide_level', 2)
        body_args.append(f'--slide-level={slide_level}')
    return pypandoc.convert_text(
        ast_json_str,
        format="json",
        to=body_fmt['format'],
        extra_args=body_args,
        verify_format=False,
    )


def _extra_include_directives(extra_includes, journal_template, metadata):
    """LaTeX directives for chapters declared only via the `chapters:` YAML
    key (not as body ``![](file.md)`` nodes): they have no embed node for
    texmark-embed to rewrite, so the master body gets their \\include /
    \\input directives appended here. Class-aware, matching the embed
    filter: book-family -> \\include."""
    is_book = journal_template in BOOK_FAMILY_TEMPLATES
    per_chapter = is_book and bool(metadata.get('bibliography_per_chapter'))
    cmd = '\\include' if is_book else '\\input'
    parts = []
    for stem in extra_includes:
        if per_chapter:
            # Mirror the embed filter: wrap top-level book-family chapters
            # in a biblatex refsection so each prints its own bibliography.
            parts.append(
                '\\begin{refsection}\n'
                f'\\include{{{stem}}}\n'
                '\\printbibliography[heading=subbibliography]\n'
                '\\end{refsection}\n'
            )
        else:
            parts.append(f'{cmd}{{{stem}}}\n')
    return ''.join(parts)


def build_tex(input_md, output_tex, template='', bib_file='', build_dir='build',
              filters=None, journal_template=None, filters_module=None, packages=None,
              copy_figures=None, figure_folders=None, project_root=None, body_only=False,
              companion_stems=None, embed_stems=None, own_stem=None,
              figure_manifest_accumulate=False, embed_depth=0,
              includeonly='', extra_includes=None, engine=None,
              rewrite_unicode=None, block_cache=None):
    # 1. Read the front matter and resolve effective metadata.
    text = open(input_md).read()
    metadata = load_markdown(text).metadata

    journal_template = _resolve_journal_template(metadata, journal_template)
    metadata.setdefault('longtable', False)
    metadata.setdefault('packages', []).extend(packages or [])

    # bibliography_per_chapter (Item 18) only makes sense for book-family
    # templates, which emit \include + carry the biblatex refsection scaffolding.
    # For article-class templates the flag is silently ignored at the template
    # and embed-filter level; warn once (on the master/companion build, not the
    # body-only chunks) so the user knows their flag had no effect.
    if (metadata.get('bibliography_per_chapter')
            and journal_template not in BOOK_FAMILY_TEMPLATES
            and not body_only):
        logger.warning(
            "texmark: bibliography_per_chapter requires a book-family template; ignoring."
        )

    # Internal build context for the pandoc filters: directory layout,
    # effective figure settings, cross-document reference peers. Stored
    # under the single reserved ``texmark`` metadata key (the only channel
    # that reaches subprocess filters) — see texmark/context.py for the
    # field meanings. Effective values resolve CLI > yaml; CWD-relative
    # paths are made absolute here so the filters don't have to.
    if copy_figures is None:
        copy_figures = metadata.get('copy_figures', False)
    if figure_folders is None:
        figure_folders = metadata.get('figure_folders', []) or []
    # project_root is what GitHub-style leading-slash URLs resolve against.
    # Root *detection* (yaml key > git toplevel > cwd) is texmark.project's
    # job; main() threads the resolved value into every build_tex call, so
    # the resolve_image_paths filter never detects anything itself (when
    # the key is unset, it falls back to cwd).
    if project_root is None:
        project_root = metadata.get('project_root', None) or None
    if filters_module is None:
        filters_module = metadata.get('filters_module', None) or None
    context = BuildContext(
        build_dir=str(Path(build_dir).resolve()),
        source_dir=str(Path(input_md).resolve().parent),
        cwd=str(Path.cwd().resolve()),
        project_root=str(Path(project_root).resolve()) if project_root else None,
        copy_figures=bool(copy_figures),
        figure_folders=[str(Path(p).resolve()) for p in figure_folders],
        crossref_companion_stems=list(companion_stems or []),
        crossref_embed_stems=list(embed_stems or []),
        crossref_own_stem=own_stem or Path(input_md).stem,
        figure_manifest_accumulate=bool(figure_manifest_accumulate),
        embed_depth=int(embed_depth),
        filters_module=filters_module or None,
    )
    metadata[CONTEXT_METADATA_KEY] = context.to_metadata()

    # includeonly: book-family templates emit ``{{ includeonly }}`` in the
    # preamble. Populated from the ``--only`` CLI flag (Item 13) with a full
    # ``\includeonly{stem1,stem2}`` string, or empty for a full build /
    # article-class templates. Template-facing (Jinja), hence top-level
    # rather than part of the filter context.
    metadata['includeonly'] = includeonly or ''
    metadata['user_preamble'] = _resolve_user_preamble(
        metadata, Path(input_md).resolve().parent)

    if not template:
        template = metadata.get('template')
        if not template:
            template = f'templates/{journal_template}/template.tex'
    template_name = Path(template).name
    resource_path = rootpath / Path(template).parent

    if not bib_file:
        bib_file = metadata.get('bibliography', None)
    bib_args = [arg for f in bib_files(bib_file) for arg in ('--bibliography', f)]
    user_pandoc_args = metadata.get('pandoc_args', [])
    division_args = []
    if (journal_template in BOOK_FAMILY_TEMPLATES
            and not any('--top-level-division' in a for a in user_pandoc_args)):
        # Book-family classes (report/book/memoir/classicthesis) support
        # \chapter, but pandoc can't detect that from a custom template, so
        # without this it treats markdown top-level headings as \section
        # (numbered under an implicit, unstarted chapter 0 -> "0.1", "0.1.1").
        division_args = ["--top-level-division=chapter"]
    pandoc_args = bib_args + user_pandoc_args + division_args + [
        "--natbib",
    ]

    filters = [
        "texmark-download-images",
        "texmark-journal",
        ] + (filters or metadata.get('filters', []))

    # 2. Parse the markdown (shared with the embed scan), set the values
    # resolved above in its metadata, and apply the filters.
    def load_doc(ast=None):
        # ``ast``: pandoc JSON (a dict) to load instead of the parsed text
        # (the block cache converts some of the blocks only).
        doc = pf.load(io.StringIO(parse_markdown(text) if ast is None else json.dumps(ast)))
        _set_yaml_metadata(doc, {key: metadata[key] for key in (
            'journal', 'longtable', 'packages', CONTEXT_METADATA_KEY,
            'includeonly', 'user_preamble')})
        # What --bibliography sets on the pandoc command line: a MetaString
        # per file (not markdown), overriding the YAML value.
        bibs = [pf.MetaString(f) for f in bib_files(bib_file)]
        if bibs:
            doc.metadata['bibliography'] = bibs[0] if len(bibs) == 1 else pf.MetaList(*bibs)
        return doc

    def render(ast_json_str):
        return _render_latex(ast_json_str, journal_template, metadata, pandoc_args)

    def plain(doc):
        ast_json_str, doc = _apply_filters_to_ast(doc, filters)
        return render(ast_json_str), doc

    raw_body = None
    if block_cache is not None:
        # Reuse the LaTeX of unchanged paragraphs (texmark/blockcache.py).
        if not body_only:
            block_cache.disable('the document is not body-only')
        elif not all(f in _INPROC_FILTERS for f in filters):
            block_cache.disable('of user filters')
        elif body_formats.get(journal_template, body_formats['default'])['format'] != 'latex':
            block_cache.disable('the output format is not latex')
        elif user_pandoc_args:
            block_cache.disable('of pandoc_args')
        else:
            def chain_for(doc):
                return [flt for name in filters for flt in _inproc_chain(name, doc)]
            raw_body, doc = _blockcache.convert(
                block_cache, text, json.loads(parse_markdown(text)), load_doc,
                chain_for, render, plain)
    if raw_body is None:
        raw_body, doc = plain(load_doc())
    metadata.update(meta_to_python(doc.metadata))

    # 3. Write the output: the bare body for body-only chunks, or the Jinja
    # master template (authors, abstract, preamble, ...) wrapped around it.
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    Path(output_tex).parent.mkdir(parents=True, exist_ok=True)

    body = _finish_body(raw_body)
    if extra_includes and not body_only:
        body = body + '\n' + _extra_include_directives(
            extra_includes, journal_template, metadata)

    if body_only:
        output_text = body
    else:
        # Resolve the template before opening output_tex: a TemplateNotFound
        # must not leave a truncated .tex behind (latexmk would then compile
        # an empty file on the next watch iteration).
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(resource_path))
        env.filters['join_if_list'] = join_if_list
        master_template = env.get_template(template_name)
        # A list of .bib files is passed to \bibliography{} comma-separated.
        template_vars = dict(metadata)
        if isinstance(template_vars.get('bibliography'), list):
            template_vars['bibliography'] = ','.join(bib_files(template_vars['bibliography']))
        output_text = master_template.render(body=body, **template_vars)

    with open(output_tex, "w") as f:
        f.write(output_text)

    # pdflatex's 8-bit font stack drops non-ASCII codepoints outside
    # inputenc's default table. Pandoc converts the common typography
    # chars (em-dash, smart quotes, ellipsis) but passes the rest
    # through raw — so a δ or ⁸ written directly in the body markdown
    # ends up in the .tex and triggers "Unicode character not set up"
    # at compile time. Run the same rewriter we use on the staged .bib
    # over the freshly written .tex so the body is covered too. Gated
    # by ``rewrite_unicode`` (auto/on/off, default auto = on under
    # pdflatex, off under lualatex/xelatex) so users on a UTF-8-native
    # engine can opt out and keep raw codepoints for OpenType shaping.
    effective_engine = engine or metadata.get('engine') or 'pdflatex'
    ru = rewrite_unicode if rewrite_unicode is not None else metadata.get('rewrite_unicode')
    if _resolve_rewrite_unicode(ru, effective_engine):
        from texmark.unicode_bib import rewrite_in_place
        rewrite_in_place(output_tex)

    metadata["resource_path"] = str(resource_path)
    return metadata


# ---------------------------------------------------------------------------
# compile_pdf: one .tex file -> one .pdf
# ---------------------------------------------------------------------------

def stage_bibliography(bib_file, build_dir, engine, rewrite_unicode=None):
    """Copy the .bib next to the generated .tex, rewriting non-ASCII
    codepoints and HTML tags for pdflatex (see compile_pdf). Called from
    compile_pdf and, for tex-only builds, from build_project, so that the
    staged bibliography never lags behind the source when the PDF is
    compiled by hand or by an external latexmk call. ``bib_file`` is a
    path or a list of paths."""
    build_dir = Path(build_dir)
    for f in bib_files(bib_file):
        src = Path(f)
        if src.exists() and src.parent.resolve() != build_dir.resolve():
            if _resolve_rewrite_unicode(rewrite_unicode, engine):
                from texmark.unicode_bib import stage_bib
                stage_bib(src, build_dir)
            else:
                shutil.copy2(src, build_dir / src.name)


# Draft job: figures replaced by boxes of the same size (graphicx's draft
# option), so the layout, and hence every page number and reference, is that
# of the full build. It runs under its own jobname, so the draft and full
# builds keep separate .aux/.log/.fdb_latexmk files and latexmk can skip
# either one when nothing changed since its last run.
DRAFT_PRETEX = r'\PassOptionsToPackage{draft}{graphicx}'


def draft_jobname(input_tex):
    return Path(input_tex).stem + '-draft'


def _draft_marker(build_dir, input_tex):
    """File recording that a draft PDF was published over the full job's own
    PDF (the default output path). latexmk only checks that its target
    exists, so the next full build must be forced (-g) to replace it."""
    return Path(build_dir) / f".{Path(input_tex).stem}.pdf-is-draft"


def prepare_build_dir(input_tex, build_dir, bib_file='', resource_path='',
                      engine='pdflatex', rewrite_unicode=None):
    """Put everything the engine reads into ``build_dir``: the template
    resources, the .tex (if written elsewhere) and the bibliography."""
    build_dir = Path(build_dir)
    if resource_path:
        logger.info(f"Resource path: {resource_path}")
        sync_tree(resource_path, build_dir)

    # Figure bundling (copy_figures mode) is handled inside the
    # resolve_image_paths filter during the pandoc pass, so we don't need
    # to stage anything here.
    if input_tex:
        src = Path(input_tex)
        if src.exists() and src.parent.resolve() != build_dir.resolve():
            shutil.copy2(src, build_dir)
    # Bibliography staging. By default (rewrite_unicode='auto') and when
    # the engine is pdflatex, non-ASCII codepoints in the .bib are replaced
    # with pylatexenc-supplied LaTeX equivalents and CrossRef-style HTML
    # tags are converted to LaTeX commands. Under lualatex/xelatex the
    # rewrite is skipped so the .bib stages as a plain copy; both engines
    # handle UTF-8 natively, and biber (used with biblatex) reads UTF-8
    # cleanly. The flag accepts on/off to override the auto behaviour.
    # See docs/encoding.md for the full strategy.
    stage_bibliography(bib_file, build_dir, engine, rewrite_unicode)


def _engine_cmd(engine, tex_name, jobname=None, pretex=''):
    cmd = [engine, '-interaction=nonstopmode']
    if jobname:
        cmd.append(f'-jobname={jobname}')
    cmd.append(pretex + '\\input{' + tex_name + '}' if pretex else tex_name)
    return cmd


def engine_pass(tex_name, build_dir, engine='pdflatex', jobname=None, pretex=''):
    """One engine pass. Returns True when the engine exited without error."""
    cmd = _engine_cmd(engine, tex_name, jobname, pretex)
    result = run(cmd, cwd=build_dir, check=False)
    return getattr(result, 'returncode', 0) == 0


def latex_errors(log_file, context=2):
    """The error lines (``! ...`` and the ``context`` lines after each) of an
    engine log, or an empty string."""
    try:
        lines = Path(log_file).read_text(errors='replace').splitlines()
    except FileNotFoundError:
        return ''
    out = []
    for i, line in enumerate(lines):
        if line.startswith('!'):
            out.extend(lines[i:i + 1 + context])
    return '\n'.join(out)


def run_latexmk(tex_name, build_dir, engine='pdflatex', jobname=None, pretex='',
                force=False):
    """latexmk to completion: bibtex/biber and as many engine passes as the
    .aux/.bbl need, none when nothing changed since its last run."""
    build_dir = Path(build_dir)
    # -f keeps latexmk going (matching the raw backend's check=False reruns)
    # even when an engine pass returns nonzero, so the .pdf still appears
    # for downstream inspection.
    engine_flag = {
        'pdflatex': '-pdf',
        'xelatex': '-pdfxe',
        'lualatex': '-pdflua',
    }.get(engine, '-pdf')
    # Stuck-state recovery: latexmk records its previous run's outcome in
    # <job>.fdb_latexmk. When that outcome was a pdflatex error AND the
    # input fingerprint hasn't changed since, latexmk says "Nothing to do"
    # and exits nonzero with "gave an error in previous invocation of
    # latexmk". The user then sees an error message with no obvious way
    # to act on it — the stale error masks whatever the current state is.
    #
    # Heuristic: if the previous engine pass left errors in <job>.log,
    # pass -g (force-make) so latexmk re-runs the engine and surfaces
    # the current errors (or, if the source has since been fixed, a
    # clean build). On a clean log we run incrementally as before.
    job = jobname or Path(tex_name).stem
    if latex_errors(build_dir / f'{job}.log'):
        force = True
    cmd = ['latexmk', engine_flag, '-interaction=nonstopmode', '-f']
    if force:
        cmd.append('-g')
    if jobname:
        cmd.append(f'-jobname={jobname}')
    if pretex:
        cmd.append(f'-usepretex={pretex}')
    cmd.append(tex_name)
    run(cmd, cwd=build_dir, check=False)


def run_raw(tex_name, build_dir, engine='pdflatex', biblatex=False,
            jobname=None, pretex=''):
    """engine → bibtex (or biber) → engine → engine, unconditionally."""
    job = jobname or Path(tex_name).stem
    engine_pass(tex_name, build_dir, engine, jobname, pretex)
    bibcmd = ['biber', job] if biblatex else ['bibtex', f'{job}.aux']
    run(bibcmd, cwd=build_dir, check=False)
    engine_pass(tex_name, build_dir, engine, jobname, pretex)
    engine_pass(tex_name, build_dir, engine, jobname, pretex)


def run_tectonic(tex_name, build_dir):
    run(['tectonic', '--keep-intermediates', '--keep-logs', tex_name],
        cwd=build_dir, check=False)


def run_driver(backend, tex_name, build_dir, engine='pdflatex', biblatex=False,
               jobname=None, pretex='', force=False):
    """Run the selected backend to completion on one job."""
    if backend == 'latexmk':
        run_latexmk(tex_name, build_dir, engine, jobname, pretex, force=force)
    elif backend == 'raw':
        run_raw(tex_name, build_dir, engine, biblatex, jobname, pretex)
    elif backend == 'tectonic':
        if jobname or pretex:
            raise ValueError("the tectonic backend does not support draft jobs")
        run_tectonic(tex_name, build_dir)
    else:
        raise ValueError(f"Unknown backend {backend!r}; use 'latexmk', 'raw', or 'tectonic'.")


def publish_pdf(src, dst):
    """Copy ``src`` to ``dst`` atomically: copy to a temporary file in the
    destination directory, then rename it over ``dst``.

    A viewer that reloads while the copy is in progress would otherwise read
    a half-written PDF. The rename gives ``dst`` a new inode; viewers that
    watch the file for changes reload it (checked with GNOME Papers).
    """
    dst = Path(dst)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp")
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def publish_job_pdf(input_tex, output_pdf, build_dir, draft=False):
    """Publish the PDF of the full job (or of the draft job) to ``output_pdf``.

    The job PDF stays in ``build_dir``: latexmk checks for it, and without
    it reruns the engine on every build even when nothing changed.
    """
    build_dir = Path(build_dir)
    full_pdf = build_dir / f'{Path(input_tex).stem}.pdf'
    job_pdf = build_dir / f'{draft_jobname(input_tex)}.pdf' if draft else full_pdf
    output_pdf = Path(output_pdf)
    if output_pdf.resolve() == job_pdf.resolve():
        return
    if draft and output_pdf.resolve() == full_pdf.resolve():
        _draft_marker(build_dir, input_tex).touch()
    publish_pdf(job_pdf, output_pdf)


def compile_pdf(input_tex, output_pdf, engine='pdflatex', build_dir='build',
                bib_file='references.bib', resource_path='', backend='latexmk',
                biblatex=False, rewrite_unicode=None, draft=False):
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

    biblatex (Item 18): when True the document uses biblatex, so its
    bibliography backend is biber rather than bibtex. The 'raw' backend runs
    `biber <stem>` instead of `bibtex <stem>.aux`. latexmk and tectonic both
    auto-detect biber from the emitted `.bcf` file, so they need no extra flag.

    draft: compile the draft job (``<stem>-draft``, figures as boxes, see
    DRAFT_PRETEX) and publish its PDF to ``output_pdf``. Not supported by
    the tectonic backend.
    """
    build_dir = Path(build_dir)
    prepare_build_dir(input_tex, build_dir, bib_file, resource_path,
                      engine, rewrite_unicode)
    tex_name = Path(input_tex).name
    if draft:
        run_driver(backend, tex_name, build_dir, engine, biblatex,
                   jobname=draft_jobname(input_tex), pretex=DRAFT_PRETEX)
    else:
        marker = _draft_marker(build_dir, input_tex)
        run_driver(backend, tex_name, build_dir, engine, biblatex,
                   force=marker.exists())
        marker.unlink(missing_ok=True)
    publish_job_pdf(input_tex, output_pdf, build_dir, draft=draft)


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
    paths = [Path(p) for p in paths if p]
    last = {}
    for p in paths:
        try:
            last[p] = p.stat().st_mtime
        except FileNotFoundError:
            pass
    logger.info(f"texmark: watching {len(paths)} path(s); Ctrl-C to stop.")
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
                    logger.info("texmark: build OK; watching for next change.")
                except Exception as e:
                    logger.error(f"texmark: build failed: {e}")
    except KeyboardInterrupt:
        logger.info("texmark: stopped watching.")


# ---------------------------------------------------------------------------
# Project-level orchestration (main)
# ---------------------------------------------------------------------------

@dataclass
class ProjectPlan:
    """Everything ``main`` resolves once per invocation.

    ``build_project`` takes a plan and performs one full build (embeds,
    master, companions, PDF compilation); watch mode calls it repeatedly
    with the same plan. Per-build values that may change while watching
    (engine/backend/rewrite_unicode from YAML) are re-read by
    ``_resolve_build_options`` on every build instead of living here.
    """
    args: argparse.Namespace
    project: Project
    primary_input: str
    build_dir: Path
    tex_file: object
    pdf_file: object
    want_pdf: bool
    companion_stems: list
    embed_stems: list
    root_stem: str
    # Single source for what leading-slash figure URLs resolve against:
    # CLI override, else the root resolved by resolve_project (yaml > git
    # toplevel > cwd). Threaded into every build_tex call — embeds, master
    # and companions — so all documents interpret ``/foo`` the same way.
    effective_project_root: str
    # In multi-file copy_figures mode each chunk runs the bundle filter
    # independently; the manifest must accumulate across chunks instead of
    # each finalize treating its own slice as authoritative.
    manifest_accumulate: bool
    includeonly: str
    extra_chapter_stems: list
    root_template: str


def _build_parser():
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
    parser.add_argument('--rewrite-unicode', choices=['auto', 'on', 'off'], default=None,
                        help='Rewrite non-ASCII Unicode and inline HTML tags in .bib and .tex '
                             'files to LaTeX equivalents (\\ensuremath{\\delta}, \\textsuperscript, '
                             'etc.) at stage time. auto (default): on for pdflatex, off for '
                             'lualatex/xelatex. See docs/encoding.md. YAML key: rewrite_unicode.')
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
    parser.add_argument('--only', default=None,
                        help='Comma-separated list of chapters to typeset this pass, e.g. '
                             '`--only ch1.md,ch2.md`. Injects \\includeonly{ch1,ch2} into the '
                             'master preamble so latexmk reuses the other chapters\' cached .aux '
                             'instead of recompiling them. Meaningful only for book-family '
                             'templates (article-class lacks \\include); ignored with a warning '
                             'otherwise.')
    parser.add_argument('--draft', action='store_true', default=None,
                        help='Compile with figures replaced by boxes of the same size (graphicx '
                             'draft option), so the layout is that of the full build but faster. '
                             'Runs as the LaTeX job <stem>-draft, which keeps its own .aux files; '
                             'the PDF is still written to the --output path. Not supported with '
                             'the tectonic backend or with companion documents. YAML key: draft.')
    parser.add_argument('--progressive', action='store_true', default=None,
                        help='With --pdf, publish the PDF in stages: (1) one LaTeX pass of the '
                             'draft job (see --draft), reusing the previous references; (2) the '
                             'draft job with references and bibliography resolved; (3) unless '
                             '--draft is given, the full build with figures. Companion documents '
                             'are compiled in stage 3 only. YAML key: progressive.')
    parser.add_argument('--packages', nargs='*', help='custom latex packages to include')
    parser.add_argument('--no-cache', action='store_true',
                        help='Convert every embedded document (chapter) again, instead of '
                             'reusing the .tex of those unchanged since the last run '
                             '(cached in <build>/.texmark-cache/).')
    # Deprecated: figures are now discovered from the markdown URLs, and
    # (with --copy-figures) always bundled into <build>/figures/. The flag
    # is accepted-and-ignored so existing invocations keep working.
    parser.add_argument('--images', help=argparse.SUPPRESS)
    return parser


def plan_project(args) -> ProjectPlan:
    """Resolve the input files and CLI flags into a ProjectPlan."""
    # Derive filenames (from the root / first input)
    build_dir = Path(args.build)
    primary_input = args.inputs[0]
    tex_file = args.tex or build_dir / Path(primary_input).with_suffix(".tex").name
    pdf_file = args.output or build_dir / Path(primary_input).with_suffix(".pdf").name

    # Resolve the project once up-front: discovers embedded files (via
    # ![](file.md) body syntax) and companions (via `companions:` yaml).
    # When the resolved project has no embeds, no companions, and a
    # single input, downstream behaviour is identical to the historical
    # single-file pipeline.
    project = resolve_project(
        [Path(p) for p in args.inputs],
        scan=None if getattr(args, 'no_cache', False) else _texcache.cached_embed_scan(build_dir))

    # Pre-compute the stem lists used by the crossref filter so they don't
    # need to be re-derived on every body-only/master build call.
    companion_stems = [p.stem for p in project.companion_files]
    embed_stems = [p.stem for p in project.embedded_files]

    # --only / chapters: wiring (Item 13). The `chapters:` YAML key unions
    # extra chapter files into project.embedded_files; those not also present
    # as body `![](file.md)` nodes have no embed node, so the master build
    # must emit their \include directives explicitly (extra_chapter_stems).
    body_stems = set()
    for inp in args.inputs:
        for p in _scan_ast_for_embeds(Path(inp)):
            body_stems.add(p.stem)
    extra_chapter_stems = [p.stem for p in project.embedded_files
                           if p.stem not in body_stems]

    # The root's effective journal template decides whether --only applies:
    # \includeonly requires \include, which only book-family templates emit.
    root_yaml_meta = load_markdown(open(primary_input).read()).metadata
    root_template = (args.journal_template
                     or root_yaml_meta['journal'].get('template')
                     or 'default')

    includeonly = ''
    if args.only:
        only_stems = [Path(item.strip()).stem for item in args.only.split(',') if item.strip()]
        if only_stems:
            if root_template in BOOK_FAMILY_TEMPLATES:
                includeonly = '\\includeonly{' + ','.join(only_stems) + '}'
            else:
                logger.warning(
                    "texmark: --only is meaningful only for book-family templates; ignoring."
                )

    return ProjectPlan(
        args=args,
        project=project,
        primary_input=primary_input,
        build_dir=build_dir,
        tex_file=tex_file,
        pdf_file=pdf_file,
        want_pdf=args.pdf or args.watch,
        companion_stems=companion_stems,
        embed_stems=embed_stems,
        root_stem=Path(primary_input).stem,
        effective_project_root=args.project_root or str(project.project_root),
        manifest_accumulate=bool(project.embedded_files),
        includeonly=includeonly,
        extra_chapter_stems=extra_chapter_stems,
        root_template=root_template,
    )


def _resolve_build_options(plan):
    """Per-build option resolution (CLI > YAML > built-in default).

    Re-read on every build so editing YAML in --watch mode takes effect.
    rewrite_unicode stays the raw auto/on/off value: build_tex (body .tex)
    and compile_pdf (staged .bib) resolve it against their own effective
    engine, so companions — which use the engine from their own YAML —
    get the right auto behaviour without the root's engine leaking in.
    """
    yaml_meta = load_markdown(open(plan.primary_input).read()).metadata
    engine = str(plan.args.engine or yaml_meta.get('engine') or 'pdflatex')
    backend = str(plan.args.backend or yaml_meta.get('backend') or 'latexmk')
    rewrite_unicode = plan.args.rewrite_unicode or yaml_meta.get('rewrite_unicode')
    draft = bool(plan.args.draft or yaml_meta.get('build_draft'))
    progressive = bool(plan.args.progressive or yaml_meta.get('build_progressive'))
    return engine, backend, rewrite_unicode, draft, progressive


def _check_draft_options(plan, backend, draft, progressive):
    """Drop the draft and progressive options where they are not supported,
    with a warning. Returns the (draft, progressive) to apply."""
    if backend == 'tectonic' and (draft or progressive):
        logger.warning("texmark: the tectonic backend has no draft mode; "
                       "ignoring --draft/--progressive and building with figures.")
        return False, False
    if draft and plan.project.companion_files:
        # xr-hyper reads each peer's <stem>.aux, i.e. the full job's: a
        # draft job would leave the cross-document references stale.
        logger.warning("texmark: draft builds are not supported with companion "
                       "documents; building with figures.")
        draft = False
    return draft, progressive


def _compile_documents(plan, targets, engine, backend, rewrite_unicode, draft=False):
    """Compile every (tex, pdf, bib, resource_path, biblatex) target.

    Companions need multi-pass coordination: xr-hyper resolves cross-doc
    refs by reading peer .aux files, so each pass may change another doc's
    aux until they all stabilise. With no companions there is nothing to
    coordinate — single pass.
    """
    if plan.project.companion_files:
        prev_snapshot = None
        for _pass_idx in range(1, MAX_PASSES + 1):
            for in_tex, out_pdf, bib, rp, bl in targets:
                compile_pdf(in_tex, out_pdf, engine=engine, build_dir=plan.args.build,
                            bib_file=bib, resource_path=rp, backend=backend,
                            biblatex=bl, rewrite_unicode=rewrite_unicode)
            cur_snapshot = _aux_files_snapshot(plan.project, plan.build_dir)
            if prev_snapshot is not None and cur_snapshot == prev_snapshot:
                break
            prev_snapshot = cur_snapshot
        else:
            logger.warning(
                "texmark: companion build did not converge after "
                f"{MAX_PASSES} passes; cross-refs may be stale"
            )
    else:
        in_tex, out_pdf, bib, rp, bl = targets[0]
        compile_pdf(in_tex, out_pdf, engine=engine, build_dir=plan.args.build,
                    bib_file=bib, resource_path=rp, backend=backend,
                    biblatex=bl, rewrite_unicode=rewrite_unicode, draft=draft)


def _mtime(path):
    try:
        return Path(path).stat().st_mtime_ns
    except FileNotFoundError:
        return None


# Files of the full job that the draft job can start from: the layout is
# the same, so their labels, citations and contents lines are valid for it.
_SEED_SUFFIXES = ('.aux', '.bbl', '.toc', '.lof', '.lot', '.out')


def _seed_draft_job(build_dir, input_tex):
    """When the draft job has never run but the full job has, start the
    draft job from the full job's .aux/.bbl/..., so that its first single
    pass already shows the existing references."""
    build_dir = Path(build_dir)
    stem, job = Path(input_tex).stem, draft_jobname(input_tex)
    if (build_dir / f'{job}.aux').exists():
        return
    for suffix in _SEED_SUFFIXES:
        src = build_dir / f'{stem}{suffix}'
        if src.exists():
            shutil.copy2(src, build_dir / f'{job}{suffix}')


def _compile_progressive(plan, targets, engine, backend, rewrite_unicode,
                         draft=False, t0=None):
    """Compile the root document in stages, publishing the PDF after each:

    1. one engine pass on the draft job: the .aux/.bbl of its previous run
       are reused, so only labels and citations added since show as ??;
    2. the backend to completion on the draft job (bibtex and further
       passes where needed), published only if the PDF changed;
    3. unless ``draft``, the full build with figures (with companions, the
       usual multi-pass loop over all documents).

    Companion documents are compiled in stage 3 only.
    """
    t0 = time.monotonic() if t0 is None else t0
    in_tex, out_pdf, bib, rp, bl = targets[0]
    build_dir = plan.build_dir
    tex_name = Path(in_tex).name
    job = draft_jobname(in_tex)
    job_pdf = build_dir / f'{job}.pdf'

    def written(what):
        logger.info(f"texmark: {what} written: {out_pdf} "
                    f"({time.monotonic() - t0:.1f} s)")

    prepare_build_dir(in_tex, build_dir, bib, rp, engine, rewrite_unicode)
    _seed_draft_job(build_dir, in_tex)

    # Stage 1. On a LaTeX error, report it and go on, as the full build
    # does (latexmk -f, raw backend reruns): stage 2 shows the current state.
    before = _mtime(job_pdf)
    if not engine_pass(tex_name, build_dir, engine, jobname=job, pretex=DRAFT_PRETEX):
        errors = latex_errors(build_dir / f'{job}.log')
        if errors:
            logger.warning(f"texmark: LaTeX errors in the draft pass:\n{errors}")
    if _mtime(job_pdf) not in (None, before):
        publish_job_pdf(in_tex, out_pdf, build_dir, draft=True)
        written("draft PDF (1 pass)")
    else:
        logger.warning("texmark: the draft pass wrote no PDF")

    # Stage 2.
    before = _mtime(job_pdf)
    run_driver(backend, tex_name, build_dir, engine, bl,
               jobname=job, pretex=DRAFT_PRETEX)
    if _mtime(job_pdf) not in (None, before):
        publish_job_pdf(in_tex, out_pdf, build_dir, draft=True)
        written("draft PDF (references resolved)")
    else:
        logger.info("texmark: draft PDF unchanged after the reference passes")

    # Stage 3.
    if draft:
        return
    _compile_documents(plan, targets, engine, backend, rewrite_unicode)
    written("PDF with figures")


def build_project(plan):
    """One full build of the plan: embeds, master, companions, PDFs."""
    t0 = time.monotonic()
    args = plan.args
    engine, backend, rewrite_unicode, draft, progressive = _resolve_build_options(plan)

    # Body-only builds for each embedded chapter, written as
    # `<build>/<stem>.tex` so the master's `\input{<stem>}` resolves at
    # LaTeX time. Embeds are not separately compiled. An embed whose inputs
    # are unchanged since the last run keeps its .tex (texmark/texcache.py).
    for embed_path in plan.project.embedded_files:
        embed_tex = plan.build_dir / f"{embed_path.stem}.tex"
        _texcache.cached_build_tex(
                  build_tex, str(embed_path), str(embed_tex),
                  enabled=not getattr(args, 'no_cache', False),
                  template=args.template, bib_file=args.bib,
                  build_dir=args.build,
                  filters=args.filters, journal_template=plan.root_template,
                  filters_module=args.filters_module, packages=args.packages,
                  copy_figures=args.copy_figures,
                  figure_folders=args.figure_folders,
                  project_root=plan.effective_project_root,
                  body_only=True,
                  companion_stems=plan.companion_stems,
                  embed_stems=plan.embed_stems,
                  own_stem=embed_path.stem,
                  figure_manifest_accumulate=plan.manifest_accumulate,
                  embed_depth=1,
                  engine=engine, rewrite_unicode=rewrite_unicode)

    # Build the master .tex for the root.
    root_metadata = build_tex(
        plan.primary_input, plan.tex_file, template=args.template, bib_file=args.bib,
        build_dir=args.build,
        filters=args.filters, journal_template=args.journal_template,
        filters_module=args.filters_module, packages=args.packages,
        copy_figures=args.copy_figures,
        figure_folders=args.figure_folders,
        project_root=plan.effective_project_root,
        companion_stems=plan.companion_stems,
        embed_stems=plan.embed_stems,
        own_stem=plan.root_stem,
        figure_manifest_accumulate=plan.manifest_accumulate,
        includeonly=plan.includeonly,
        extra_includes=plan.extra_chapter_stems,
        engine=engine, rewrite_unicode=rewrite_unicode,
    )

    # Build each companion's standalone .tex. Each companion gets the
    # universe of peers (root + sibling companions) minus itself so its
    # crossref filter can wire xr-hyper in both directions. Companions
    # are first-class documents: bibliography, template, and engine come
    # from the companion's own YAML, not the root's CLI overrides.
    companion_builds = []  # (companion_path, tex_path, pdf_path, metadata)
    for comp_path in plan.project.companion_files:
        peers = [plan.root_stem] + [s for s in plan.companion_stems if s != comp_path.stem]
        comp_tex = plan.build_dir / f"{comp_path.stem}.tex"
        comp_pdf = plan.build_dir / f"{comp_path.stem}.pdf"
        comp_meta = build_tex(
            str(comp_path), str(comp_tex),
            build_dir=args.build,
            filters=args.filters,
            filters_module=args.filters_module, packages=args.packages,
            copy_figures=args.copy_figures,
            figure_folders=args.figure_folders,
            project_root=plan.effective_project_root,
            companion_stems=peers,
            own_stem=comp_path.stem,
        )
        companion_builds.append((comp_path, comp_tex, comp_pdf, comp_meta))

    if plan.want_pdf:
        # bibliography_per_chapter (Item 18) swaps the root to a biblatex+biber
        # pipeline. Only the root honours this flag, and only for book-family
        # templates; companions are decoupled and always use their own (bibtex)
        # pipeline regardless of the root's flag.
        root_biblatex = (bool(root_metadata.get('bibliography_per_chapter'))
                         and plan.root_template in BOOK_FAMILY_TEMPLATES)

        # Compile target list: (input_tex, output_pdf, bib_file,
        # resource_path, biblatex). Body-only embeds are inputs to the
        # master, never compile targets.
        targets = [(
            plan.tex_file, plan.pdf_file,
            bib_files(root_metadata.get('bibliography')),
            str(root_metadata.get('resource_path') or ''),
            root_biblatex,
        )]
        for _cp, c_tex, c_pdf, c_meta in companion_builds:
            targets.append((
                c_tex, c_pdf,
                bib_files(c_meta.get('bibliography')),
                str(c_meta.get('resource_path') or ''),
                False,
            ))
        draft, progressive = _check_draft_options(plan, backend, draft, progressive)
        if progressive:
            _compile_progressive(plan, targets, engine, backend, rewrite_unicode,
                                 draft=draft, t0=t0)
        else:
            _compile_documents(plan, targets, engine, backend, rewrite_unicode,
                               draft=draft)
    else:
        # tex-only build: stage the template resources (.cls, .sty, .bst)
        # and the bibliographies anyway, so that the generated .tex can be
        # compiled by other means in the build directory (compile_pdf does
        # this itself on the --pdf path).
        for meta in [root_metadata] + [m for _cp, _t, _p, m in companion_builds]:
            if meta.get('resource_path'):
                sync_tree(meta['resource_path'], plan.build_dir)
            stage_bibliography(meta.get('bibliography'), plan.build_dir,
                               engine, rewrite_unicode)

    return root_metadata


def _collect_watch_paths(plan, metadata):
    """Paths whose mtime change triggers a rebuild in --watch mode."""
    # The journal template lives under texmark's install dir; watching it
    # is convenient when iterating on a new template.
    rp = metadata.get('resource_path')
    tmpl_path = Path(str(rp)) / 'template.tex' if rp else None

    watch_paths: list = [plan.primary_input, *bib_files(metadata.get('bibliography')), tmpl_path]
    watch_paths.extend(plan.project.embedded_files)
    watch_paths.extend(plan.project.companion_files)

    for comp_path in plan.project.companion_files:
        comp_meta = load_markdown(comp_path.read_text()).metadata
        for comp_bib in bib_files(comp_meta.get('bibliography')):
            watch_paths.append(Path(comp_path).parent / comp_bib)
        comp_jt = comp_meta.get('journal', {}).get('template') or 'default'
        watch_paths.append(rootpath / f'templates/{comp_jt}/template.tex')

    # Deduplicate preserving first-occurrence order, dropping None/empty.
    seen_resolved: set = set()
    deduped: list = []
    for p in watch_paths:
        if not p:
            continue
        key = str(Path(p).resolve())
        if key not in seen_resolved:
            seen_resolved.add(key)
            deduped.append(p)
    return deduped


def main():
    from texmark.logs import setup_console_logging
    setup_console_logging()
    args = _build_parser().parse_args()

    if args.images is not None:
        logger.warning(
            "warning: --images is deprecated and ignored; figures are now "
            "auto-detected from the markdown and (with --copy-figures) bundled "
            "into <build>/figures/.")

    plan = plan_project(args)

    if args.watch:
        metadata = build_project(plan)
        watch_loop(lambda: build_project(plan), _collect_watch_paths(plan, metadata))
    else:
        build_project(plan)


if __name__ == '__main__':
    main()
