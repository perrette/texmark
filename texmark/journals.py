"""Journal filter registry: which filter chain runs for which template.

The per-journal differences are data: which sections are extracted into
template variables, how they are renamed, which citation command the
document class wants. The ``JOURNALS`` table below holds that data; the
``journal_chain`` factory turns one entry into a working filter chain.

``texmark.shared.filters`` maps template name -> chain. Built-ins are
registered as zero-argument factories so every build gets fresh filter
instances (no state shared between builds); plain lists are also accepted
for user registrations via ``--filters-module``. ``run_filters`` is the
entry used both in-process by build.py and by the ``texmark-journal``
pandoc subprocess filter.

To add a journal: add a ``JOURNALS`` entry (and a matching template under
``templates/<name>/``). Keys:

  aliases                 alternative template names for the same chain
  cite                    optional citation rewriter hook, inserted after the
                          basic filters (e.g. ``force_cite``, ``apacite_cite``)
  extract_sections        section identifiers lifted out of the body into
                          template variables (SI/appendix sections are always
                          extracted and mapped to ``appendix``; don't list them)
  sections_map            section identifier -> template variable rename
  remap_command_sections  section header -> raw LaTeX command replacement
  drop_sections           sections removed with a warning (template can't
                          place them)
  post                    hooks appended after the SectionFilter
"""

import importlib

import panflute as pf

from texmark.context import BuildContext
from texmark.logs import logger
from texmark.shared import filters, Filter, BOOK_FAMILY_TEMPLATES
from texmark.sectiontracker import SectionFilter, panflute2latex
from texmark.filters.tabular import table_to_latex
from texmark.filters.embed import embed_filter
from texmark.filters.crossref import crossref_filter
from texmark.filters.equations import equations_filter
from texmark.filters.images import strip_leading_slash, resolve_image_paths
from texmark.filters.figures import (
    tag_figures,
    extract_table_identifier,
    stringify_captions,
    apply_figure_defaults,
)


basic_filters = [
    embed_filter,
    crossref_filter,
    equations_filter,
    strip_leading_slash,
    resolve_image_paths,
    extract_table_identifier,
    stringify_captions,
    tag_figures,
    apply_figure_defaults,
    table_to_latex,
]

default_filters = basic_filters

si_sections = ["appendix", "supplementary-material", "supplementary-information"]
method_sections = ["methods", "materials-and-methods", "methodology"]


# ---------------------------------------------------------------------------
# Citation-command rewriters (referenced from JOURNALS entries)
# ---------------------------------------------------------------------------

def force_cite(elem, doc):
    if isinstance(elem, pf.Cite):
        keys = [c.id for c in elem.citations]
        key_str = ",".join(keys)
        # Build as raw LaTeX \cite{}
        return pf.RawInline(f'\\cite{{{key_str}}}', format='latex')


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


def header_to_unnumbered(elem, doc):
    if isinstance(elem, pf.Header):
        # Convert header to raw LaTeX \section*{...}
        level = elem.level
        content = pf.stringify(elem)
        latex_cmd = f'\\{"sub" * (level - 1)}section*{{{content}}}'
        return pf.RawBlock(latex_cmd, format='latex')


def header_to_paragraph(elem, doc):
    if isinstance(elem, pf.Header):
        # Convert header to raw LaTeX \paragraph*{...}
        content = pf.stringify(elem)
        latex_cmd = f'\\paragraph*{{{content+"."}}}'
        return pf.RawBlock(latex_cmd, format='latex')


# ---------------------------------------------------------------------------
# Per-journal configuration (data only — see module docstring for the keys)
# ---------------------------------------------------------------------------

