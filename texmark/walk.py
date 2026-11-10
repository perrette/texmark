"""A faster equivalent of panflute's tree walk, for the in-process filters.

``panflute.Element.walk`` reassigns every child container it visits
(``setattr(elem, name, walked)``), which rebuilds and type-checks every
``ListContainer`` in the document on every walk, even when no action changed
anything. Each filter in a chain walks the whole document, so on a large
document most of the filter time goes into those rebuilds.

``walk`` here visits the same elements in the same order (children first, then
the element itself), attaches ``parent``/``location``/``index`` to each element
before visiting it as panflute's iteration does, and calls the action with the
same arguments. The difference: a child container is reassigned only when its
contents changed, i.e. when an action returned a replacement (an element, or a
list to splice in, ``[]`` to delete) or modified the container during the walk.
The resulting document is the same.

``run_filter`` / ``run_filters`` mirror the panflute functions of the same
name for an in-memory ``doc``.
"""
from __future__ import annotations

import panflute as pf
from panflute.base import Element
from panflute.containers import DictContainer, ListContainer


def _walk_list(container, action, doc, stop_if):
    """Walk the items of ``container``; return the new item list if anything
    changed, else ``None``."""
    items = container.list
    parent = container.parent
    location = container.location
    out = []
    changed = False
    i = 0
    # Live iteration, like MutableSequence.__iter__: items an action appends
    # to this container during the walk are visited too.
    while i < len(items):
        item = items[i]
        if not isinstance(item, (int, str, bool)):
            item.parent = parent
            item.location = location
            item.index = i
        new = walk(item, action, doc, stop_if)
        if new is item:
            out.append(item)
        elif type(new) is list:
            out.extend(new)
            changed = True
        else:
            out.append(new)
            changed = True
        i += 1
    if not changed:
        # An action may have modified the container itself (insert, delete,
        # item assignment) without returning anything; panflute would then
        # overwrite it with the walked items, so do the same.
        if len(items) != len(out) or any(a is not b for a, b in zip(items, out)):
            changed = True
    return out if changed else None


def walk(elem, action, doc=None, stop_if=None):
    """Walk ``elem`` and its children, applying ``action``; same result as
    ``elem.walk(action, doc, stop_if)``."""
    if doc is None:
        doc = elem.doc
    if stop_if is None or not stop_if(elem):
        for name in elem._children:
            child = getattr(elem, name)
            if isinstance(child, ListContainer):
                new = _walk_list(child, action, doc, stop_if)
                if new is not None or getattr(elem, name) is not child:
                    setattr(elem, name, child.list if new is None else new)
            elif isinstance(child, Element):
                new = walk(child, action, doc, stop_if)
                if new is not child or getattr(elem, name) is not child:
                    setattr(elem, name, new)
            elif isinstance(child, DictContainer):
                # Metadata maps: small, so keep panflute's own walk.
                setattr(elem, name, child.walk(action, doc, stop_if))
            elif child is None:
                pass  # empty table headers or captions
            else:
                raise TypeError(type(child))
    altered = action(elem, doc)
    return elem if altered is None else altered


def run_filters(actions, prepare=None, finalize=None, doc=None, stop_if=None):
    """``panflute.run_filters`` for an in-memory ``doc``, using ``walk``."""
    if doc is None:
        raise ValueError("texmark.walk.run_filters needs an in-memory doc")
    if prepare is not None:
        prepare(doc)
    for action in actions:
        doc = walk(doc, action, doc, stop_if)
    if finalize is not None:
        finalize(doc)
    return doc


def run_filter(action, prepare=None, finalize=None, doc=None, stop_if=None):
    """``panflute.run_filter`` for an in-memory ``doc``, using ``walk``."""
    return run_filters([action], prepare=prepare, finalize=finalize,
                       doc=doc, stop_if=stop_if)
