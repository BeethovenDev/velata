"""WebP (RIFF) chunk walking and EXIF/XMP stripping."""

from __future__ import annotations

import struct
from collections.abc import Iterator

from velata.tiff import extract_metadata

__all__ = ["inspect_webp", "iter_riff_chunks", "strip_webp"]

DROP_CHUNKS = {"EXIF", "XMP ", "XMP"}


def iter_riff_chunks(data: bytes) -> Iterator[tuple[str, bytes, int, int]]:
    """Yield ``(fourcc, payload, start, end)`` for chunks inside ``RIFF....WEBP``."""
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a RIFF WebP stream")
    riff_payload_end = 12 + struct.unpack("<I", data[4:8])[0] - 4
    offset = 12
    while offset + 8 <= min(len(data), riff_payload_end):
        fourcc = data[offset : offset + 4].decode("latin-1")
        size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        end = offset + 8 + size
        yield fourcc, data[offset + 8 : end], offset, end
        offset = end + (size & 1)  # odd-sized chunks are padded to even


def inspect_webp(data: bytes) -> dict[str, object]:
    chunk_names: list[str] = []
    exif_present = False
    gps: dict[str, object] | None = None
    for fourcc, payload, _start, _end in iter_riff_chunks(data):
        if fourcc not in DROP_CHUNKS:
            continue
        chunk_names.append(fourcc)
        if fourcc == "EXIF" and payload.startswith(b"Exif\x00\x00"):
            exif_present = True
            meta = extract_metadata(payload[6:])
            if isinstance(meta["gps"], dict):
                gps = meta["gps"]
    return {
        "tags": {},
        "exif": {},
        "gps": gps,
        "metadata_present": bool(chunk_names),
        "extras": {
            "embedded_chunks": sorted(chunk_names),
            "exif_present": exif_present,
        },
    }


def strip_webp(data: bytes) -> tuple[bytes, bool]:
    """Drop EXIF and XMP chunks, renumber the RIFF size, preserve the rest."""
    kept: list[bytes] = []
    removed = False
    for fourcc, _payload, start, end in iter_riff_chunks(data):
        if fourcc in DROP_CHUNKS:
            removed = True
            continue
        kept.append(data[start:end])

    body = bytearray()
    for chunk in kept:
        body += chunk
        if len(chunk) & 1:
            body += b"\x00"
    riff_size = 4 + len(body)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WEBP" + bytes(body), removed
