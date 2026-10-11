"""PDF metadata inspection — read-only.

PDFs carry their metadata in a document-info dictionary and (in modern files)
in XMP. VELATA reports the classic info entries; stripping PDFs is on the
roadmap but deliberately *unsupported* here — a naive rewrite can corrupt the
xref table, and corrupting a document to clean it is no kindness.
"""

from __future__ import annotations

import re

__all__ = ["inspect_pdf"]

_PATTERNS: dict[str, bytes] = {
    "Title": rb"/Title\s*\((.*?)\)",
    "Author": rb"/Author\s*\((.*?)\)",
    "Creator": rb"/Creator\s*\((.*?)\)",
    "Producer": rb"/Producer\s*\((.*?)\)",
    "CreationDate": rb"/CreationDate\s*\((.*?)\)",
    "ModDate": rb"/ModDate\s*\((.*?)\)",
}


def _clean(raw: bytes) -> str:
    text = raw.replace(b"\\n", b"\n").replace(b"\\r", b"\r").replace(b"\\((", b"(")
    value = text.decode("latin-1")
    return value.replace("\\)", ")").replace("\\(", "(").strip()


def inspect_pdf(data: bytes) -> dict[str, object]:
    if data[:5] != b"%PDF-":
        raise ValueError("not a PDF stream")
    tags: dict[str, str] = {}
    for name, pattern in _PATTERNS.items():
        match = re.search(pattern, data)
        if match:
            tags[name] = _clean(match.group(1))
    return {
        "tags": tags,
        "exif": {},
        "gps": None,
        "metadata_present": bool(tags),
        "strip_supported": False,
    }
