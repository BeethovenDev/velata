"""VELATA command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from velata import BANNER, __version__
from velata.inspect import Inspection, UnsupportedError
from velata.inspect import inspect as do_inspect
from velata.inspect import strip as do_strip

__all__ = ["main"]


def _emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def _render(inspection: Inspection, label: str) -> str:
    lines = [f"{label}  [{inspection.format}]"]
    for name, value in sorted(inspection.tags.items()):
        lines.append(f"  {name}: {value}")
    for extra_name, extra_value in sorted(inspection.extras.items()):
        lines.append(f"  {extra_name}: {extra_value}")
    if inspection.gps:
        lines.append(
            f"  GPS: {inspection.gps.get('latitude')}, {inspection.gps.get('longitude')}"
            f"  ({inspection.gps.get('dms')})"
        )
        if inspection.gps.get("altitude_m") is not None:
            lines.append(f"  altitude: {inspection.gps.get('altitude_m')} m")
    status = "metadata present" if inspection.metadata_present else "clean"
    if not inspection.strip_supported:
        status += " (strip: read-only)"
    lines.append(f"  status: {status}")
    return "\n".join(lines)


def cmd_inspect(args: argparse.Namespace) -> int:
    reports: list[dict[str, object]] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            print(f"error: {raw_path}: {exc}", file=sys.stderr)
            return 2
        try:
            inspection = do_inspect(data)
        except UnsupportedError as exc:
            if args.json:
                reports.append({"file": raw_path, "error": str(exc)})
            else:
                print(f"error: {raw_path}: {exc}", file=sys.stderr)
            continue
        if args.json:
            reports.append({"file": raw_path, **inspection.to_dict()})
        else:
            print(_render(inspection, raw_path))

    if args.json:
        _emit_json({"files": reports})
    return 0


def cmd_strip(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.paths]
    if args.out and len(paths) != 1:
        print("error: --out takes exactly one input file", file=sys.stderr)
        return 2

    results: list[dict[str, object]] = []
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            return 2
        try:
            cleaned, removed = do_strip(data)
        except UnsupportedError as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            return 2

        if args.out:
            target = Path(args.out)
        elif args.in_place:
            target = path
        else:
            print(
                f"error: {path}: choose --in-place or --out (nothing was modified)",
                file=sys.stderr,
            )
            return 2

        if args.out and target.resolve() == path.resolve():
            print(
                f"error: {path}: refusing to write over the input; use --in-place to confirm",
                file=sys.stderr,
            )
            return 2

        if not removed:
            if not args.json:
                print(f"{path}: nothing to strip — file left untouched")
            results.append({"file": str(path), "removed": False, "out": str(target)})
            continue

        target.write_bytes(cleaned)
        if not args.json:
            print(
                f"{path}: stripped {len(data) - len(cleaned)} bytes "
                f"({len(data)} -> {len(cleaned)}) -> {target}"
            )
        results.append(
            {
                "file": str(path),
                "removed": True,
                "out": str(target),
                "original_bytes": len(data),
                "cleaned_bytes": len(cleaned),
            }
        )

    if args.json:
        _emit_json({"files": results})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="velata",
        description="Metadata autopsy & strip — take the veil off files you publish.",
        epilog="Repo: https://github.com/BeethovenDev/velata",
    )
    parser.add_argument("--version", action="version", version=f"velata {__version__}")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="autopsy metadata without touching the file")
    p_inspect.add_argument("paths", nargs="+", metavar="FILE")
    p_inspect.set_defaults(func=cmd_inspect)

    p_strip = sub.add_parser("strip", help="write a copy with metadata removed")
    p_strip.add_argument("paths", nargs="+", metavar="FILE")
    p_strip.add_argument("--out", metavar="FILE", help="output path (single input only)")
    p_strip.add_argument("--in-place", action="store_true", dest="in_place",
                         help="replace the original with the cleaned copy")
    p_strip.set_defaults(func=cmd_strip)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(BANNER, file=sys.stderr)
    try:
        return int(args.func(args))
    except (UnsupportedError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
