"""PNG chunk walking, text/time metadata extraction and stripping."""

from __future__ import annotations

import struct
from collections.abc import Iterator

__all__ = ["PNG_SIGNATURE", "inspect_png", "iter_chunks", "strip_png"]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Chunks that can carry privacy metadata. zTXt is the compressed form of tEXt.
DROP_CHUNKS = {"tEXt", "iTXt", "zTXt", "tIME", "eXIf"}


def iter_chunks(data: bytes) -> Iterator[tuple[str, bytes, int, int]]:
    """Yield ``(type, payload, start, end)`` for every PNG chunk."""
    offset = 8
    while offset + 8 <= len(data):
        length, raw_type = struct.unpack(">I4s", data[offset : offset + 8])
        type_ = raw_type.decode("latin-1")
        end = offset + 12 + length
        yield type_, data[offset + 8 : end - 4], offset, end
        offset = end


def inspect_png(data: bytes) -> dict[str, object]:
    texts: list[dict[str, str]] = []
    time_value: str | None = None
    exif_present = False
    for type_, payload, _start, _end in iter_chunks(data):
        if type_ == "tEXt":
            keyword, _, value = payload.partition(b"\x00")
            texts.append(
                {
                    "keyword": keyword.decode("latin-1"),
                    "text": value.decode("utf-8", "replace"),
                }
            )
        elif type_ == "iTXt":
            keyword, _, rest = payload.partition(b"\x00")
            # keyword\0 {flag}{method}\0 lang\0 translated-keyword\0 text
            parts = rest.split(b"\x00")
            if len(parts) >= 3:
                translated, _, value = parts[1], b"", b"".join(parts[2:])
                if translated:
                    texts.append(
                        {"keyword": keyword.decode("latin-1"),
                         "text": translated.decode("utf-8", "replace")}
                    )
                else:
                    texts.append(
                        {"keyword": keyword.decode("latin-1"),
                         "text": value.decode("utf-8", "replace")}
                    )
        elif type_ == "tIME":
            year, month, day, hour, minute, second = struct.unpack(
                ">HBBBBB", payload
            )
            time_value = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        elif type_ == "eXIf":
            exif_present = True

    extras: dict[str, object] = {}
    if texts:
        extras["text_chunks"] = texts
    if time_value:
        extras["modification_time"] = time_value
    extras["exif_chunk"] = exif_present
    return {
        "tags": {},
        "exif": {},
        "gps": None,
        "metadata_present": bool(texts) or exif_present,
        "extras": extras,
    }


def strip_png(data: bytes) -> tuple[bytes, bool]:
    """Drop text, time and EXIF chunks; every other byte is preserved."""
    out = bytearray(PNG_SIGNATURE)
    removed = False
    for type_, _payload, start, end in iter_chunks(data):
        if type_ in DROP_CHUNKS:
            removed = True
            continue
        out += data[start:end]
    return bytes(out), removed
