"""The JSON Schema of the front matter (texmark.schema, ``texmark schema``):
the output, the template names, and that every key texmark reads is in it.

jsonschema is not a dependency: ``_validate`` below checks the subset of
JSON Schema that the schema uses.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import frontmatter
import jinja2
import jinja2.meta
import jinja2.nodes
import pytest

from texmark import schema as S

REPO_ROOT = Path(__file__).parent.parent
PACKAGE = REPO_ROOT / 'texmark'

# Variables that a template sets itself ({% set %} in a block).
TEMPLATE_LOCALS = {'_', '_kp', '_hl_list', 'words'}


def _cli(*args):
    return subprocess.run([sys.executable, '-m', 'texmark.cli', *args],
                          capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope='module')
def schema():
    return json.loads(_cli('schema'))


# ---------------------------------------------------------------------------
# a small validator
# ---------------------------------------------------------------------------

_TYPES = {'string': str, 'boolean': bool, 'object': dict, 'array': list,
          'integer': int, 'number': (int, float)}


def _is_type(value, name):
    if name in ('integer', 'number') and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def _errors(value, sub, root, path='$'):
    if '$ref' in sub:
        ref = root
        for part in sub['$ref'].lstrip('#/').split('/'):
            ref = ref[part]
        yield from _errors(value, ref, root, path)
    if 'type' in sub:
        types = sub['type'] if isinstance(sub['type'], list) else [sub['type']]
        if not any(_is_type(value, t) for t in types):
            yield f"{path}: {value!r} is not of type {types}"
            return
    if 'const' in sub and value != sub['const']:
        yield f"{path}: {value!r} != {sub['const']!r}"
    if 'enum' in sub and not any(value == e and type(value) is type(e) for e in sub['enum']):
        yield f"{path}: {value!r} not in {sub['enum']}"
    if 'oneOf' in sub:
        if sum(not list(_errors(value, s, root, path)) for s in sub['oneOf']) != 1:
            yield f"{path}: {value!r} matches not exactly one of oneOf"
    if 'anyOf' in sub:
        if all(list(_errors(value, s, root, path)) for s in sub['anyOf']):
            yield f"{path}: {value!r} matches none of anyOf"
    if isinstance(value, dict):
        props = sub.get('properties', {})
        extra = sub.get('additionalProperties', True)
        for k, v in value.items():
            if k in props:
                yield from _errors(v, props[k], root, f"{path}.{k}")
            elif extra is False:
                yield f"{path}: unexpected key {k}"
            elif isinstance(extra, dict):
                yield from _errors(v, extra, root, f"{path}.{k}")
    if isinstance(value, list) and 'items' in sub:
        for i, v in enumerate(value):
            yield from _errors(v, sub['items'], root, f"{path}[{i}]")


def _validate(value, schema):
    return list(_errors(value, schema, schema))


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

def test_version_flag():
    out = subprocess.run([sys.executable, '-m', 'texmark.cli', '--version'],
                         capture_output=True, text=True, check=True).stdout
    assert re.fullmatch(r'texmark \d+\.\d+\.\d+\S*\n', out)


def test_output_is_a_json_schema(schema):
    assert schema['$schema'] == 'https://json-schema.org/draft/2020-12/schema'
    assert schema['type'] == 'object'
    assert schema['additionalProperties'] is True

    def check(sub, path):
        assert sub.get('description'), path
        assert 'type' in sub or '$ref' in sub or 'anyOf' in sub, path
        for key, child in sub.get('properties', {}).items():
            check(child, f'{path}.{key}')
        for i, child in enumerate(sub.get('anyOf', [])):
            if '$ref' not in child:
                check(child, f'{path}|{i}')
        if isinstance(sub.get('items'), dict) and sub['items'].get('type') == 'object':
            check(sub['items'], f'{path}[]')
        if sub.get('type') == 'array' or 'array' in (sub.get('type') or []):
            assert 'items' in sub, path

    for key, sub in schema['properties'].items():
        check(sub, key)


def test_journal_template_lists_the_installed_templates(schema):
    folders = {d.name for d in (PACKAGE / 'templates').iterdir()
               if (d / 'template.tex').is_file()}
    choices = {c['const']: c.get('description')
               for c in schema['$defs']['template']['oneOf']}
    assert folders <= set(choices)
    assert all(choices[name] for name in folders)
    assert choices['nature'].startswith('Alias of springernature')
    journal = schema['properties']['journal']
    obj = next(s for s in journal['anyOf'] if s.get('type') == 'object')
    assert obj['properties']['template']['$ref'] == '#/$defs/template'


def test_new_template_folder_is_listed(tmp_path, monkeypatch):
    (tmp_path / 'mine').mkdir()
    (tmp_path / 'mine' / 'template.tex').write_text(
        '{# texmark-template: My journal -#}\n\\documentclass{article}\n')
    (tmp_path / 'notatemplate').mkdir()
    monkeypatch.setattr(S, 'TEMPLATES_DIR', tmp_path)
    assert S.templates() == {'mine': 'My journal'}


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_example_frontmatter_validates(schema):
    meta = frontmatter.loads((REPO_ROOT / 'example.md').read_text()).metadata
    assert meta
    assert _validate(meta, schema) == []


@pytest.mark.parametrize('meta', [
    {'journal': 'nature'},
    {'journal': {'template': 'copernicus', 'short': 'cp', 'draft': False}},
    {'journal': {'template': 'elsarticle', 'options': ['final', '5p']}},
    {'authors': [{'firstname': 'A', 'lastname': 'B', 'affiliation': '1,2',
                  'corresponding': True}],
     'bibliography': ['a.bib', 'b.bib'], 'changes': 'auto', 'build_synctex': False,
     'keywords': ['x', 'y'], 'figure-span': 'full', 'pandoc-only-key': 3},
])
def test_valid_frontmatter(schema, meta):
    assert _validate(meta, schema) == []


@pytest.mark.parametrize('meta', [
    {'journal': {'template': 'nosuchjournal'}},
    {'journal': 'nosuchjournal'},
    {'authors': 'A. B.'},
    {'engine': 'tex'},
    {'build_draft': 'yes'},
])
def test_invalid_frontmatter(schema, meta):
    assert _validate(meta, schema) != []


# ---------------------------------------------------------------------------
# every key that texmark reads is in the schema
# ---------------------------------------------------------------------------

_PY_READS = [
    r"get_metadata\(\s*['\"]([^'\"]+)['\"]",
    r"\b\w*meta\w*\.get\(\s*['\"]([^'\"]+)['\"]",
    r"\b\w*meta\w*\[\s*['\"]([^'\"]+)['\"]\s*\]",
]
_PY_JOURNAL_READS = [
    r"\[['\"]journal['\"]\]\.get\(\s*['\"]([^'\"]+)['\"]",
    r"get\(['\"]journal['\"][^)]*\)\.get\(\s*['\"]([^'\"]+)['\"]",
]


def _python_sources():
    return [(p, p.read_text()) for p in PACKAGE.rglob('*.py')]


def test_keys_read_by_the_python_code_are_in_the_schema():
    known = set(S.FRONTMATTER) | S.INTERNAL_KEYS
    missing = {}
    for path, text in _python_sources():
        for pattern in _PY_READS:
            for key in re.findall(pattern, text):
                if key not in known:
                    missing.setdefault(key, path.name)
    assert missing == {}
    journal = set(S.JOURNAL['properties'])
    for path, text in _python_sources():
        for pattern in _PY_JOURNAL_READS:
            assert set(re.findall(pattern, text)) <= journal, path


def test_keys_read_through_tables_are_in_the_schema():
    from texmark.filters.crossref import CrossrefFilter
    from texmark.journals import FrontmatterFilter
    keys = {key for _c, key, _cmd in CrossrefFilter._COUNTER_MAP}
    keys |= set(FrontmatterFilter.FRONT_SECTIONS)
    assert keys <= set(S.FRONTMATTER)


def _template_asts():
    env = jinja2.Environment()
    env.filters['join_if_list'] = lambda value, *a: value
    for path in sorted((PACKAGE / 'templates').glob('*/template.tex')):
        yield path, env.parse(path.read_text())


def test_template_variables_are_in_the_schema():
    known = set(S.FRONTMATTER) | S.INTERNAL_KEYS | TEMPLATE_LOCALS
    for path, ast in _template_asts():
        missing = jinja2.meta.find_undeclared_variables(ast) - known
        assert not missing, (path.parent.name, missing)


def test_template_attributes_are_in_the_schema():
    """journal.x, running.x, beamer.x, author.x and selectattr('x') on the
    authors."""
    props = {
        'journal': set(S.JOURNAL['properties']),
        'running': set(S.FRONTMATTER['running']['properties']),
        'beamer': set(S.BEAMER['properties']),
        'author': set(S.AUTHOR['properties']),
    }
    for path, ast in _template_asts():
        for node in ast.find_all(jinja2.nodes.Getattr):
            if isinstance(node.node, jinja2.nodes.Name) and node.node.name in props:
                assert node.attr in props[node.node.name], (path.parent.name, node.node.name,
                                                            node.attr)
        for node in ast.find_all(jinja2.nodes.Filter):
            if node.name == 'selectattr' and node.args:
                arg = node.args[0]
                if isinstance(arg, jinja2.nodes.Const):
                    assert arg.value in props['author'], (path.parent.name, arg.value)
