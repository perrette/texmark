"""Lossless conversions of figures that pdflatex embeds slowly.

pdftex copies the compressed data of a PNG into the PDF as it is when the
PNG has no alpha channel, at most 8 bits per sample and no interlacing.
Any other PNG it decodes and compresses again, on every pass: for the large
RGBA screenshots of a thesis, about 0.5 s per figure and pass.

``fast_figure(path, build_dir)`` returns a copy of the figure that pdftex
copies as it is, when one can be made without changing the image, else
None. The conversions are:

- an alpha channel that is fully opaque (alpha 255 everywhere) is dropped;
- an interlaced PNG is written without interlacing.

PNGs with real transparency and 16-bit PNGs are left as they are.

The PNG header tells whether a figure is one of these cases, so other
figures cost a read of their first bytes. A candidate is hashed (sha256 of
its contents) and looked up in ``<build_dir>/.texmark-cache/figures/<hash>/``,
which holds either the converted figure, under the original basename, or an
empty file ``unchanged`` when no conversion applies (real transparency).
Deleting the build directory deletes the cache.

The conversions need Pillow. Without it the figures are used as they are,
with a warning naming them.
"""
import hashlib
import os
import struct
from pathlib import Path

from texmark.logs import logger

CACHE_SUBDIR = os.path.join('.texmark-cache', 'figures')
UNCHANGED = 'unchanged'

_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_ALPHA_COLOR_TYPES = (4, 6)   # grey + alpha, RGB + alpha

_warned_no_pillow = set()


def png_header(path):
    """(bit depth, color type, interlace method) of a PNG, or None if the
    file is not a PNG."""
    try:
        with open(path, 'rb') as f:
            head = f.read(29)
    except OSError:
        return None
    if len(head) < 29 or head[:8] != _PNG_SIGNATURE or head[12:16] != b'IHDR':
        return None
    bit_depth, color_type, _, _, interlace = struct.unpack('>BBBBB', head[24:29])
    return bit_depth, color_type, interlace


def is_candidate(path):
    """Whether pdftex would decode the figure at ``path`` (an 8-bit PNG with
    an alpha channel or interlacing)."""
    header = png_header(path)
    if header is None:
        return False
    bit_depth, color_type, interlace = header
    return bit_depth <= 8 and (color_type in _ALPHA_COLOR_TYPES or interlace != 0)


def _convert(src, dst):
    """Write the lossless fast copy of ``src`` to ``dst``. Returns False when
    no conversion applies (the alpha channel is used)."""
    from PIL import Image
    with Image.open(src) as im:
        im.load()
        if im.mode in ('RGBA', 'LA'):
            if im.getchannel('A').getextrema() != (255, 255):
                return False
            im = im.convert('RGB' if im.mode == 'RGBA' else 'L')
        elif im.mode == 'P' and 'transparency' in im.info:
            # a palette with transparent entries: keep it as it is
            return False
        tmp = dst.with_name(dst.name + '.tmp')
        im.save(tmp, format='PNG')
    os.replace(tmp, dst)
    return True


def fast_figure(path, build_dir):
    """The converted copy of the figure ``path`` in the cache of
    ``build_dir`` (made if needed), or None to use ``path`` as it is."""
    path = Path(path)
    if not is_candidate(path):
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    entry = Path(build_dir) / CACHE_SUBDIR / digest
    dst = entry / path.name
    if dst.exists():
        return dst
    if (entry / UNCHANGED).exists():
        return None
    try:
        import PIL  # noqa: F401
    except ImportError:
        if path not in _warned_no_pillow:
            _warned_no_pillow.add(path)
            logger.warning(f"texmark: {path} has an alpha channel or interlacing, "
                           "which pdflatex decodes on every pass; install Pillow "
                           "to have texmark convert it when lossless.")
        return None
    entry.mkdir(parents=True, exist_ok=True)
    try:
        converted = _convert(path, dst)
    except Exception as e:  # unreadable image: use it as it is
        logger.warning(f"texmark: could not convert {path} ({e}); using it as it is")
        return None
    if not converted:
        (entry / UNCHANGED).touch()
        return None
    logger.info(f"texmark: {path.name}: lossless copy for faster embedding in {entry}")
    return dst
