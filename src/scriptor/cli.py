"""``scriptor`` CLI — subcommands ``extract``, ``reflow``, ``all``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scriptor import pipeline
from scriptor._text import plural


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scriptor",
        description="PDF -> Markdown converter for scholarly prose.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="PDF -> per-page JSON page model")
    e.add_argument("pdf", type=Path)
    e.add_argument("--out", type=Path, required=True, help="output directory for page JSON")
    e.add_argument(
        "--emit-txt",
        action="store_true",
        help="also write the plain text channel to <out>/txt/ (derived, never read)",
    )

    r = sub.add_parser("reflow", help="per-page JSON/TXT -> Markdown/TXT")
    r.add_argument("src", type=Path, help="directory with page JSON (or legacy TXT) files")
    r.add_argument("--out", type=Path, required=True, help="output .md or .txt file")
    r.add_argument("--format", choices=["md", "txt"], default=None)
    r.add_argument(
        "--decisions",
        type=Path,
        default=None,
        help="decision sidecar: place the footnote markers accepted in it",
    )
    r.add_argument(
        "--ocr-profile",
        type=Path,
        default=None,
        help="OCR profile from `scriptor learn`: what a corrected corpus says the glyphs are",
    )

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
    a.add_argument(
        "--decisions",
        type=Path,
        default=None,
        help="decision sidecar: place the footnote markers accepted in it",
    )
    a.add_argument(
        "--ocr-profile",
        type=Path,
        default=None,
        help="OCR profile from `scriptor learn`: what a corrected corpus says the glyphs are",
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
        help="ZIP/directory of per-page TXT (Internet Archive and similar) -> per-page TXT, optionally reflowed",
    )
    pz.add_argument("src", type=Path, help="ZIP archive or directory of page TXT files")
    pz.add_argument(
        "--out",
        type=Path,
        default=None,
        help="reflowed output (.md/.txt). Without --out only the per-page TXT directory is written",
    )
    pz.add_argument(
        "--pages-dir",
        type=Path,
        default=None,
        help="target directory for the renumbered page TXTs (default: <out|src>_pages)",
    )
    pz.add_argument("--format", choices=["md", "txt"], default=None)
    pz.add_argument(
        "--dry-run",
        action="store_true",
        help="report the file classification (kept/skipped) without writing",
    )

    tp = sub.add_parser(
        "translate-prep",
        help="Markdown master -> translation-ready MD (<dnt> protection) + briefing",
    )
    tp.add_argument("src", type=Path, help="Markdown master (e.g. book.md)")
    tp.add_argument("--out", type=Path, required=True, help="translation-ready .md")

    ln = sub.add_parser(
        "learn",
        help="decision sidecars -> OCR profile (which glyph a corrected corpus calls which digit)",
    )
    ln.add_argument("src", type=Path, nargs="+", help="one or more *.decisions.txt files")
    ln.add_argument("--out", type=Path, required=True, help="output profile .json")

    bf = sub.add_parser(
        "bind-footnotes",
        help="DOCX: attach loose N.) footnotes to the paragraph holding their superscript reference",
    )
    bf.add_argument("src", type=Path, help="input DOCX")
    bf.add_argument("--out", type=Path, required=True, help="output DOCX")
    return p


def main(argv: list[str] | None = None) -> int:
    from scriptor.reflow.decisions import AmbiguousDecision

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return _dispatch(args, parser)
    except AmbiguousDecision as exc:
        # A refusal, not a crash: the user has to say which candidate they mean.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc.filename}: file not found", file=sys.stderr)
        return 2


def _dispatch(args, parser) -> int:
    if args.cmd == "extract":
        written = pipeline.extract(args.pdf, args.out, emit_txt=args.emit_txt)
        print(f"{plural(len(written), 'page')} -> {args.out}", file=sys.stderr)
    elif args.cmd == "reflow":
        pipeline.reflow(args.src, args.out, args.format, args.decisions, args.ocr_profile)
    elif args.cmd == "all":
        pipeline.run_all(
            args.pdf, args.out, args.format, args.pages_dir, args.decisions, args.ocr_profile
        )
    elif args.cmd == "prepared":
        from scriptor.reflow.prepared import convert_file
        audit = convert_file(args.src, args.out)
        print(f"Written: {args.out}", file=sys.stderr)
        audit_path = args.out.with_suffix(args.out.suffix + ".audit.txt")
        if not audit and audit_path.exists():
            audit_path.unlink()
        if audit:
            total = sum(len(v) for v in audit.values())
            lines = [
                f"# Footnote audit for {args.out}",
                f"# {plural(total, 'footnote definition')} without a marker in "
                f"the body, on {plural(len(audit), 'page')};",
                "# each appended to the last visible page as a hanging reference.",
                "",
            ]
            for pn in sorted(audit):
                lines.append(f"p. {pn}: FN {', '.join(audit[pn])}")
            audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"Audit: {plural(total, 'unanchored footnote')} -> {audit_path}", file=sys.stderr)
    elif args.cmd == "clippings":
        from scriptor.clippings import convert_file as clippings_convert
        result = clippings_convert(args.src, args.out, dry_run=args.dry_run)
        verb = "Would write" if args.dry_run else "Written"
        out_target = args.out or args.src.with_suffix(".pandoc.md")
        print(
            f"{verb}: {out_target}  "
            f"({result.converted_in_body}/{result.total_fn_defs} footnote markers linked in the body)",
            file=sys.stderr,
        )
        if result.missing_in_body:
            joined = ", ".join(str(n) for n in result.missing_in_body)
            print(
                f"  ! Markers missing from the body: {joined}",
                file=sys.stderr,
            )
        if result.extra_in_body:
            joined = ", ".join(str(n) for n in result.extra_in_body)
            print(
                f"  ! Surplus markers (>{result.total_fn_defs}): {joined}",
                file=sys.stderr,
            )
        if result.ok:
            print("  OK: every footnote definition is linked once in the body.", file=sys.stderr)
    elif args.cmd == "pages-zip":
        from scriptor.pages_zip import convert as pages_zip_convert

        if args.dry_run:
            result = pages_zip_convert(args.src, None, dry_run=True)
            print(
                f"Would keep {plural(len(result.kept), 'page')}, skip {len(result.skipped)}.",
                file=sys.stderr,
            )
            if result.skipped:
                shown = ", ".join(result.skipped[:10])
                more = " …" if len(result.skipped) > 10 else ""
                print(f"  Skipped: {shown}{more}", file=sys.stderr)
            return 0

        pages_dir = args.pages_dir
        if pages_dir is None:
            base = args.out if args.out is not None else args.src
            pages_dir = base.parent / f"{base.stem}_pages"
        result = pages_zip_convert(args.src, pages_dir, dry_run=False)
        print(
            f"{plural(len(result.kept), 'page')} -> {pages_dir}  "
            f"({len(result.skipped)} skipped, "
            f"{plural(result.encoding_fallbacks, 'encoding fallback')})",
            file=sys.stderr,
        )
        if args.out is not None:
            pipeline.reflow(pages_dir, args.out, args.format)
            print(f"Reflow written: {args.out}", file=sys.stderr)
    elif args.cmd == "translate-prep":
        briefing_path = pipeline.translate_prep(args.src, args.out)
        print(f"Translation-ready file written: {args.out}", file=sys.stderr)
        print(f"Briefing: {briefing_path}", file=sys.stderr)
    elif args.cmd == "learn":
        prof = pipeline.learn(args.src, args.out)
        print(f"Written: {args.out}", file=sys.stderr)
        if not prof:
            print("  ! no candidate was marked in any file; the profile is empty",
                  file=sys.stderr)
        for digit in prof.digits():
            shown = ", ".join(
                f"{g!r} {r.accepted}+/{r.rejected}-"
                for g, r in sorted(prof.glyphs[digit].items(), key=lambda kv: -kv[1].accepted)
            )
            print(f"  footnote {digit}: {shown}", file=sys.stderr)
    elif args.cmd == "bind-footnotes":
        report = pipeline.bind_footnotes(args.src, args.out)
        print(f"Written: {args.out}", file=sys.stderr)
        print(
            f"  {len(report.attached)} attached, "
            f"{plural(len(report.orphan_defs), 'orphaned definition')}, "
            f"{plural(len(report.orphan_refs), 'reference without a definition', 'references without a definition')}",
            file=sys.stderr,
        )
    else:  # pragma: no cover
        parser.error(f"unknown command {args.cmd!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
