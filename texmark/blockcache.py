"""Reuse the LaTeX of a document's unchanged paragraphs across runs.

When an embedded document (chapter) was edited, its texcache entry no longer
matches and ``build_tex`` runs again. Most edits change one or two
paragraphs; this module lets that run filter and render only the top-level
blocks that changed, and take the LaTeX of the others from the previous run.
The output is the same as a full conversion, byte for byte; whenever that is
not certain, the run does a full conversion.

The markdown is still parsed whole (pandoc's reader resolves references,
footnote definitions, example-list numbers and header identifiers across the
whole file), so each block is compared as pandoc parsed it: by the sha256 of
its JSON, citation numbers left out (``_NOTE_NUM``).

Self-contained blocks
---------------------
A top-level block is *self-contained* (S) when it is a Para, Plain, list,
BlockQuote, LineBlock, CodeBlock, RawBlock, HorizontalRule or Div, and

* contains no Header, Image, Figure, Table, display math, nor a Link with the
  ``include`` class, and
* is not next to a top-level block that contains display math.

Every other block is *non-self-contained* (N). Consecutive N blocks form an
N run. A document is a sequence of *units*: S blocks and N runs.

Why S blocks can be converted on their own, given the default filter chains
(``journals``, checked by ``_supported``):

* the element-local filters (``texmark.chain.WALK_GROUPS``, the citation
  rewriters, ``header_to_*``) act on one element and its subtree, using only
  the document metadata and build context; on an S block, only the
  equations (Cite, Link, Para), crossref and leading-slash (Link) and embed
  (Para) actions can do anything;
* ``equations_filter.prepare`` merges a paragraph with its neighbour only
  when one of them contains display math: never an S block (no display
  math, no neighbour with display math);
* the image filters collect and rewrite Images only (none in S blocks);
* ``SectionFilter`` and ``FrontmatterFilter`` move whole sections (from a
  Header to the next one) into metadata, and ``collect_figures_and_tables``
  moves Figures and Tables; which blocks move depends on the Headers, the
  metadata and the position of the blocks between the Headers (see below).

And for pandoc's LaTeX writer: the body of a block list is the outputs of
its blocks, each rendered on its own, the non-empty ones joined by a blank
line. The one exception (with ``--natbib``) is a level-1 Header that is the
last block of the document, which is dropped (pandoc takes it as the
bibliography title): only N runs contain Headers, and they are never
rendered apart from their position in the document.

How a run converts
------------------
Each S block is surrounded by separators: paragraphs holding one unique word
(``TEXMARKBLOCK<nonce><k>``, rendered as that word on its own paragraph).
Separators are S blocks themselves, so the filters leave them alone; S
blocks are therefore always converted between separators, whether within
the whole document or not.

*Full conversion*: separators are inserted into the whole document, which
then goes through the filters and the writer as usual. If any separator
is missing from the filtered document (a filter moved it, e.g. into an
extracted section) or from the LaTeX, the document is converted again
without separators and nothing is recorded. Otherwise the LaTeX between the
separators is that of each unit (and of what a filter inserted at the start
or end, e.g. ``\\graphicspath``); the body is these pieces joined as the
writer joins blocks, which is the writer output of the document without
separators.

*Incremental conversion*: possible when the previous run recorded its
pieces and

* everything except the text is unchanged (texcache's ``ctx`` key: build
  arguments, YAML front matter, environment, figure files),
* pandoc's metadata is unchanged, and
* the *skeleton* is unchanged: the sequence of units with each N run given
  by the hashes of its blocks and consecutive S blocks collapsed into one
  marker. N blocks and their positions relative to S blocks are thus the
  same, so the filters do the same with them (including which sections are
  moved), and give the same N pieces; and since the previous run kept every
  separator, no S block is moved either.

The S blocks not seen in the previous run (by hash) are then put, between
separators, in a document of their own with the same metadata, filtered
(without the image filters, which have side effects: copying figures,
writing the figure manifest) and rendered in one writer call. The filtered
metadata of that document must equal the one recorded by the full
conversion (otherwise a filter took something from the document into the
metadata). The body is assembled from the recorded and new pieces.

Disabled (a full conversion without separators) for non-body-only
documents, beamer, pandoc_args, user filters, or a filter chain with
filters not listed in ``_supported``; ``build_tex`` checks the first four.
Each decision is logged at debug level ("block cache: ...").
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import secrets

import panflute as pf

from texmark import journals as _journals
from texmark.filters import download_images as _download_images
from texmark.filters.images import resolve_image_paths
from texmark.logs import logger
from texmark.sectiontracker import SectionFilter
from texmark.shared import Filter

_S_TYPES = {'Para', 'Plain', 'BulletList', 'OrderedList', 'DefinitionList',
            'BlockQuote', 'LineBlock', 'CodeBlock', 'RawBlock',
            'HorizontalRule', 'Div'}
# Element types that make a block N, as they appear in compact pandoc JSON.
_N_MARKERS = tuple(f'"t":"{t}"' for t in ('Header', 'Image', 'Figure', 'Table'))
_DISPLAY_MATH = '"t":"DisplayMath"'
_LINK = '"t":"Link"'
_TOKEN = 'TEXMARKBLOCK'
# The reader numbers citations through the document (``citationNoteNum``),
# so a citation or footnote added in one paragraph changes the JSON of every
# later citation. The number is only used by citeproc (pandoc's own citation
# processing, for note styles), not by the LaTeX writer with --natbib nor by
# the filters, so it is left out of the block hashes.
_NOTE_NUM = re.compile(r'"citationNoteNum":-?\d+')

# Filters whose behaviour on S blocks is analysed in the module docstring.
_LOCAL_FILTERS = set(map(id, _journals.basic_filters + [
    _download_images.action, _journals.force_cite, _journals.apacite_cite,
    _journals.header_to_unnumbered, _journals.header_to_paragraph]))
_PREPARE_HOOKS = {_journals._surface_chapter_style,
                  _journals._surface_classicthesis_options}
# Filters left out of the chain for a document of S blocks only.
_IMAGE_FILTERS = {id(resolve_image_paths), id(_download_images.action)}


def _supported(f):
    if id(f) in _LOCAL_FILTERS or isinstance(f, (SectionFilter, _journals.FrontmatterFilter)):
        return True
    return (type(f) is Filter and f._action is None and f._finalize is None
            and f._prepare in _PREPARE_HOOKS)


class BlockCache:
    """Block-cache state for one ``build_tex`` call.

    ``previous`` is what the last run recorded (or None), ``reason`` why
    it is None; after the call, ``entry`` is what to record for the next
    run (None: nothing).
    """

    def __init__(self, previous=None, reason=None):
        self.previous = previous
        self.reason = reason or 'there is no previous run to reuse'
        self.entry = None

    def disable(self, reason):
        self.previous = None
        logger.debug(f'block cache: not used because {reason}')


def _dumps(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _has_include_link(node):
    if isinstance(node, dict):
        if node.get('t') == 'Link' and 'include' in node['c'][0][1]:
            return True
        return any(_has_include_link(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_include_link(v) for v in node)
    return False


def classify(blocks):
    """``(hashes, self_contained)`` for a list of top-level blocks (pandoc JSON)."""
    dumped = [_dumps(b) for b in blocks]
    math = [_DISPLAY_MATH in s for s in dumped]
    sc = []
    for i, (b, s) in enumerate(zip(blocks, dumped)):
        ok = (b['t'] in _S_TYPES and not math[i]
              and not (i > 0 and math[i - 1])
              and not (i + 1 < len(blocks) and math[i + 1])
              and not any(m in s for m in _N_MARKERS)
              and not (_LINK in s and _has_include_link(b)))
        sc.append(ok)
    return [_sha(_NOTE_NUM.sub('', s)) for s in dumped], sc


def units(hashes, sc):
    """Units of the document: ``('S', index)`` or ``('N', [indices])``."""
    out = []
    for i, s in enumerate(sc):
        if s:
            out.append(('S', i))
        elif out and out[-1][0] == 'N':
            out[-1][1].append(i)
        else:
            out.append(('N', [i]))
    return out


def skeleton(hashes, us):
    sk = []
    for kind, val in us:
        if kind == 'N':
            sk.append([hashes[i] for i in val])
        elif not sk or sk[-1] != 'S':
            sk.append('S')
    return sk


def _first_change(old, new, us, blocks):
    """Where skeleton ``new`` first differs from ``old``, for the log."""
    nruns = [val for kind, val in us if kind == 'N']
    r = 0
    for a, b in zip(old, new):
        if a != b:
            break
        r += b != 'S'
    else:
        return 'blocks added or removed at the end'
    if r < len(nruns):
        i = nruns[r][0]
        return f'in the run of blocks starting at block {i + 1}, a {blocks[i]["t"]}'
    return 'a block was removed'


def _sep(token, k):
    return pf.Para(pf.Str(f'{token}{k}'))


def _layout(us, blocks, token):
    """Document content with separators around each S block, and the number
    of separators. Slots (the text between separators) are: a lead slot if
    the first unit is S, one slot per unit, a tail slot if the last is S."""
    content = []
    k = 0
    for j, (kind, val) in enumerate(us):
        if kind == 'S' or (j > 0 and us[j - 1][0] == 'S'):
            content.append(_sep(token, k))
            k += 1
        content.extend([blocks[val]] if kind == 'S' else [blocks[i] for i in val])
    if us and us[-1][0] == 'S':
        content.append(_sep(token, k))
        k += 1
    return content, k


def _separators_kept(doc, token, n):
    seen = [b.content[0].text for b in doc.content
            if isinstance(b, pf.Para) and len(b.content) == 1
            and isinstance(b.content[0], pf.Str) and b.content[0].text.startswith(token)]
    return seen == [f'{token}{k}' for k in range(n)]


def split(body, token, n):
    """The ``n + 1`` pieces of LaTeX between the ``n`` separators of
    ``body``, or None if the separators are not where expected."""
    pieces = []
    pos = 0
    for k in range(n):
        mark = f'{token}{k}'
        i = body.find(mark, pos)
        if i < 0:
            return None
        piece = body[pos:i]
        if piece:
            if not piece.endswith('\n\n'):
                return None
            piece = piece[:-2]
        j = i + len(mark)
        if body.startswith('\n\n', j):
            pos = j + 2
        elif j == len(body):
            pos = j
        else:
            return None
        pieces.append(piece)
    pieces.append(body[pos:])
    if any(token in p for p in pieces):
        return None
    return pieces


def join(pieces):
    """Join LaTeX pieces as pandoc's writer joins blocks."""
    return '\n\n'.join(p for p in pieces if p)


