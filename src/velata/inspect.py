"""VELATA dispatch: sniff the format, inspect it, strip it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from velata import jpeg as jpeg_mod
from velata import pdf as pdf_mod
from velata import png as png_mod
from velata import webp as webp_mod
from velata.tiff import REMOVED_TAGS, TiffReader, extract_metadata, strip_metadata_ifds

__all__ = ["Inspection", "UnsupportedError", "inspect", "sniff", "strip"]


class UnsupportedError(ValueError):
    """Raised for formats VELATA cannot or will not process."""


@dataclass
class Inspection:
    format: str
    tags: dict[str, str] = field(default_factory=dict)
    extras: dict[str, object] = field(default_factory=dict)
    gps: dict[str, object] | None = None
    metadata_present: bool = False
    strip_supported: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "tags": self.tags,
            "extras": self.extras,
            "gps": self.gps,
            "metadata_present": self.metadata_present,
            "strip_supported": self.strip_supported,
        }


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(png_mod.PNG_SIGNATURE):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if data[:5] == b"%PDF-":
        return "pdf"
    return None


def _tags_of(raw: dict[str, object], key: str = "tags") -> dict[str, str]:
    value = raw.get(key, {})
    if isinstance(value, dict):
        return cast(dict[str, str], value)
    return {}


def inspect(data: bytes) -> Inspection:
    fmt = sniff(data)
    if fmt is None:
        raise UnsupportedError("unsupported or unknown file format")

    if fmt == "jpeg":
        raw = jpeg_mod.inspect_jpeg(data)
        return Inspection(
            format="jpeg",
            tags=_tags_of(raw),
            extras={"exif": raw.get("exif", {})},
            gps=_as_gps(raw.get("gps")),
            metadata_present=bool(raw.get("metadata_present")),
        )
    if fmt == "png":
        raw = png_mod.inspect_png(data)
        return Inspection(
            format="png",
            extras=_extras_of(raw),
            metadata_present=bool(raw.get("metadata_present")),
        )
    if fmt == "webp":
        raw = webp_mod.inspect_webp(data)
        return Inspection(
            format="webp",
            extras=_extras_of(raw),
            gps=_as_gps(raw.get("gps")),
            metadata_present=bool(raw.get("metadata_present")),
        )
    if fmt == "tiff":
        meta = extract_metadata(data)
        return Inspection(
            format="tiff",
            tags=_tags_of(meta),
            extras={"exif": meta.get("exif", {})},
            gps=_as_gps(meta.get("gps")),
            metadata_present=bool(
                meta.get("gps") or meta.get("tags") or meta.get("exif")
            ),
        )
    if fmt == "pdf":
        raw = pdf_mod.inspect_pdf(data)
        return Inspection(
            format="pdf",
            tags=_tags_of(raw),
            metadata_present=bool(raw.get("metadata_present")),
            strip_supported=False,
        )
    raise UnsupportedError(fmt)  # pragma: no cover - unreachable


def strip(data: bytes) -> tuple[bytes, bool]:
    """Return ``(cleaned_bytes, removed_anything)`` or raise UnsupportedError."""
    fmt = sniff(data)
    if fmt == "jpeg":
        return jpeg_mod.strip_jpeg(data)
    if fmt == "png":
        return png_mod.strip_png(data)
    if fmt == "webp":
        return webp_mod.strip_webp(data)
    if fmt == "tiff":
        reader = TiffReader(data)
        entries, _ = reader.entries(reader.ifd0_offset)
        if not any(entry.tag in REMOVED_TAGS for entry in entries):
            return data, False
        return strip_metadata_ifds(data), True
    if fmt == "pdf":
        raise UnsupportedError(
            "PDF stripping is read-only in velata 0.1.0 — see README"
        )
    raise UnsupportedError("unsupported or unknown file format")


def _extras_of(raw: dict[str, object]) -> dict[str, object]:
    value = raw.get("extras", {})
    return value if isinstance(value, dict) else {}


def _as_gps(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None
