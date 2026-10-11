"""Format-level tests for VELATA, built on synthesized fixtures."""

from __future__ import annotations

import struct
import zlib

import pytest

from velata.inspect import UnsupportedError, inspect, sniff, strip
from velata.jpeg import inspect_jpeg, strip_jpeg
from velata.pdf import inspect_pdf
from velata.png import inspect_png, strip_png
from velata.tiff import extract_metadata, strip_metadata_ifds
from velata.webp import inspect_webp, strip_webp

U16, U32 = None, None  # removed

def u16(value: int) -> bytes:
    return struct.pack("<H", value)


def u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _rational(num: int, den: int) -> bytes:
    return u32(num) + u32(den)


def build_tiff(
    *,
    make: str = "EOS R5",
    software: str = "VELATA-CAM",
    lat=(50, 27, 0, "N"),
    lon=(30, 31, 24, "E"),
) -> bytes:
    """Assemble a little-endian TIFF: IFD0 + GPS IFD + EXIF IFD + value heap."""
    lat_deg, lat_min, lat_sec, lat_ref = lat
    lon_deg, lon_min, lon_sec, lon_ref = lon

    def inline_entry(tag: int, typ: int, count: int, value: bytes) -> bytes:
        return u16(tag) + u16(typ) + u32(count) + value.ljust(4, b"\x00")

    def off_entry(tag: int, typ: int, count: int, offset: int) -> bytes:
        return u16(tag) + u16(typ) + u32(count) + u32(offset)

    def ptr_entry(tag: int, offset: int) -> bytes:
        return inline_entry(tag, 4, 1, u32(offset))

    heap = bytearray()

    def heap_add(payload: bytes) -> int:
        offset = 146 + len(heap)
        heap.extend(payload)
        return offset

    make_off = heap_add(make.encode() + b"\x00")
    sw_off = heap_add(software.encode() + b"\x00")
    dt_off = heap_add(b"2024:03:11 14:22:05\x00")
    lat_off = heap_add(
        _rational(lat_deg, 1)
        + _rational(lat_min, 1)
        + _rational(int(lat_sec * 1000), 1000)
    )
    lon_off = heap_add(
        _rational(lon_deg, 1)
        + _rational(lon_min, 1)
        + _rational(int(lon_sec * 1000), 1000)
    )

    ifd0 = bytearray()
    ifd0 += u16(5)
    ifd0 += off_entry(0x010F, 2, len(make) + 1, make_off)           # Make
    ifd0 += off_entry(0x0131, 2, len(software) + 1, sw_off)         # Software
    ifd0 += inline_entry(0x0112, 3, 1, u16(1))                      # Orientation = 1
    ifd0 += ptr_entry(0x8769, 128)                                  # -> EXIF IFD
    ifd0 += ptr_entry(0x8825, 74)                                   # -> GPS IFD
    ifd0 += u32(0)                                                  # no next IFD

    gps = bytearray()
    gps += u16(4)
    gps += inline_entry(0x0001, 2, 2, lat_ref.encode() + b"\x00")
    gps += inline_entry(0x0003, 2, 2, lon_ref.encode() + b"\x00")
    gps += off_entry(0x0002, 5, 3, lat_off)
    gps += off_entry(0x0004, 5, 3, lon_off)
    gps += u32(0)

    exif = bytearray()
    exif += u16(1)
    exif += off_entry(0x9003, 2, 20, dt_off)                        # DateTimeOriginal
    exif += u32(0)

    return b"II" + u16(42) + u32(8) + bytes(ifd0) + bytes(gps) + bytes(exif) + bytes(heap)


def build_jpeg(tiff: bytes, exif: bool = True) -> bytes:
    def segment(marker: int, payload: bytes) -> bytes:
        return bytes([0xFF, marker]) + struct.pack(">H", 2 + len(payload)) + payload

    out = b"\xff\xd8"
    out += segment(0xE0, b"JFIF\x00\x01\x01")  # APP0
    if exif:
        out += segment(0xE1, b"Exif\x00\x00" + tiff)  # APP1
    out += b"\xff\xd9"  # EOI
    return out


def _chunk(type_: bytes, payload: bytes) -> bytes:
    data = type_ + payload
    return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF)


def build_png(with_metadata: bool = True) -> bytes:
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out += _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    if with_metadata:
        out += _chunk(b"tEXt", b"Author\x00Ludwig van Beethoven")
        out += _chunk(b"tIME", struct.pack(">HBBBBB", 2024, 3, 11, 14, 22, 5))
    out += _chunk(b"IDAT", b"\x78\x9c\x00\x00\x00\x00")
    out += _chunk(b"IEND", b"")
    return bytes(out)