def _meta_json(doc):
    return _dumps(doc.metadata.to_json())


def _new_token(text):
    while True:
        token = f'{_TOKEN}{secrets.token_hex(6)}x'
        if token not in text:
            return token


def convert(state, text, ast, load_doc, chain_for, render, plain):
    """Filter and render the document; return ``(latex body, filtered doc)``.

    ``ast``: pandoc JSON (parsed) of ``text``. ``load_doc(ast=None)``: a
    panflute doc of ``ast`` (default: the whole document), with the build's
    metadata set. ``chain_for(doc)``: its filter chain. ``render(json_str)``:
    the writer. ``plain(doc)``: a conversion without the block cache,
    returning ``(latex body, doc)``.
    """
    hashes, sc = classify(ast['blocks'])
    us = units(hashes, sc)
    sk = skeleton(hashes, us)
    meta_in = _sha(_dumps(ast['meta']))

    prev = state.previous
    reason = state.reason
    if prev is not None:
        try:
            if prev['meta_in'] != meta_in:
                reason = 'the document metadata changed'
            elif prev['skeleton'] != sk:
                reason = ('blocks other than self-contained paragraphs changed '
                          f'({_first_change(prev["skeleton"], sk, us, ast["blocks"])})')
            else:
                out = _incremental(state, prev, ast, hashes, us, load_doc, chain_for,
                                   render, plain, text)
                if out is not None:
                    return out
                reason = state.reason
        except (KeyError, TypeError, ValueError, IndexError, AttributeError, StopIteration):
            reason = 'the previous entry is unreadable'
    doc = load_doc()
    chain = chain_for(doc)
    if not _check_chain(state, chain):
        return plain(doc)
    logger.debug(f'block cache: full conversion because {reason}')
    return _full(state, doc, hashes, us, sk, meta_in, chain, render, plain, load_doc, text)


