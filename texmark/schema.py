"""JSON Schema of the YAML front matter that texmark reads.

``texmark schema`` prints it (draft 2020-12), for editors that complete the
keys and values of the front matter and show their descriptions.

``FRONTMATTER`` below lists every key read by the Python code (``metadata``,
``doc.get_metadata``) or by the built-in templates (Jinja variables);
tests/test_schema.py checks that no key read there is missing. Keys that
texmark sets itself for the templates (``body``, ``user_preamble``, ...) are
in ``INTERNAL_KEYS``. The template names are read at run time from the
template folders (``texmark/templates/<name>/template.tex``), with the
aliases of ``texmark.journals.JOURNALS``; the description of each comes
from the first line of its template.tex, a Jinja comment
``{# texmark-template: <description> -#}``. In the schema, the template
names are a ``oneOf`` of ``{"const": <name>, "description": ...}``
(``$defs/template``).

The other fields texmark writes in front of a key: ``type``, a one-line
``description``, ``default`` where texmark has one, ``properties`` for a
mapping and ``items`` for a list. Pandoc keys texmark does not read pass
through: ``additionalProperties`` is true at the top level.
"""
import json
import re
import sys
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / 'templates'
_DESCRIPTION = re.compile(r'\{#-?\s*texmark-template:\s*(.*?)\s*-?#\}')

_STR = {'type': 'string'}
_STRS = {'type': 'array', 'items': _STR}
_STR_OR_STRS = {'type': ['string', 'array'], 'items': _STR}


def _key(description, schema=None, **extra):
    return {**(schema or _STR), 'description': description, **extra}


def _section(name, heading=None):
    """A key that can also be given as a ``# Heading`` section."""
    heading = heading or name.capitalize()
    return _key(f"{heading}; also as a `# {heading}` section of the body.", _STR_OR_STRS)


AUTHOR = {
    'type': 'object',
    'description': "An author.",
    'properties': {
        'firstname': _key("First name."),
        'lastname': _key("Last name."),
        'affiliation': _key(
            "Affiliation: index into `affiliations` (from 1), or several as \"1,2\".",
            {'type': ['integer', 'string']}),
        'email': _key("Email address."),
        'corresponding': _key(
            "Corresponding author. Without any, the first author is.",
            {'type': 'boolean'}, default=False),
        'equalcontrib': _key(
            "Contributed equally (templates whose class has a command for it).",
            {'type': 'boolean'}, default=False),
        'thanks': _key("Footnote to the author's name."),
    },
    'additionalProperties': True,
}

JOURNAL = {
    'type': 'object',
    'description': "Journal template and class options.",
    'properties': {
        'template': {'$ref': '#/$defs/template',
                     'description': "Journal template: the LaTeX template and filters.",
                     'default': 'default'},
        'draft': _key(
            "Submission layout (true) or publication-ready layout (false).",
            {'type': 'boolean'}, default=True),
        'options': _key(
            "Raw document class options; override `draft`.", _STR_OR_STRS),
        'short': _key("Journal abbreviation passed to the class (copernicus: cp, esd, ...)."),
        'name': _key("Journal name (agujournal, elsarticle)."),
        'doi': _key("DOI (pnas)."),
        'classification': _key("Article type (pnas).", default="Research Article"),
        'templatetype': _key("Template type (pnas).", default="pnasresearcharticle"),
        'displaywatermark': _key("Watermark (pnas); defaults to `draft`.",
                                 {'type': 'boolean'}),
    },
    'additionalProperties': True,
}

BEAMER = {
    'type': 'object',
    'description': "Beamer options (beamer template).",
    'properties': {
        'theme': _key("Beamer theme.", default='default'),
        'colortheme': _key("Beamer color theme."),
        'fonttheme': _key("Beamer font theme."),
        'aspectratio': _key("Aspect ratio, e.g. 169.", {'type': ['integer', 'string']}),
        'slide_level': _key("Heading level that starts a slide.",
                            {'type': 'integer'}, default=2),
    },
    'additionalProperties': True,
}

