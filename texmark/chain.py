"""Run a filter chain, sharing document walks between element-local filters.

A filter chain is a list of filters, run in order. Each filter is either a
plain action function ``action(elem, doc)`` or an object with ``action`` and
optionally ``prepare(doc)`` / ``finalize(doc)`` methods (the panflute
convention). Run one at a time, every filter walks the whole document.

Most built-in filters are *element-local*: their action only looks at the
element it is given and that element's own subtree, and acts on one or two
element types. ``WALK_GROUPS`` below lists all of them, in chain order, split
into groups. Consecutive filters of the chain that belong to the same group,
in the group's order, run in a single walk: for each element (children first,
as in a normal walk), the group's actions for that element's type are applied
one after the other, each to the result of the previous one. The prepare
methods of the group run before that walk and the finalize methods after it,
in chain order.

Every other filter runs in its own walk, at its place in the chain. That
includes filters this module does not know (user filters registered with
``--filters-module``) and the whole-document filters: those with a prepare or
finalize that reads or rewrites the document content, or with an action that
looks at siblings or ancestors. A filter that sets ``needs_walk = False``
(its action does nothing) only has its prepare and finalize called.

What sharing a walk changes
---------------------------
Run separately, filter B sees the document after filter A has processed all
of it. In a shared walk, B processes element X right after A did, when A (and
B) have processed X's subtree but not yet X's later siblings or ancestors.
The output is the same when, for every pair A before B in a group:

* A's action does not read anything in X's subtree that B changes (B has
  already processed that subtree when A gets to X);
* B's prepare (run before A's actions) does not depend on A's changes, and
  does not change what A's actions see; likewise A's finalize (run after B's
  actions);
* when A returns a new element, it has no children B would act on (B is
  applied to the new element itself, not to its children);
* when A returns a list (elements to splice in, or ``[]`` to delete), B has
  nothing to do on the list items: processing of that element stops there.
  The items taken from the element's own subtree (e.g. a citation's prefix)
  were already seen by B during the walk; new items must be ones B ignores.

These conditions hold for each group below in the order given (and so for
any ordered subset of it, e.g. the beamer chain without
``apply_figure_defaults``). When adding a filter, check them against the
other members of the group it would join; when unsure, start a new group or
leave the filter out, which keeps it in its own walk.
"""
from __future__ import annotations

import panflute as pf

from texmark import walk as _walk
from texmark.logs import logger
from texmark.filters import download_images
from texmark.filters.crossref import crossref_filter
from texmark.filters.embed import embed_filter
from texmark.filters.equations import equations_filter
from texmark.filters.figures import (
    apply_figure_defaults,
    extract_table_identifier,
    stringify_captions,
    tag_figures,
)
from texmark.filters.images import resolve_image_paths, strip_leading_slash
from texmark.filters.changes import track_changes
from texmark.filters.tabular import table_to_latex


# Element-local filters, as (filter, element types its action handles).
# Groups and the order within a group follow the default chain
# (``journals.basic_filters``, preceded by ``texmark-download-images`` in a
# build). Why the groups are split where they are:
#
# * ``equations_filter``'s prepare merges paragraphs around display math and
#   must see the document after ``embed_filter`` replaced its paragraphs (a
#   paragraph starting with an equation is otherwise merged into a preceding
#   ``![](chapter.md)`` paragraph). ``crossref_filter`` (prepare and finalize
#   read only build context and metadata; Links it replaces don't change the
#   merge) goes with it rather than with ``embed_filter``, whose check of a
#   ``[](x.md){.include}`` link would otherwise see links crossref already
#   replaced.
# * ``resolve_image_paths``'s prepare collects every image of the document
#   (copy mode); images inside a same-document reference link that
#   ``equations_filter`` replaces must already be gone.
# * ``table_to_latex`` renders the table cells: the citation rewriters
#   (``force_cite`` ...) that come after it in journal chains must not reach
#   the cells first, so they keep their own walk.
WALK_GROUPS = (
    (
        (download_images.action, (pf.Image,)),
        (embed_filter, (pf.Para, pf.Figure)),
    ),
    (
        (crossref_filter, (pf.Link,)),
        (equations_filter, (pf.Para, pf.Plain, pf.Cite, pf.Link)),
        (strip_leading_slash, (pf.Link,)),
        (track_changes, (pf.Span, pf.Strikeout, pf.RawInline, pf.Para, pf.Plain,
                          pf.Header, pf.ListItem, pf.BulletList, pf.OrderedList,
                          pf.BlockQuote)),
    ),
    (
        (resolve_image_paths, (pf.Image,)),
        (extract_table_identifier, (pf.Table,)),
        (stringify_captions, (pf.Figure, pf.Table)),
        (tag_figures, (pf.Figure,)),
        (apply_figure_defaults, (pf.Figure,)),
        (table_to_latex, (pf.Table,)),
    ),
)