def _check_chain(state, chain):
    unsupported = [f for f in chain if not _supported(f)]
    if unsupported:
        state.disable(f'of the filter {unsupported[0]!r}')
    return not unsupported


def _run_chain(chain, doc):
    from texmark import chain as _chain
    return _chain.run_chain(chain, doc)


def _dump(doc):
    sink = io.StringIO()
    pf.dump(doc, sink)
    return sink.getvalue()


def _full(state, doc, hashes, us, sk, meta_in, chain, render, plain, load_doc, text):
    token = _new_token(text)
    doc.content, n = _layout(us, list(doc.content), token)
    doc = _run_chain(chain, doc)
    pieces = None
    if _separators_kept(doc, token, n):
        pieces = split(render(_dump(doc)), token, n)
    if pieces is None:
        logger.debug('block cache: separators not kept by the conversion; '
                     'converting again without them')
        return plain(load_doc())
    lead = pieces.pop(0) if us and us[0][0] == 'S' else None
    tail = pieces.pop() if us and us[-1][0] == 'S' else None
    sblocks, nruns = {}, []
    for (kind, val), piece in zip(us, pieces):
        if kind == 'S':
            sblocks[hashes[val]] = piece
        else:
            nruns.append(piece)
    state.entry = {
        'meta_in': meta_in, 'skeleton': sk, 'meta': _meta_json(doc),
        'lead': lead, 'tail': tail, 'nruns': nruns, 'sblocks': sblocks,
        'url_map': dict(resolve_image_paths.url_map),
    }
    return join(([lead] if lead is not None else []) + pieces
                + ([tail] if tail is not None else [])), doc