JOURNALS = {
    'copernicus': {
        'aliases': ['cp', 'esd'],
        'extract_sections': [
            'abstract', 'acknowledgements',
            'author-contributions', 'competing-interests',
        ],
        'remap_command_sections': {
            'introduction': r'\introduction',
            'conclusions': r'\conclusions',
        },
        'sections_map': {
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
        },
    },
    'science': {
        'cite': force_cite,
        'extract_sections': [
            'abstract', 'acknowledgements',
            'author-contributions', 'competing-interests',
            'methods', 'materials-and-methods',
        ],
        'sections_map': {
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'materialandmethods' for section in method_sections},
        },
        'post': [header_to_paragraph],
    },
    'ametsoc': {
        'aliases': ['amsoc', 'jclim', 'jas', 'mwr', 'jamc', 'jhm', 'jpo',
                    'jtech', 'waf', 'bams'],
        'extract_sections': [
            'abstract', 'acknowledgements', 'acknowledgments',
            'significance', 'significance-statement', 'capsule',
            'data-availability', 'data-availability-statement',
        ],
        'sections_map': {
            'acknowledgments': 'acknowledgements',
            'significance-statement': 'significance',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
        },
        'drop_sections': ['author-contributions'],
    },
    'arxiv': {
        'aliases': ['preprint'],
        'extract_sections': [
            'abstract', 'keywords',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions', 'competing-interests',
        ],
        'sections_map': {
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
        },
    },
    'elsarticle': {
        'aliases': ['elsevier'],
        'extract_sections': [
            'abstract', 'keywords', 'highlights',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions', 'credit', 'competing-interests',
        ],
        'sections_map': {
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'credit': 'authorcontribution',
            'competing-interests': 'competinginterests',
        },
    },
    'agujournal': {
        'aliases': ['agu', 'jgr', 'grl', 'james', 'earthsfuture', 'wrr', 'rog'],
        'cite': apacite_cite,
        'extract_sections': [
            'abstract', 'plain-language-summary', 'keypoints', 'key-points',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
        ],
        'sections_map': {
            'acknowledgments': 'acknowledgements',
            'plain-language-summary': 'plainlanguagesummary',
            'key-points': 'keypoints',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
        },
        'drop_sections': ['author-contributions'],
    },
    'springernature': {
        'aliases': ['springer', 'nature', 'naturecomms', 'natclimchange',
                    'natgeoscience', 'scirep'],
        'cite': force_cite,
        'extract_sections': [
            'abstract', 'keywords',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'funding', 'ethics', 'ethics-approval',
            'author-contributions', 'competing-interests',
        ],
        'sections_map': {
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            'ethics-approval': 'ethics',
        },
    },
    'pnas': {
        'cite': force_cite,
        'extract_sections': [
            'abstract', 'keywords',
            'significance', 'significance-statement',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions',
            'competing-interests', 'declaration', 'author-declaration',
            'equal-authors',
        ],
        'sections_map': {
            'acknowledgments': 'acknowledgements',
            'significance-statement': 'significance',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            'declaration': 'competinginterests',
            'author-declaration': 'competinginterests',
            'equal-authors': 'equalauthors',
        },
    },
}


def journal_chain(config):
    """Build a fresh filter chain from a ``JOURNALS`` config entry."""
    chain = list(basic_filters)
    if config.get('cite'):
        chain.append(config['cite'])
    chain.append(SectionFilter(
        # SI/appendix sections are extracted (and mapped to 'appendix') for
        # every journal, so configs don't have to repeat them.
        extract_sections=list(config.get('extract_sections', [])) + si_sections,
        sections_map={
            **{section: 'appendix' for section in si_sections},
            **config.get('sections_map', {}),
        },
        remap_command_sections=config.get('remap_command_sections', {}),
        drop_sections=config.get('drop_sections', ()),
    ))
    chain.extend(config.get('post', ()))
    return chain


# ---------------------------------------------------------------------------
# Book-family and beamer chains
# ---------------------------------------------------------------------------

class FrontmatterFilter:
    """Lift # Dedication / # Preface / # Foreword sections into metadata.

    Only active for book-family templates. YAML wins: when a front-matter key
    is declared in YAML *and* a matching ``# Section`` header also appears in
    the body, the YAML value is kept and the body section is discarded (with a
    warning log).  ``list_of_figures`` and ``list_of_tables`` are pure YAML
    flags — the filter does not need to lift them; the templates read them
    directly.
    """

    FRONT_SECTIONS = ['dedication', 'preface', 'foreword']

    def __init__(self):
        self._skip = False
        self._yaml_has = {}

    def prepare(self, doc):
        template = doc.get_metadata('journal', {}).get('template', '')
        self._skip = template not in BOOK_FAMILY_TEMPLATES
        self._yaml_has = {}
        if self._skip:
            return
        for key in self.FRONT_SECTIONS:
            self._yaml_has[key] = doc.get_metadata(key, None) is not None

    def action(self, elem, doc):
        return None

    def finalize(self, doc):
        if self._skip:
            return

        new_blocks = []
        current_key = None
        current_content = []

        for blk in doc.content:
            if isinstance(blk, pf.Header):
                if current_key is not None:
                    self._flush(current_key, current_content, doc)
                    current_key = None
                    current_content = []
                sid = blk.identifier.lower()
                if sid in self.FRONT_SECTIONS:
                    current_key = sid
                    continue
                new_blocks.append(blk)
                continue
            if current_key is not None:
                current_content.append(blk)
            else:
                new_blocks.append(blk)

        if current_key is not None:
            self._flush(current_key, current_content, doc)

        doc.content = new_blocks

    def _flush(self, key, content, doc):
        if self._yaml_has.get(key):
            logger.warning(
                f"texmark: '{key}' declared in both YAML and as a "
                f"'# {key.capitalize()}' markdown section; "
                f"YAML value takes precedence."
            )
            return
        if content:
            latex_str = panflute2latex(content)
            doc.metadata[key] = pf.MetaString(latex_str)


