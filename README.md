<div align="center">

# VELATA

**Metadata autopsy & strip — take the veil off files you publish.**

*From Fidelio: the prisoner held behind veils of identity. VELATA looks at
everything a file carries that you did not write in visible ink — EXIF, GPS,
editor names, hidden timestamps — and then removes it before the file leaves
your hands.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#philosophy)

</div>

---

Before you publish an image, a document or a scan, VELATA asks: *what does
this file know that I don't?* A camera writes its model and the coordinates
of your breakfast table into the pixels. An office file stamps your account
name into its properties. VELATA shows you every one of those hidden notes —
then strips them, byte for byte.

## Install

```bash
git clone https://github.com/BeethovenDev/velata.git
cd velata
python -m pip install -e .
```

## Quick start

```bash
# What does this file know about you?
velata inspect photo.jpg report.pdf data.tif

# Write a clean copy (the original is never touched)
velata strip photo.jpg --out photo.clean.jpg

# Or confirm you want the original replaced
velata strip photo.jpg --in-place

# Machine-readable, for pipelines
velata --json inspect photo.jpg
```

## What VELATA sees and strips

| Format | Inspected | Stripped |
|--------|-----------|----------|
| JPEG   | EXIF APP1 (make, model, software, dates) + GPS | whole EXIF APP1 removed |
| PNG    | tEXt / iTXt / zTXt, tIME, eXIf | text, time and EXIF chunks removed |
| WebP   | EXIF and XMP chunks + GPS | EXIF/XMP chunks removed |
| TIFF   | IFD0 tags, EXIF IFD, GPS IFD | EXIF/GPS/UserComment IFDs rebuilt away |
| PDF    | `/Author /Creator /Producer /Dates` | read-only (see below) |

GPS is decoded to decimal and DMS and reported prominently — it is the single
most revealing piece of metadata there is.

## Why PDF is read-only

PDF xref tables are unforgiving. A naive rewrite can corrupt a document.
VELATA prefers to tell you exactly what the PDF contains and let you clean it
in the tool that made it — corrupting your document to clean it helps nobody.

## Safety rails

* `strip` writes **only** where you name a destination.
* Writing over the input requires `--in-place` — the explicit command.
* A file with no metadata is reported "nothing to strip" and left alone.
* Every other byte is copied verbatim; only the metadata construct goes away.

## How it works

```
bytes ──sniff──▶ jpeg | png | webp | tiff | pdf
                     │
        container parsers (segments, chunks, IFDs)
                     │
        make/model/software/dates + GPS decode  →  inspect
                     │
        segment/chunk/IFD surgery  →  strip (verbatim elsewhere)
```

## Philosophy

* **Passive by default, explicit by design.** Inspect never writes; strip
  only writes where told.
* **Purpose-built, dependency-free.** A small TIFF engine is worth keeping
  auditable; no image library drags in guesswork.
* **Honest about limits.** The list of what is *not* stripped (watermarks,
  steganography, sidecars, PDF internals) is in the README, not in fine print.

## License

MIT