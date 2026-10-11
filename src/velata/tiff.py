"""Minimal pure-Python TIFF / EXIF engine.

Enough TIFF to find and decode the metadata that matters (make, model,
software, dates, GPS) and to rebuild a *cleaned* TIFF whose metadata IFDs
(EXIF 0x8769, GPS 0x8825, UserComment 0x9286) are gone. Value bytes are
copied verbatim, so the rebuild is lossless for every metadata tag that stays.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

__all__ = [
    "TIFF_MAGIC",
    "TiffReader",
    "extract_metadata",
    "gps_from_ifd",
    "strip_metadata_ifds",
]

TIFF_MAGIC = 42

# Tags whose presence is a privacy risk, even when "empty".
REMOVED_TAGS = (0x8769, 0x8825, 0x9286)  # EXIF IFD, GPS IFD, UserComment

TAG_NAMES_IFD0 = {
    0x010E: "ImageDescription",
    0x010F: "Make",
    0x0110: "Model",
    0x0112: "Orientation",
    0x0131: "Software",
    0x0132: "DateTime",
    0x8298: "Copyright",
    0xA434: "LensModel",
    0xA433: "LensMake",
}

TAG_NAMES_EXIF = {
    0x829A: "ExposureTime",
    0x829D: "FNumber",
    0x8827: "ISOSpeedRatings",
    0x9003: "DateTimeOriginal",
    0x9004: "DateTimeDigitized",
    0xA002: "PixelXDimension",
    0xA003: "PixelYDimension",
}

GPS_NAMES = {
    0x0001: "LatitudeRef",
    0x0002: "Latitude",
    0x0003: "LongitudeRef",
    0x0004: "Longitude",
    0x0005: "AltitudeRef",
    0x0006: "Altitude",
    0x0007: "TimeStamp",
    0x001D: "DateStamp",
    0x0011: "ImgDirection",
    0x0012: "ImgDirectionRef",
}

# IFD field types and their byte widths.
TYPE_SIZES = {
    1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8,
}

Scalar = int | float | str | bytes
TIFFValue = Scalar | list[Scalar]


@dataclass(frozen=True)
class TiffEntry:
    tag: int
    type: int
    count: int
    offset: int      # value: inline int, or absolute pointer into the file
    position: int    # absolute position of this entry's 12 bytes


@dataclass(frozen=True)
class GpsData:
    latitude: float
    longitude: float
    dms: str
    altitude_m: float | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "dms": self.dms,
            "altitude_m": self.altitude_m,
            "timestamp": self.timestamp,
        }


class TiffReader:
    """Parse a TIFF byte stream located at ``base`` inside ``data``."""

    def __init__(self, data: bytes, base: int = 0) -> None:
        if len(data) < base + 8:
            raise ValueError("TIFF stream too short")
        two = data[base : base + 2]
        if two == b"II":
            self.byte_order = "<"
        elif two == b"MM":
            self.byte_order = ">"
        else:
            raise ValueError("not a TIFF stream (bad byte order marker)")
        magic = struct.unpack(self.byte_order + "H", data[base + 2 : base + 4])[0]
        if magic != TIFF_MAGIC:
            raise ValueError(f"not TIFF (magic 0x{magic:x})")
        (self.ifd0_offset,) = struct.unpack(self.byte_order + "I", data[base + 4 : base + 8])
        self.data = data
        self.base = base
        if self.ifd0_offset < 8:
            raise ValueError(f"suspicious IFD0 offset {self.ifd0_offset}")

    def _slice(self, file_offset: int, length: int) -> bytes:
        start = self.base + file_offset
        return self.data[start : start + length]

    def entries(self, ifd_offset: int) -> tuple[list[TiffEntry], int]:
        count = struct.unpack(
            self.byte_order + "H", self._slice(ifd_offset, 2)
        )[0]
        out: list[TiffEntry] = []
        for index in range(count):
            position = ifd_offset + 2 + index * 12
            tag, field_type, item_count, value_field = struct.unpack(
                self.byte_order + "HHII", self._slice(position, 12)
            )
            out.append(
                TiffEntry(tag, field_type, item_count, value_field, self.base + position)
            )
        next_ifd = struct.unpack(
            self.byte_order + "I", self._slice(ifd_offset + 2 + count * 12, 4)
        )[0]
        return out, next_ifd

    def value_bytes(self, entry: TiffEntry) -> bytes:
        size = TYPE_SIZES.get(entry.type)
        if size is None:
            return b""
        byte_len = size * entry.count
        if byte_len <= 0:
            return b""
        if byte_len <= 4:
            return self._slice(entry.position - self.base + 8, byte_len)
        return self._slice(entry.offset, byte_len)

    def decode(self, entry: TiffEntry) -> TIFFValue | None:
        raw = self.value_bytes(entry)
        if entry.type == 2:  # ASCII
            return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
        if entry.type in (1, 6, 7):  # BYTE / SBYTE / UNDEFINED
            return list(raw)
        fmt_size = {3: "H", 4: "I", 8: "h", 9: "i"}.get(entry.type)
        if fmt_size:
            return list(struct.unpack(self.byte_order + f"{entry.count}{fmt_size}", raw))
        if entry.type in (5, 10):  # RATIONAL / SRATIONAL
            integers = struct.unpack(
                self.byte_order + f"{entry.count * 2}I", raw
            )
            return [
                integers[i] / integers[i + 1] if integers[i + 1] else 0.0
                for i in range(0, len(integers), 2)
            ]
        if entry.type == 12:  # DOUBLE
            return list(struct.unpack(self.byte_order + f"{entry.count}d", raw))
        return None


def _ifd_tags(reader: TiffReader, entries: list[TiffEntry]) -> dict[int, TIFFValue]:
    tags: dict[int, TIFFValue] = {}
    for entry in entries:
        value = reader.decode(entry)
        if value is not None:
            tags[entry.tag] = value
    return tags


def gps_from_ifd(reader: TiffReader, gps_entries: list[TiffEntry]) -> GpsData | None:
    tags = _ifd_tags(reader, gps_entries)
    lat = tags.get(0x0002)
    lon = tags.get(0x0004)
    if not isinstance(lat, list) or not isinstance(lon, list) or not lat or not lon:
        return None
    lat_ref = str(tags.get(0x0001, "N"))
    lon_ref = str(tags.get(0x0003, "E"))

    def to_decimal(triple: list[Scalar], ref: str) -> float:
        a, b, c = float(triple[0]), float(triple[1]), float(triple[2])
        value = a + b / 60.0 + c / 3600.0
        return -value if ref.upper() in ("S", "W") else value

    lat_dec = to_decimal(lat, lat_ref)
    lon_dec = to_decimal(lon, lon_ref)
    dms = _format_dms(lat, lat_ref, lon, lon_ref)

    altitude: float | None = None
    alt = tags.get(0x0006)
    if isinstance(alt, list) and alt:
        altitude = float(alt[0])
        if str(tags.get(0x0005, "0")) == "1":
            altitude = -altitude  # below sea level

    timestamp: str | None = None
    time_parts = tags.get(0x0007)
    if isinstance(time_parts, list) and time_parts:
        h, m, s = int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
        stamp = f"{h:02d}:{m:02d}:{s:02d}"
        day = tags.get(0x001D)
        if isinstance(day, str) and day:
            stamp = f"{day.strip()} {stamp}"
        timestamp = stamp

    return GpsData(lat_dec, lon_dec, dms, altitude, timestamp)


def _format_dms(lat: list[Scalar], lat_ref: str, lon: list[Scalar], lon_ref: str) -> str:
    def fmt(triple: list[Scalar], ref: str) -> str:
        a, b, c = float(triple[0]), float(triple[1]), float(triple[2])
        return f"{int(a)}°{int(b):02d}'{c:.2f}\" {ref}"

    return f"{fmt(lat, lat_ref.upper())}  {fmt(lon, lon_ref.upper())}"


def extract_metadata(data: bytes, base: int = 0) -> dict[str, object]:
    """Return ``{tags, exif, gps}`` from a TIFF byte stream."""
    reader = TiffReader(data, base)
    entries, _ = reader.entries(reader.ifd0_offset)

    tags: dict[str, object] = {}
    for entry in entries:
        if entry.tag in TAG_NAMES_IFD0:
            value = reader.decode(entry)
            if value not in (None, ""):
                tags[TAG_NAMES_IFD0[entry.tag]] = _stringify(value)
        elif entry.tag == 0x0100:  # ImageWidth / height are harmless
            continue

    exif: dict[str, object] = {}
    gps: GpsData | None = None
    for entry in entries:
        if entry.tag == 0x8769:  # EXIF IFD pointer
            pointer = _pointer(reader, entry)
            if pointer is not None:
                sub_entries, _ = reader.entries(pointer)
                for sub in sub_entries:
                    if sub.tag in TAG_NAMES_EXIF:
                        value = reader.decode(sub)
                        if value not in (None, ""):
                            exif[TAG_NAMES_EXIF[sub.tag]] = _stringify(value)
        elif entry.tag == 0x8825:  # GPS IFD pointer
            pointer = _pointer(reader, entry)
            if pointer is not None:
                gps_entries, _ = reader.entries(pointer)
                gps = gps_from_ifd(reader, gps_entries)

    return {"tags": tags, "exif": exif, "gps": gps.to_dict() if gps else None}


def _pointer(reader: TiffReader, entry: TiffEntry) -> int | None:
    value = reader.decode(entry)
    if isinstance(value, list) and value:
        return int(value[0])
    return None


def _stringify(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(_stringify(item) for item in value)
    if isinstance(value, float):
        return f"{value:.6g}".rstrip("0").rstrip(".")
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def strip_metadata_ifds(data: bytes, base: int = 0) -> bytes:
    """Rebuild a TIFF with EXIF/GPS/UserComment IFDs removed.

    The first IFD is kept (minus the privacy pointers); the thumbnail chain
    is dropped (next-IFD pointer = 0); value bytes are copied verbatim.
    """
    reader = TiffReader(data, base)
    entries, _ = reader.entries(reader.ifd0_offset)
    kept = [entry for entry in entries if entry.tag not in REMOVED_TAGS]

    header = data[base : base + 4] + struct.pack(reader.byte_order + "I", 8)
    heap = bytearray()
    encoded: list[bytes] = []
    for entry in kept:
        raw_value = reader.value_bytes(entry)
        if len(raw_value) <= 4:
            field = raw_value.ljust(4, b"\x00")
        else:
            offset = 8 + 2 + 12 * len(kept) + 4 + len(heap)
            if offset % 2:
                heap.extend(b"\x00")
                offset += 1
            heap.extend(raw_value)
            field = struct.pack(reader.byte_order + "I", offset)
        encoded.append(
            struct.pack(reader.byte_order + "HHI", entry.tag, entry.type, entry.count)
            + field
        )

    ifd0 = (
        struct.pack(reader.byte_order + "H", len(kept))
        + b"".join(encoded)
        + struct.pack(reader.byte_order + "I", 0)
    )
    return header + ifd0 + bytes(heap)
