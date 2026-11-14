"""CriticMarkup to spans (texmark.criticmarkup)."""
from texmark.criticmarkup import rewrite, found


def test_marks_become_spans():
    text, f = rewrite('a {++ new [@k] ++} b {-- old --} c {== hi ==} d {>> note <<} e')
    assert f
    assert text == 'a [new [@k]]{.added} b [old]{.deleted} c [hi]{.highlight} d [note]{.comment} e'


def test_substitution_and_attached_comment():
    text, _ = rewrite('{~~ old ~> new ~~}{>> why <<}.')
    assert text == '[old]{.deleted}[new]{.added comment="why"}.'
    text, _ = rewrite('{-- gone --} {>> it was wrong <<}')
    assert text == '[gone]{.deleted comment="it was wrong"}'


def test_no_mark_across_blank_line_and_code_untouched():
    src = '{++ open\n\nnot closed ++}\n\n```\n{-- code --}\n```\n\n{-- x --}'
    text, f = rewrite(src)
    assert f
    assert '{++ open' in text and '{-- code --}' in text and text.endswith('[x]{.deleted}')


def test_found_and_plain_text():
    assert not found('nothing here, not even {braces}')
    assert rewrite('plain') == ('plain', False)
    assert found('a {++ b ++}')


def test_inline_code_untouched():
    text, f = rewrite('Write `{++ x ++}` or ``{-- `y` --}`` for {++ z ++}.')
    assert f
    assert text == 'Write `{++ x ++}` or ``{-- `y` --}`` for [z]{.added}.'
    assert not found('only `{== code ==}` here')


def test_code_inside_a_mark_is_kept():
    assert rewrite('{++ call `f(x)` ++}')[0] == '[call `f(x)`]{.added}'


def test_fences_of_any_length_and_tildes():
    src = ('````md\n```\n{-- in code --}\n```\n````\n\n'
           '~~~\n{++ in code ++}\n~~~\n\n  ```python\n{== code ==}\n  ```\n\n{-- out --}')
    text, f = rewrite(src)
    assert f
    for kept in ('{-- in code --}', '{++ in code ++}', '{== code ==}'):
        assert kept in text
    assert text.endswith('[out]{.deleted}')


def test_unclosed_fence_leaves_the_rest_alone():
    text, f = rewrite('{++ a ++}\n\n```\n{++ b ++}\n')
    assert f and text.startswith('[a]{.added}') and '{++ b ++}' in text


def test_unbalanced_brackets_escaped():
    assert rewrite('{++ see [x ++}')[0] == r'[see \[x]{.added}'
    assert rewrite('{-- a] --}')[0] == r'[a\]]{.deleted}'
    assert rewrite('{++ [@k] and [link](u) ++}')[0] == '[[@k] and [link](u)]{.added}'


def test_comment_attribute_quoting_and_whitespace():
    text, _ = rewrite('{++ a ++}{>> say "hi"\nthen \\o <<}')
    assert text == '[a]{.added comment="say \\"hi\\" then \\\\o"}'


def test_marks_read_by_pandoc():
    """The spans written by ``rewrite`` are read by pandoc as intended."""
    import json
    import panflute as pf
    from texmark.project import parse_markdown
    doc = pf.load(__import__('io').StringIO(parse_markdown(
        'A {++ new [@k] ++}{>> why "so" <<} {-- old [ --} {~~ x ~> y ~~}.\n')))
    spans = [e for e in doc.content[0].content if isinstance(e, pf.Span)]
    assert [s.classes for s in spans] == [['added'], ['deleted'], ['deleted'], ['added']]
    assert spans[0].attributes['comment'] == 'why "so"'
    assert isinstance(spans[0].content[-1], pf.Cite)
    assert pf.stringify(spans[1]) == 'old ['


def test_front_matter_untouched():
    src = '---\ntitle: "a {++ b ++}"\n---\n\nText {++ c ++}.\n'
    text, f = rewrite(src)
    assert f
    assert text == '---\ntitle: "a {++ b ++}"\n---\n\nText [c]{.added}.\n'
    assert not found('---\nnote: "{-- x --}"\n---\n\nPlain.\n')


def test_block_markers_stay_outside_the_spans():
    src = '{++ ## Results\n- first\n  - nested ++}{>> why <<}'
    assert rewrite(src)[0] == (
        '## [Results]{.added}\n- [first]{.added}\n  - [nested]{.added comment="why"}')
    assert rewrite('{-- 1. one --}')[0] == '1. [one]{.deleted}'
    assert rewrite('{++ > quoted ++}')[0] == '> [quoted]{.added}'


def test_block_markers_only_at_line_start():
    assert rewrite('Text {++ # not a heading ++}')[0] == 'Text [# not a heading]{.added}'
    assert rewrite('Text {++ more\n- item ++}')[0] == 'Text [more]{.added}\n- [item]{.added}'


def test_marks_in_indented_code_math_and_raw_latex_restored():
    import io
    import panflute as pf
    from texmark.project import parse_markdown
    src = ('Para {++ a ++}.\n\n    code {++ b ++}\n\n'
           'Math $x^{++}$ and {== c ==}.\n\n\\begin{verbatim}\n{-- d --}\n\\end{verbatim}\n')
    doc = pf.load(io.StringIO(parse_markdown(src)))
    code = [e.text for e in doc.content if isinstance(e, (pf.CodeBlock, pf.RawBlock))]
    assert code == ['code {++ b ++}', '\\begin{verbatim}\n{-- d --}\n\\end{verbatim}']
    spans = []
    doc.walk(lambda e, d: spans.append(pf.stringify(e)) if isinstance(e, pf.Span) else None)
    assert spans == ['a', 'c']
