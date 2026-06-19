"""``scriptor`` CLI — subcommands ``extract``, ``reflow``, ``all``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scriptor import pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scriptor",
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

    cl = sub.add_parser(
        "clippings",
        help=(
            "Cambridge-Core / JSTOR / Traditio Markdown clipping (inline number markers + "
            "<sup>N</sup> defs) -> Pandoc-footnote Markdown sidecar"
        ),
    )
    cl.add_argument("src", type=Path, help="clipping .md file")
    cl.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output .md file (default: <src-stem>.pandoc.md alongside the input)",
    )
    cl.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change (counts, missing/extra markers) without writing",
    )

    pz = sub.add_parser(
        "pages-zip",
        help="ZIP/Verzeichnis mit Einzelseiten-TXT (Internet Archive u. ä.) -> Per-Seite-TXT (optional gereflowt)",
    )
    pz.add_argument("src", type=Path, help="ZIP-Archiv oder Verzeichnis mit Seiten-TXT")
    pz.add_argument(
        "--out",
        type=Path,
        default=None,
        help="gereflowte Ausgabe (.md/.txt). Ohne --out wird nur das Per-Seite-TXT-Verzeichnis geschrieben",
    )
    pz.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="Zielverzeichnis für die renummerierten Seiten-TXT (Default: <out|src>_pages)",
    )
    pz.add_argument("--format", choices=["md", "txt"], default=None)
    pz.add_argument(
        "--dry-run",
        action="store_true",
        help="Datei-Klassifikation (übernommen/übersprungen) berichten, ohne zu schreiben",
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
    elif args.cmd == "prepared":
        from scriptor.reflow.prepared import convert_file
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
    elif args.cmd == "clippings":
        from scriptor.clippings import convert_file as clippings_convert
        result = clippings_convert(args.src, args.out, dry_run=args.dry_run)
        verb = "Würde schreiben" if args.dry_run else "Geschrieben"
        out_target = args.out or args.src.with_suffix(".pandoc.md")
        print(
            f"{verb}: {out_target}  "
            f"({result.converted_in_body}/{result.total_fn_defs} FN-Marker im Body verlinkt)",
            file=sys.stderr,
        )
        if result.missing_in_body:
            joined = ", ".join(str(n) for n in result.missing_in_body)
            print(
                f"  ⚠ Fehlende Marker im Body: {joined}",
                file=sys.stderr,
            )
        if result.extra_in_body:
            joined = ", ".join(str(n) for n in result.extra_in_body)
            print(
                f"  ⚠ Übrige Marker (>{result.total_fn_defs}): {joined}",
                file=sys.stderr,
            )
        if result.ok:
            print("  ✓ Alle FN-Definitionen 1:1 im Body verlinkt.", file=sys.stderr)
    elif args.cmd == "pages-zip":
        from scriptor.pages_zip import convert as pages_zip_convert

        if args.dry_run:
            result = pages_zip_convert(args.src, None, dry_run=True)
            print(
                f"Würde {len(result.kept)} Seiten übernehmen, {len(result.skipped)} überspringen.",
                file=sys.stderr,
            )
            if result.skipped:
                shown = ", ".join(result.skipped[:10])
                more = " …" if len(result.skipped) > 10 else ""
                print(f"  Übersprungen: {shown}{more}", file=sys.stderr)
            return 0

        pages_dir = args.pages_dir
        if pages_dir is None:
            base = args.out if args.out is not None else args.src
            pages_dir = base.parent / f"{base.stem}_pages"
        result = pages_zip_convert(args.src, pages_dir, dry_run=False)
        print(
            f"{len(result.kept)} Seiten → {pages_dir}  "
            f"({len(result.skipped)} übersprungen, {result.encoding_fallbacks} Encoding-Fallbacks)",
            file=sys.stderr,
        )
        if args.out is not None:
            pipeline.reflow(pages_dir, args.out, args.format)
            print(f"Reflow geschrieben: {args.out}", file=sys.stderr)
    else:  # pragma: no cover
        parser.error(f"unknown command {args.cmd!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
