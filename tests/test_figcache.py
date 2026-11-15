"""texmark.figcache: lossless copies of the PNGs that pdflatex decodes."""
import struct
import zlib
from pathlib import Path

import panflute as pf
import pytest

from texmark import figcache
from texmark.figcache import CACHE_SUBDIR, UNCHANGED, fast_figure, is_candidate
from texmark.filters.images import ResolveImagePathsFilter


def write_png(path, width=4, height=3, color_type=6, alpha=255, interlace=0):
    """A small 8-bit PNG (color type 2: RGB, 6: RGBA) written without Pillow.
    ``interlace`` is only written in the header (enough for is_candidate)."""
    channels = {2: 3, 6: 4}[color_type]
    pixel = bytes([200, 100, 50, alpha][:channels])
    raw = b''.join(b'\x00' + pixel * width for _ in range(height))

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', width, height, 8, color_type, 0, 0, interlace)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                           + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return Path(path)


def test_candidates(tmp_path):
    assert is_candidate(write_png(tmp_path / 'rgba.png', color_type=6))
    assert is_candidate(write_png(tmp_path / 'inter.png', color_type=2, interlace=1))
    assert not is_candidate(write_png(tmp_path / 'rgb.png', color_type=2))
    (tmp_path / 'fig.pdf').write_bytes(b'%PDF-1.5\n')
    assert not is_candidate(tmp_path / 'fig.pdf')


def test_non_candidate_is_not_read_beyond_header(tmp_path):
    rgb = write_png(tmp_path / 'rgb.png', color_type=2)
    assert fast_figure(rgb, tmp_path / 'build') is None
    assert not (tmp_path / 'build').exists()


def test_without_pillow_warns_and_keeps_original(tmp_path, monkeypatch, caplog):
    import builtins
    real_import = builtins.__import__

    def no_pil(name, *args, **kwargs):
        if name == 'PIL' or name.startswith('PIL.'):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_pil)
    monkeypatch.setattr(figcache, '_warned_no_pillow', set())
    png = write_png(tmp_path / 'rgba.png')
    assert fast_figure(png, tmp_path / 'build') is None
    assert 'install Pillow' in caplog.text


def test_opaque_alpha_is_dropped_and_cached(tmp_path):
    Image = pytest.importorskip('PIL.Image')
    png = write_png(tmp_path / 'shot.png', alpha=255)
    build = tmp_path / 'build'
    fast = fast_figure(png, build)
    assert fast is not None and fast.name == 'shot.png'
    assert fast.parent.parent == build / CACHE_SUBDIR
    with Image.open(fast) as im:
        assert im.mode == 'RGB'
        assert im.getpixel((0, 0)) == (200, 100, 50)
    assert not is_candidate(fast)
    # second call: from the cache, not converted again
    mtime = fast.stat().st_mtime_ns
    assert fast_figure(png, build) == fast
    assert fast.stat().st_mtime_ns == mtime


def test_real_transparency_is_kept(tmp_path):
    pytest.importorskip('PIL')
    png = write_png(tmp_path / 'logo.png', alpha=128)
    build = tmp_path / 'build'
    assert fast_figure(png, build) is None
    entries = list((build / CACHE_SUBDIR).iterdir())
    assert len(entries) == 1 and (entries[0] / UNCHANGED).exists()
    assert fast_figure(png, build) is None


def _run_filter(tmp_path, copy_figures):
    write_png(tmp_path / 'shot.png')
    build = tmp_path / 'build'
    build.mkdir()
    doc = pf.Doc(pf.Para(pf.Image(url='shot.png')))
    doc.metadata['texmark'] = pf.MetaMap(
        build_dir=pf.MetaString(str(build)), source_dir=pf.MetaString(str(tmp_path)),
        cwd=pf.MetaString(str(tmp_path)), copy_figures=pf.MetaBool(copy_figures))
    f = ResolveImagePathsFilter()
    f.prepare(doc)
    doc = doc.walk(f.action)
    f.finalize(doc)
    return build, doc.content[0].content[0].url, f


def test_filter_default_mode_points_to_converted_copy(tmp_path):
    pytest.importorskip('PIL')
    build, url, f = _run_filter(tmp_path, copy_figures=False)
    assert url.startswith(CACHE_SUBDIR) and url.endswith('shot.png')
    assert (build / url).exists()
    assert f.url_map == {'shot.png': url}


def test_filter_copy_mode_bundles_converted_copy(tmp_path):
    pytest.importorskip('PIL')
    build, url, _ = _run_filter(tmp_path, copy_figures=True)
    assert url == 'figures/shot.png'
    assert not is_candidate(build / url)
    assert is_candidate(tmp_path / 'shot.png')   # original untouched