FRONTMATTER = {
    # Title page
    'title': _key("Title of the document."),
    'authors': _key("Authors.", {'type': 'array', 'items': AUTHOR}),
    'author': _key("Author line when there is no `authors` list (book-family templates)."),
    'affiliations': _key("Affiliations, referred to by `authors[].affiliation`.", _STRS),
    'running': {
        'type': 'object',
        'description': "Running head (copernicus).",
        'properties': {
            'title': _key("Short title for the running head."),
            'author': _key("Short author list for the running head."),
        },
        'additionalProperties': True,
    },
    'date': _key("Date of the document."),
    'journal': {
        'description': "Journal template (a name) or the template with options (a mapping).",
        'anyOf': [{'$ref': '#/$defs/template'}, JOURNAL],
    },
    'template': _key("Path of a custom Jinja LaTeX template instead of the journal's."),
    'documentclassoptions': _key(
        "Document class options (default, book, report, memoir, classicthesis).",
        _STR_OR_STRS),
    'beamer': BEAMER,
    # Bibliography
    'bibliography': _key("BibTeX file(s), relative to the markdown file.", _STR_OR_STRS),
    'biblio_style': _key("BibTeX style (default, arxiv, beamer, elsarticle, book family).",
                         default='plainnat'),
    'bibliography_per_chapter': _key(
        "A reference list per chapter with biblatex (book-family templates).",
        {'type': 'boolean'}, default=False),
    # Sections that can also be given in the front matter
    'abstract': _section('abstract'),
    'keywords': _section('keywords'),
    'acknowledgements': _section('acknowledgements', 'Acknowledgements'),
    'dataavailability': _section('dataavailability', 'Data Availability'),
    'codeavailability': _section('codeavailability', 'Code Availability'),
    'codedataavailability': _section('codedataavailability', 'Code and Data Availability'),
    'sampleavailability': _section('sampleavailability', 'Sample Availability'),
    'videoavailability': _section('videoavailability', 'Video Supplement'),
    'authorcontribution': _section('authorcontribution', 'Author Contributions'),
    'competinginterests': _section('competinginterests', 'Competing Interests'),
    'appendix': _section('appendix'),
    'significance': _section('significance'),
    'capsule': _section('capsule'),
    'keypoints': _section('keypoints', 'Key Points'),
    'plainlanguagesummary': _section('plainlanguagesummary', 'Plain Language Summary'),
    'highlights': _section('highlights'),
    'funding': _section('funding'),
    'ethics': _section('ethics'),
    'materialsandmethods': _section('materialsandmethods', 'Materials and Methods'),
    'supplementarytext': _section('supplementarytext', 'Supplementary Text'),
    'disclaimer': _section('disclaimer'),
    'copyright': _section('copyright'),
    'equalauthors': _key("Equal-contribution statement (pnas); overrides "
                         "`authors[].equalcontrib`."),
    'preface': _section('preface'),
    'foreword': _section('foreword'),
    'dedication': _key("Dedication (book-family templates)."),
    'list_of_figures': _key("List of figures (book-family templates).",
                            {'type': 'boolean'}, default=False),
    'list_of_tables': _key("List of tables (book-family templates).",
                           {'type': 'boolean'}, default=False),
    'chapter-style': _key("memoir chapter style, e.g. veelo (memoir)."),
    'classicthesis-options': _key("classicthesis package options (classicthesis)."),
    # Preamble
    'packages': _key("LaTeX packages to load.", _STRS),
    'preamble': _key("LaTeX before \\begin{document}: inline, or file path(s) "
                     "relative to the markdown file.", _STR_OR_STRS),
    # Figures and tables
    'figure-width': _key("Default figure width.", default='100%'),
    'figure-span': _key("Default figure span: column, or full text width (figure*).",
                        {'type': 'string', 'enum': ['column', 'full']}, default='column'),
    'collect_figures_and_tables': _key(
        "Move figures and tables to the end of the document.",
        {'type': 'boolean'}, default=False),
    'copy_figures': _key("Copy the figures into <build>/figures.",
                         {'type': 'boolean'}, default=False),
    'figure_folders': _key("Folders searched for figures.", _STRS),
    'project_root': _key("Folder that leading-slash paths resolve against "
                         "(default: git top level, else the current directory)."),
    'table_type': _key("Table style; defaults to the journal template."),
    # Multi-file projects
    'chapters': _key("Chapter files, \\include'd in this order.", _STRS),
    'companions': _key("Companion documents (separate PDFs with cross-references).", _STRS),
    'prefix': _key("Prefix of the figure, table, equation and section numbers (S for S1)."),
    'figure-prefix': _key("Prefix of the figure numbers; overrides `prefix`."),
    'table-prefix': _key("Prefix of the table numbers; overrides `prefix`."),
    'equation-prefix': _key("Prefix of the equation numbers; overrides `prefix`."),
    'section-prefix': _key("Prefix of the section numbers; overrides `prefix`."),
    # Track changes
    'changes': _key("Track changes (CriticMarkup): auto (when the text has marks), "
                    "true or false.",
                    {'type': ['string', 'boolean'], 'enum': ['auto', True, False]},
                    default='auto'),
    # Build options
    'engine': _key("LaTeX engine (--engine).",
                   {'type': 'string', 'enum': ['pdflatex', 'xelatex', 'lualatex']},
                   default='pdflatex'),
    'backend': _key("Build backend (--backend).",
                    {'type': 'string', 'enum': ['latexmk', 'raw', 'tectonic']},
                    default='latexmk'),
    'rewrite_unicode': _key(
        "Rewrite non-ASCII characters as LaTeX commands; auto: under pdflatex.",
        {'type': ['string', 'boolean'], 'enum': ['auto', 'on', 'off', True, False]},
        default='auto'),
    'build_draft': _key("Figures as boxes (--draft).", {'type': 'boolean'}, default=False),
    'build_progressive': _key("Staged PDF builds (--progressive).",
                              {'type': 'boolean'}, default=False),
    'build_preamble_format': _key("Precompiled preamble (false: --no-preamble-format).",
                                  {'type': 'boolean'}, default=True),
    'build_synctex': _key("SyncTeX file (false: --no-synctex).",
                          {'type': 'boolean'}, default=True),
    # Pandoc and filters
    'pandoc_args': _key("Extra pandoc arguments.", _STRS),
    'filters': _key("Extra pandoc filters.", _STRS),
    'filters_module': _key("Python module that registers filters (--filters-module)."),
    'extract_sections': _key("Section identifiers lifted into template variables "
                             "(added to the journal's).", _STRS),
    'sections_map': _key("Section identifier -> template variable (added to the journal's).",
                         {'type': 'object', 'additionalProperties': _STR}),
    'remap_command_sections': _key(
        "Section heading -> LaTeX command (added to the journal's).",
        {'type': 'object', 'additionalProperties': _STR}),
}

