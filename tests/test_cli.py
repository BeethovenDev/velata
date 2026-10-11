"""CLI tests for VELATA."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.test_formats import build_jpeg, build_tiff


def _run(*argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "velata", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        env=env,
    )


def _jpeg_file(tmp_path: Path) -> Path:
    path = tmp_path / "photo.jpg"
    path.write_bytes(build_jpeg(build_tiff(make="EOS R5")))
    return path


def test_inspect_json(tmp_path: Path) -> None:
    path = _jpeg_file(tmp_path)
    proc = _run("--json", "inspect", str(path), cwd=tmp_path)
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["files"][0]["format"] == "jpeg"
    assert payload["files"][0]["tags"]["Make"] == "EOS R5"
    assert payload["files"][0]["metadata_present"] is True


def test_strip_out_writes_clean_copy(tmp_path: Path) -> None:
    path = _jpeg_file(tmp_path)
    out = tmp_path / "photo.clean.jpg"
    proc = _run("strip", str(path), "--out", str(out), cwd=tmp_path)
    assert proc.returncode == 0
    assert out.read_bytes() == build_jpeg(build_tiff(make="EOS R5"), exif=False)


def test_strip_in_place_and_require_confirmation(tmp_path: Path) -> None:
    path = _jpeg_file(tmp_path)
    # without a destination nothing is modified
    proc = _run("strip", str(path), cwd=tmp_path)
    assert proc.returncode == 2
    assert "nothing was modified" in proc.stderr
    assert b"Exif" in path.read_bytes()
    # with --in-place the file is replaced
    proc = _run("strip", str(path), "--in-place", cwd=tmp_path)
    assert proc.returncode == 0
    assert b"Exif" not in path.read_bytes()


def test_strip_pdf_reports_read_only(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.7\n")
    proc = _run("strip", str(path), "--in-place", cwd=tmp_path)
    assert proc.returncode == 2
    assert "read-only" in proc.stderr


def test_inspect_unknown_format(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\x00\x01\x02")
    proc = _run("inspect", str(path), cwd=tmp_path)
    assert proc.returncode == 0  # soft-fails per file
    assert "unsupported" in proc.stdout or "unsupported" in proc.stderr