def _incremental(state, prev, ast, hashes, us, load_doc, chain_for, render, plain, text):
    known = prev['sblocks']
    new = []  # indices of S blocks to convert, one per distinct hash
    seen = set()
    for kind, val in us:
        if kind == 'S' and hashes[val] not in known and hashes[val] not in seen:
            seen.add(hashes[val])
            new.append(val)
    token = _new_token(text)
    blocks = ast['blocks']
    sep = lambda k: {'t': 'Para', 'c': [{'t': 'Str', 'c': f'{token}{k}'}]}
    doc = load_doc(dict(ast, blocks=[b for k, i in enumerate(new) for b in (sep(k), blocks[i])]
                        + [sep(len(new))]))
    chain = chain_for(doc)
    if not _check_chain(state, chain):
        return plain(load_doc())
    n = len(new) + 1
    doc = _run_chain([f for f in chain if id(f) not in _IMAGE_FILTERS], doc)
    if not _separators_kept(doc, token, n):
        state.reason = 'separators were not kept by the conversion'
        return None
    if _meta_json(doc) != prev['meta']:
        state.reason = 'the filters changed the metadata differently'
        return None
    pieces = split(render(_dump(doc)), token, n) if new else ['', '']
    if pieces is None or pieces[0] or pieces[-1]:
        state.reason = 'separators were not kept by the writer'
        return None
    fresh = {hashes[i]: p for i, p in zip(new, pieces[1:-1])}
    sblocks = {}
    out = [prev['lead']] if prev['lead'] is not None else []
    nruns = iter(prev['nruns'])
    for kind, val in us:
        if kind == 'S':
            h = hashes[val]
            sblocks[h] = fresh[h] if h in fresh else known[h]
            out.append(sblocks[h])
        else:
            out.append(next(nruns))
    if prev['tail'] is not None:
        out.append(prev['tail'])
    state.entry = dict(prev, sblocks=sblocks)
    resolve_image_paths._reset()
    resolve_image_paths.url_map.update(prev['url_map'])
    logger.debug(f'block cache: converted {len(new)} of {len(sblocks)} '
                 'self-contained blocks, reused the rest')
    return join(out), doc
