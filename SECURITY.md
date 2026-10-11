# Security policy

## Scope

VELATA is a local file tool: it makes **no network calls**, stores **no
telemetry**, and writes only the file you explicitly name. It never needs to
"phone home" — reading your file's metadata is a local operation.

## Reporting a vulnerability

Do **not** open a public issue for a security problem. Report it privately via
GitHub's [Security Advisories] for this repository.

- Include the version, platform and Python version.
- Include a minimal reproduction. If the reproduction involves a GPS-bearing
  file, scrub the coordinates from the fixture before sharing.
- Every report is acknowledged within 5 business days.

## Notes for users

- **Inspect is passive.** `velata inspect` never rewrites a file; `strip`
  writes only where told.
- **Stripping is not a guarantee.** VELATA removes the metadata it knows:
  EXIF APP1 in JPEG, text/time/EXIF chunks in PNG, EXIF/XMP in WebP, the
  EXIF/GPS/UserComment IFDs in TIFF, and prints *nothing* for PDFs (read-only).
  Watermarks, steganography, hidden layers and application-specific sidecar
  files are outside its scope.
- **PDF is read-only on purpose.** Rebuilding PDF xref tables is delicate;
  corrupting a document to clean it helps nobody.
- **Thumbnails.** TIFF stripping drops the second IFD (thumbnail). In JPEG a
  thumbnail can live inside the EXIF APP1, which is removed whole.
- Test stripping on copies: VELATA protects your input from accidental
  overwrite, but no tool can protect a file from an attacker after you
  published it stripped *and* the original.

[Security Advisories]: https://github.com/BeethovenDev/velata/security/advisories