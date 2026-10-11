"""JPEG segment walking, EXIF extraction and metadata stripping."""

from __future__ import annotations

import struct
from collections.abc import Iterator

from velata.tiff import extract_metadata

__all__ = ["APP1", "inspect_jpeg", "iter_segments", "strip_jpeg"]

APP1 = 0xE1  # ff e1
SOS = 0xDA  # ff da
EOI = 0xD9  # ff d9

_NO_LENGTH_MARKERS = {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, EOI}


def iter_segments(data: bytes) -> Iterator[tuple[int, bytes]]:
    """Yield ``(marker, payload)`` for every marker segment until SOS/EOI."""
    index = 2  # after SOI
    while index + 4 <= len(data):
        if data[index] != 0xFF:
            break
        marker = data[index + 1]
        if marker == 0xFF:  # padding byte
            index += 1
            continue
        if marker in _NO_LENGTH_MARKERS:
            yield marker, b""
            index += 2
            if marker == EOI:
                return
            continue
        if index + 4 > len(data):
            break
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        if length < 2:
            raise ValueError("corrupt JPEG: impossible segment length")
        yield marker, data[index + 4 : index + 2 + length]
        index += 2 + length
        if marker == SOS:
            return


def inspect_jpeg(data: bytes) -> dict[str, object]:
    payload = _exif_app1_payload(data)
    if payload is None:
        return {"tags": {}, "exif": {}, "gps": None, "metadata_present": False}
    meta = extract_metadata(payload)
    meta["metadata_present"] = True
    return meta


def _exif_app1_payload(data: bytes) -> bytes | None:
    for marker, payload in iter_segments(data):
        if marker == APP1 and payload.startswith(b"Exif\x00\x00"):
            return payload[6:]
    return None


def strip_jpeg(data: bytes) -> tuple[bytes, bool]:
    """Remove EXIF APP1 segments; everything else is copied byte-for-byte."""
    out = bytearray(b"\xff\xd8")
    removed = False
    index = 2
    while index + 4 <= len(data):
        if data[index] != 0xFF:
            out += data[index:]
            break
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in _NO_LENGTH_MARKERS:
            out += data[index : index + 2]
            index += 2
            if marker == EOI:
                return bytes(out), removed
            continue
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        segment = data[index : index + 2 + length]
        if marker == APP1 and segment[4:].startswith(b"Exif\x00\x00"):
            removed = True
        else:
            out += segment
        index += 2 + length
        if marker == SOS:
            out += data[index:]
            return bytes(out), removed
    out += data[index:]
    return bytes(out), removed