def build_webp(tiff: bytes, with_exif: bool = True) -> bytes:
    chunks = bytearray()
    if with_exif:
        chunks += b"EXIF" + u32(len(tiff) + 6) + b"Exif\x00\x00" + tiff
    chunks += b"VP8L" + u32(6) + b"\x2f\x00\x00\x00\x00\x00"
    return b"RIFF" + u32(4 + len(chunks)) + b"WEBP" + bytes(chunks)


# ---- TIFF -----------------------------------------------------------------

def test_sniff_tiff() -> None:
    data = build_tiff()
    assert sniff(data) == "tiff"
    assert sniff(b"\x00\x01\x02") is None


def test_extract_tiff_tags_and_gps() -> None:
    meta = extract_metadata(build_tiff())
    assert meta["tags"]["Make"] == "EOS R5"
    assert meta["tags"]["Software"] == "VELATA-CAM"
    assert meta["exif"]["DateTimeOriginal"] == "2024:03:11 14:22:05"
    gps = meta["gps"]
    assert gps is not None
    assert abs(gps["latitude"] - 50.45) < 0.001
    assert abs(gps["longitude"] - 30.5234) < 0.001


def test_strip_tiff_removes_gps_and_exif_but_keeps_make() -> None:
    original = build_tiff()
    cleaned = strip_metadata_ifds(original)
    assert original != cleaned
    meta = extract_metadata(cleaned)
    assert meta["gps"] is None
    assert meta["exif"] == {}
    assert meta["tags"]["Make"] == "EOS R5"
    reader = _reader(cleaned)
    entries, _ = reader.entries(reader.ifd0_offset)
    assert {e.tag for e in entries} >= {0x010F, 0x0131, 0x0112}
    assert not {e.tag for e in entries} & {0x8769, 0x8825}


# ---- JPEG -----------------------------------------------------------------

def test_jpeg_inspect_and_strip() -> None:
    tiff = build_tiff()
    jpeg = build_jpeg(tiff)
    raw = inspect_jpeg(jpeg)
    assert raw["metadata_present"] is True
    assert raw["tags"]["Make"] == "EOS R5"
    assert raw["gps"] is not None

    cleaned, removed = strip_jpeg(jpeg)
    assert removed is True
    assert b"Exif" not in cleaned
    # JFIF APP0 survives, SOI/EOI survive
    assert cleaned.startswith(b"\xff\xd8")
    assert cleaned.endswith(b"\xff\xd9")
    assert b"JFIF" in cleaned
    # stripping a clean file reports removed=False
    assert strip_jpeg(build_jpeg(tiff, exif=False)) == (build_jpeg(tiff, exif=False), False)


# ---- PNG ------------------------------------------------------------------

def test_png_inspect_finds_text_and_time() -> None:
    data = build_png()
    raw = inspect_png(data)
    assert raw["metadata_present"] is True
    texts = raw["extras"]["text_chunks"]
    assert texts[0]["keyword"] == "Author"
    assert texts[0]["text"] == "Ludwig van Beethoven"
    assert raw["extras"]["modification_time"].startswith("2024-03-11")


def test_png_strip_keeps_image_chunks() -> None:
    cleaned, removed = strip_png(build_png())
    assert removed is True
    assert b"tEXt" not in cleaned
    assert b"Author" not in cleaned
    assert b"IDAT" in cleaned and b"IEND" in cleaned and b"IHDR" in cleaned
    assert strip_png(build_png(with_metadata=False)) == (build_png(with_metadata=False), False)


# ---- WebP -----------------------------------------------------------------

def test_webp_inspect_and_strip() -> None:
    data = build_webp(build_tiff())
    raw = inspect_webp(data)
    assert raw["metadata_present"] is True
    assert "EXIF" in raw["extras"]["embedded_chunks"]
    assert raw["gps"] is not None

    cleaned, removed = strip_webp(data)
    assert removed is True
    assert b"EXIF" not in cleaned
    assert b"VP8L" in cleaned
    # RIFF size header stays consistent: re-parse and check chunk names
    names = [name for name, _p, _s, _e in _riff_chunks(cleaned)]
    assert names == ["VP8L"]


# ---- PDF ------------------------------------------------------------------

def test_pdf_inspect_only() -> None:
    data = b"%PDF-1.7\n/Author (Beethoven)\n/Producer (LibreOffice)\n"
    raw = inspect_pdf(data)
    assert raw["tags"]["Author"] == "Beethoven"
    assert raw["tags"]["Producer"] == "LibreOffice"
    assert raw["strip_supported"] is False


def test_dispatch_strip_pdf_unsupported() -> None:
    with pytest.raises(UnsupportedError):
        strip(b"%PDF-1.7\n/Author (X)\n")


def test_dispatch_inspect_unknown() -> None:
    with pytest.raises(UnsupportedError):
        inspect(b"\x00\x01\x02\x03whatever")


def _reader(data: bytes):
    from velata.tiff import TiffReader

    return TiffReader(data)


def _riff_chunks(data: bytes):
    from velata.webp import iter_riff_chunks

    return list(iter_riff_chunks(data))
