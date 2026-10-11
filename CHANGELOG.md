# Changelog

All notable changes to VELATA are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-10-11

### Added

- `velata inspect FILE...` — autopsy of JPEG (EXIF APP1: make/model/software/
  dates + GPS), PNG (tEXt/iTXt/zTXt, tIME, eXIf), WebP (EXIF/XMP chunks),
  TIFF (IFD0 + EXIF/GPS IFDs), PDF (info dictionary; read-only). `--json`
  for machine-readable output.
- `velata strip FILE... --out OUT | --in-place` — writes a clean copy: JPEG
  loses EXIF APP1 segments, PNG loses text/time/EXIF chunks, WebP loses
  EXIF/XMP chunks, TIFF is rebuilt without the EXIF/GPS/UserComment IFDs
  (thumbnail chain dropped). Bytes are copied verbatim elsewhere.
- Safety rails: `strip` never touches the input without `--in-place`, refuses
  to write over the input path, and reports "nothing to strip" when clean.
- A purpose-built minimal TIFF engine (byte order, IFDs, value decoding,
  GPS rationals, lossless rebuild) — no third-party image libraries.
- Zero runtime dependencies, Python 3.10+, strict mypy and ruff, a pytest
  suite that synthesizes EXIF-bearing JPEG/PNG/WebP/TIFF/PDF fixtures.