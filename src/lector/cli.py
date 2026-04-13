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
    else:  # pragma: no cover
        parser.error(f"unknown command {args.cmd!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