# Template variables and metadata keys that texmark sets itself.
INTERNAL_KEYS = {
    'body', 'user_preamble', 'endofdump', 'includeonly', 'xr_setup', 'xr_externals',
    'xr_preamble', 'texmark', 'resource_path', '_body_lines', 'longtable',
    'chapter_style', 'classicthesis_options',
    # filled by the section filter (collect_figures_and_tables, appendices)
    'figures', 'tables', 'appendixfigures', 'appendixtables', 'appendix_letters',
    'appendixtitles',
}


def _template_description(folder):
    try:
        with open(folder / 'template.tex', encoding='utf-8') as f:
            first = f.readline()
    except OSError:
        return None
    m = _DESCRIPTION.match(first)
    return m.group(1) if m else None


def templates():
    """The built-in templates: ``{name: description or None}``."""
    return {d.name: _template_description(d) for d in sorted(TEMPLATES_DIR.iterdir())
            if (d / 'template.tex').is_file()}


def aliases():
    """``{alias: template}`` for the journal aliases (``nature`` ->
    ``springernature``)."""
    from texmark import journals
    out = {}
    for name, config in journals.JOURNALS.items():
        for alias in config.get('aliases', []):
            out[alias] = name
    for alias in ('slides', 'presentation'):
        out[alias] = journals.canonical_template(alias)
    return out


def template_schema():
    """``oneOf`` of the template names and aliases, each with its
    description."""
    names = templates()
    choices = [{'const': n, **({'description': d} if d else {})} for n, d in names.items()]
    for alias, target in sorted(aliases().items()):
        if alias in names or target not in names:
            continue
        d = names[target]
        choices.append({'const': alias,
                        'description': f"Alias of {target}" + (f": {d}" if d else "")})
    return {'type': 'string', 'oneOf': choices}


def schema():
    """The JSON Schema of the front matter, as a dict."""
    from texmark import __version__
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        'title': 'texmark front matter',
        'description': f'YAML front matter keys read by texmark {__version__}.',
        'type': 'object',
        'properties': FRONTMATTER,
        'additionalProperties': True,
        '$defs': {'template': template_schema()},
    }


def main(argv=None):
    """``texmark schema``: print the schema as JSON."""
    import argparse
    parser = argparse.ArgumentParser(
        prog='texmark schema',
        description='Print the JSON Schema (draft 2020-12) of the YAML front matter.')
    parser.add_argument('--indent', type=int, default=2,
                        help='JSON indentation (default: 2; 0: one line)')
    args = parser.parse_args(argv)
    json.dump(schema(), sys.stdout, indent=args.indent or None, ensure_ascii=False)
    sys.stdout.write('\n')
    return 0
