"""``lector`` CLI — subcommands ``extract``, ``reflow``, ``all``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lector import pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lector",
        description="PDF -> Markdown converter for scholarly prose.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="PDF -> per-page TXT")
    e.add_argument("pdf", type=Path)
    e.add_argument("--out", type=Path, required=True, help="output directory for page TXTs")

    r = sub.add_parser("reflow", help="per-page TXT -> Markdown/TXT")
    r.add_argument("src", type=Path, help="directory with page TXT files")
    r.add_argument("--out", type=Path, required=True, help="output .md or .txt file")
    r.add_argument("--format", choices=["md", "txt"], default=None)

    a = sub.add_parser("all", help="PDF -> Markdown in one shot")
    a.add_argument("pdf", type=Path)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--format", choices=["md", "txt"], default=None)
    a.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="directory for intermediate page TXTs (default: <out>_pages next to output)",
    )

    pr = sub.add_parser(
        "prepared",
        help="single prepared TXT (---/-- separators, (N) footnote markers) -> Markdown",
    )
    pr.add_argument("src", type=Path, help="prepared TXT file")
    pr.add_argument("--out", type=Path, required=True, help="output .md file")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "extract":
        written = pipeline.extract(args.pdf, args.out)
        print(f"{len(written)} Seiten nach {args.out}", file=sys.stderr)
    elif args.cmd == "reflow":
        pipeline.reflow(args.src, args.out, args.format)
    elif args.cmd == "all":
        pipeline.run_all(args.pdf, args.out, args.format, args.pages_dir)
    elif args.cmd == "prepared":
        from lector.reflow.prepared import convert_file
        audit = convert_file(args.src, args.out)
        print(f"Geschrieben: {args.out}", file=sys.stderr)
        audit_path = args.out.with_suffix(args.out.suffix + ".audit.txt")
        if not audit and audit_path.exists():
            audit_path.unlink()
        if audit:
            total = sum(len(v) for v in audit.values())
            lines = [
                f"# Fußnoten-Audit für {args.out}",
                f"# {total} FN-Definition(en) ohne Marker im Body auf {len(audit)} Seite(n);",
                f"# an die jeweils letzte sichtbare Seite als hanging reference angehängt.",
                "",
            ]
            for pn in sorted(audit):
                lines.append(f"S. {pn}: FN {', '.join(audit[pn])}")
            audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"Audit: {total} unverankerte FNs → {audit_path}", file=sys.stderr)
    else:  # pragma: no cover
        parser.error(f"unknown command {args.cmd!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
