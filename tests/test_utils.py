"""Unit tests for pure-Python utility functions in texmark."""
import panflute as pf
import pytest

from texmark.filters.download_images import is_remote_url, safe_filename_from_url
from texmark.filters.figures import parse_attr_string
from texmark.build import join_if_list, normalize_metadata


class TestIsRemoteUrl:
    def test_http(self):
        assert is_remote_url("http://example.com/figure.png")

    def test_https(self):
        assert is_remote_url("https://example.com/figure.png")

    def test_relative(self):
        assert not is_remote_url("images/figure.png")

    def test_absolute_local(self):
        assert not is_remote_url("/images/figure.png")

    def test_protocol_relative(self):
        # not http(s), so treated as local
        assert not is_remote_url("//example.com/figure.png")


class TestSafeFilenameFromUrl:
    def test_includes_basename(self):
        out = safe_filename_from_url("https://example.com/dir/figure.png")
        assert out.endswith("figure.png")

    def test_deterministic(self):
        url = "https://example.com/figure.png"
        assert safe_filename_from_url(url) == safe_filename_from_url(url)

    def test_distinct_urls_get_distinct_hashes(self):
        a = safe_filename_from_url("https://example.com/a.png")
        b = safe_filename_from_url("https://example.com/b.png")
        assert a != b

    def test_no_basename_falls_back(self):
        out = safe_filename_from_url("https://example.com/")
        # safe_filename_from_url uses "image" + ".png" when no basename;
        # contract is a non-empty filename ending with an extension
        assert out.endswith(".png") or "image" in out


class TestParseAttrString:
    def test_identifier(self):
        ident, classes, attrs = parse_attr_string("#tab:gulf")
        assert ident == "tab:gulf"
        assert classes == []
        assert attrs == {}

    def test_class(self):
        ident, classes, attrs = parse_attr_string(".highlight")
        assert ident == ""
        assert classes == ["highlight"]

    def test_attribute(self):
        ident, classes, attrs = parse_attr_string("width=50%")
        assert attrs == {"width": "50%"}

    def test_combined(self):
        ident, classes, attrs = parse_attr_string("#tab:1 .narrow width=80%")
        assert ident == "tab:1"
        assert classes == ["narrow"]
        assert attrs == {"width": "80%"}

    def test_empty(self):
        ident, classes, attrs = parse_attr_string("")
        assert ident == ""
        assert classes == []
        assert attrs == {}


class TestJoinIfList:
    def test_list(self):
        assert join_if_list(["a", "b"]) == "a\n\nb"

    def test_list_custom_sep(self):
        assert join_if_list(["a", "b", "c"], sep=" | ") == "a | b | c"

    def test_string_passes_through(self):
        assert join_if_list("plain string") == "plain string"

    def test_empty_list(self):
        assert join_if_list([]) == ""

    def test_non_string_non_list_passes_through(self):
        assert join_if_list(None) is None
        assert join_if_list(42) == 42


class TestNormalizeMetadata:
    def test_metastring(self):
        assert normalize_metadata(pf.MetaString("hello")) == "hello"

    def test_metabool(self):
        assert normalize_metadata(pf.MetaBool(True)) is True
        assert normalize_metadata(pf.MetaBool(False)) is False

    def test_metainlines_stringifies(self):
        # MetaInlines of plain words stringifies to their concatenated text
        inlines = pf.MetaInlines(pf.Str("hello"), pf.Space(), pf.Str("world"))
        assert normalize_metadata(inlines) == "hello world"

    def test_metalist_recurses(self):
        ml = pf.MetaList(pf.MetaString("a"), pf.MetaString("b"))
        assert normalize_metadata(ml) == ["a", "b"]

    def test_metamap_recurses(self):
        mm = pf.MetaMap(name=pf.MetaString("alice"), age=pf.MetaString("30"))
        out = normalize_metadata(mm)
        assert out == {"name": "alice", "age": "30"}

    def test_primitive_passthrough(self):
        assert normalize_metadata("str") == "str"
        assert normalize_metadata(7) == 7