def _surface_chapter_style(doc):
    """Copy the hyphenated ``chapter-style`` YAML key to ``chapter_style``.

    The memoir template emits ``\\chapterstyle{ {{ chapter_style }} }``, but
    Jinja cannot reference a context key containing a hyphen (it parses as a
    subtraction). We surface the value under a Jinja-safe name so the template
    can read it; when the key is absent the template falls back to its default.
    """
    cs = doc.get_metadata('chapter-style', None)
    if cs:
        doc.metadata['chapter_style'] = pf.MetaString(str(cs))


def _surface_classicthesis_options(doc):
    """Copy the hyphenated ``classicthesis-options`` YAML key to
    ``classicthesis_options``.

    The classicthesis template emits
    ``\\usepackage[ {{ classicthesis_options }} ]{classicthesis}``, but Jinja
    cannot reference a context key containing a hyphen (it parses as a
    subtraction). We surface the value under a Jinja-safe name; when the key
    is absent the template loads the package with its own defaults.
    """
    opts = doc.get_metadata('classicthesis-options', None)
    if opts:
        doc.metadata['classicthesis_options'] = pf.MetaString(str(opts))


def book_chain(extra_hooks=()):
    """Book-family chain: basic filters + template hooks + front matter."""
    return list(basic_filters) + list(extra_hooks) + [FrontmatterFilter()]


def beamer_chain():
    # Beamer presentations: a slim chain. apply_figure_defaults is dropped
    # because its figure*/`figure-span: full` behaviour is article-class-
    # specific (beamer frames have no two-column figure* environment), and no
    # SectionFilter is registered because slide decks have no abstract /
    # data-availability / appendix sections to extract into the preamble.
    return [f for f in basic_filters if f is not apply_figure_defaults]


# ---------------------------------------------------------------------------
# Registry population
# ---------------------------------------------------------------------------
# Values in ``shared.filters`` are either a zero-argument factory returning a
# filter chain (all built-ins, so each build gets fresh filter instances) or a
# plain chain list (accepted for user registrations via --filters-module).

for _name, _config in JOURNALS.items():
    _factory = (lambda config: lambda: journal_chain(config))(_config)
    for _alias in [_name, *_config.get('aliases', [])]:
        filters[_alias] = _factory

filters['default'] = lambda: list(default_filters)

for _beamer_name in ["beamer", "slides", "presentation"]:
    filters[_beamer_name] = beamer_chain

filters['book'] = book_chain
filters['report'] = book_chain
filters['memoir'] = lambda: book_chain([Filter(prepare=_surface_chapter_style)])
filters['classicthesis'] = lambda: book_chain([Filter(prepare=_surface_classicthesis_options)])


def get_filter_chain(template):
    """Resolve a template name to a fresh filter chain.

    ``shared.filters`` entries may be factories (built-ins) or plain lists
    (user registrations); unknown templates fall back to the default chain
    with a warning.
    """
    entry = filters.get(template)
    if entry is None:
        logger.warning(
            f'No filters found for journal template: {template}. Using default filter.')
        return list(default_filters)
    return entry() if callable(entry) else list(entry)


def run_filters(doc):
    if doc is not None:
        journal = doc.get_metadata('journal') or {}
    else:
        logger.warning('doc is None')
        journal = {'template': 'default'}

    filters_module = BuildContext.from_doc(doc).filters_module if doc is not None else None
    if filters_module:
        logger.info(f"Loading filters module: {filters_module}")
        importlib.import_module(filters_module)

    for filter in get_filter_chain(journal.get("template")):
        logger.info(f'Running filter: {filter} on {doc}')
        doc = pf.run_filter(action=filter.action if hasattr(filter, 'action') else filter,
                   prepare=filter.prepare if hasattr(filter, 'prepare') else None,
                   finalize=filter.finalize if hasattr(filter, 'finalize') else None,
                   doc=doc)
        assert isinstance(doc, pf.Doc), f"Filter {filter} did not return a valid doc object"

    return doc