# id(filter) -> (group index, position in group, element types)
_LOCAL = {
    id(f): (g, pos, types)
    for g, group in enumerate(WALK_GROUPS)
    for pos, (f, types) in enumerate(group)
}


def _action(f):
    return f.action if hasattr(f, 'action') else f


def _needs_walk(f):
    return getattr(f, 'needs_walk', True)


def plan(chain):
    """Split ``chain`` into steps: lists of filters that share one walk.

    Consecutive filters join the current step when they belong to the same
    ``WALK_GROUPS`` group, in increasing group position. Any other filter is a
    step of its own.
    """
    steps = []
    last = None  # (group, position) of the last filter of the current step
    for f in chain:
        local = _LOCAL.get(id(f))
        if (local is not None and last is not None
                and local[0] == last[0] and local[1] > last[1]):
            steps[-1].append(f)
        else:
            steps.append([f])
        last = local[:2] if local is not None else None
    return steps


class _GroupAction:
    """One walk action applying several element-local filters in order.

    The actions for an element are those whose declared types match it; after
    an action returns a replacement element, the remaining actions are those
    for the replacement's type. Returning a list ends the element's
    processing (see the module docstring).
    """

    def __init__(self, filters):
        self._members = [(i, _action(f), _LOCAL[id(f)][2])
                         for i, f in enumerate(filters)]
        self._by_type = {}

    def _actions_for(self, cls):
        acts = self._by_type.get(cls)
        if acts is None:
            acts = [(i, act) for i, act, types in self._members
                    if issubclass(cls, types)]
            self._by_type[cls] = acts
        return acts

    def __call__(self, elem, doc):
        acts = self._actions_for(type(elem))
        done = -1  # position of the action that produced ``elem``
        k = 0
        while k < len(acts):
            i, act = acts[k]
            k += 1
            if i <= done:
                continue
            out = act(elem, doc)
            if out is None or out is elem:
                continue
            if isinstance(out, list):
                return out
            elem, done = out, i
            acts, k = self._actions_for(type(elem)), 0
        return elem


def _run_step(filters, doc):
    for f in filters:
        if hasattr(f, 'prepare'):
            f.prepare(doc)
    walking = [f for f in filters if _needs_walk(f)]
    if len(walking) == 1:
        doc = _walk.walk(doc, _action(walking[0]), doc)
    elif walking:
        doc = _walk.walk(doc, _GroupAction(walking), doc)
    for f in filters:
        if hasattr(f, 'finalize'):
            f.finalize(doc)
    return doc


def run_chain(chain, doc, fuse=True):
    """Run the filters of ``chain`` on ``doc``, in order; return the doc.

    With ``fuse=False`` every filter walks the document on its own, as
    ``panflute.run_filter`` would (used to check that sharing walks gives the
    same result).
    """
    steps = plan(chain) if fuse else [[f] for f in chain]
    for step in steps:
        logger.debug(f'Running filters: {step}')
        if fuse:
            doc = _run_step(step, doc)
        else:
            f, = step
            doc = _walk.run_filter(_action(f),
                                   prepare=getattr(f, 'prepare', None),
                                   finalize=getattr(f, 'finalize', None),
                                   doc=doc)
        assert isinstance(doc, pf.Doc), f"Filters {step} did not return a valid doc object"
    return doc
