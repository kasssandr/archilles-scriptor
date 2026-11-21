"""A/B through the whole pipeline: two frozen trees, one test stock, set values.

    scriptor eval ab --a <tree> --b <tree> [--manifest ab.toml] [--out dir]
                     [--only name,...] [--random N --seed S] [--force] [--jobs N]

Each tree is a git work tree (``git worktree add --detach``) whose ``src/``
holds no uncommitted change; the tool refuses otherwise and records both
commits in the report. Every band of the manifest is reflowed once per tree
in a subprocess with ``PYTHONPATH=<tree>/src`` -- the very command a user
runs, so nothing is measured by a shortened rig. Outputs already on disk are
reused (resumption) unless ``--force``.

This is the one module of :mod:`scriptor.eval` that runs the converter; it
does so only as a subprocess and never imports it.

The manifest (TOML, kept local: it names copyrighted page models)::

    [random]                       # optional
    pool = "eval/golden-local/pagemodels"

    [[band]]
    name = "fried_donation"
    pages = "corpora/books/.../fried_donation_pages"
    eigenart = "white ink, edition apparatus"
    [band.expect]
    notes = 454

Paths are relative to the repository that holds the manifest, or absolute.
``expect`` keys are optional and exact: ``notes`` (``[^N]:`` lines),
``synthetic_anchors`` (notes.json), ``pages``, ``<source>_labels`` such as
``printed_labels`` (pagination.json), ``headings`` (``#`` lines). A deviation
in either direction is a finding: an improvement is entered on purpose.
The exit code is non-zero when a band failed or a set value was missed in B.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
import tomllib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

WORD = re.compile(r"\w+")
FRONT = re.compile(r"\A---\n.*?\n---\n+", re.DOTALL)
NOTE_DEF = re.compile(r"\[\^\d+\]:")
HEADING = re.compile(r"#{1,6} ")
EXPECT_KEYS = {"notes", "synthetic_anchors", "pages", "headings"}
LABEL_KEY = re.compile(r"([a-z]+)_labels\Z")
# Every file a reflow writes beside <name>.md, in the order the report names them.
SIDECARS = (
    ".review.md", ".md.notes.json", ".md.structure.json", ".md.structure.txt",
    ".md.pagination.json", ".md.pagination.txt", ".md.audit.txt",
    ".md.decisions.txt",
)


@dataclass
class Band:
    name: str
    pages: Path
    eigenart: str = ""
    expect: dict[str, int] = field(default_factory=dict)
    drawn: bool = False


@dataclass
class Manifest:
    bands: list[Band]
    pool: Path | None


def _say(text: str) -> None:
    print(text, flush=True)


class TreeError(Exception):
    """A tree that cannot serve as one side of an A/B."""


# --- manifest -----------------------------------------------------------------

def repo_root(start: Path) -> Path:
    proc = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
    return Path(proc.stdout.strip()) if proc.returncode == 0 else start


def load_manifest(path: Path) -> Manifest:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    root = repo_root(path.resolve().parent)

    def where(p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else root / q

    bands, seen = [], set()
    for entry in raw.get("band", []):
        name = entry["name"]
        if name in seen:
            raise ValueError(f"{path}: band {name!r} listed twice")
        seen.add(name)
        expect = dict(entry.get("expect", {}))
        for key in expect:
            if key not in EXPECT_KEYS and not LABEL_KEY.match(key):
                raise ValueError(f"{path}: band {name!r}: unknown expect key {key!r}")
        bands.append(Band(name, where(entry["pages"]), entry.get("eigenart", ""), expect))
    pool = raw.get("random", {}).get("pool")
    return Manifest(bands, where(pool) if pool else path.resolve().parent / "pagemodels")


def draw_random(manifest: Manifest, n: int, seed: int) -> list[Band]:
    """N page models from the pool that the manifest does not already list."""
    if n <= 0:
        return []
    if manifest.pool is None or not manifest.pool.is_dir():
        raise ValueError(f"random pool {manifest.pool} is not a directory")
    listed = {b.pages.resolve() for b in manifest.bands}
    candidates = sorted(d for d in manifest.pool.iterdir()
                        if d.is_dir() and d.resolve() not in listed)
    chosen = random.Random(seed).sample(candidates, min(n, len(candidates)))
    return [Band(f"rnd_{_slug(d.name)}", d, "random title", drawn=True) for d in chosen]


def _slug(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_").lower()[:32]


# --- trees --------------------------------------------------------------------

def tree_commit(tree: Path) -> str:
    """The tree's HEAD; refuses a tree whose src/ carries uncommitted changes."""
    if not (tree / "src" / "scriptor").is_dir():
        raise TreeError(f"{tree}: no src/scriptor here")
    head = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode != 0:
        raise TreeError(f"{tree}: not a git work tree")
    dirty = subprocess.run(["git", "-C", str(tree), "status", "--porcelain", "--", "src"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise TreeError(f"{tree}: uncommitted changes under src/:\n{dirty}")
    return head.stdout.strip()


def _env(tree: Path) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(tree / "src"), "PYTHONIOENCODING": "utf-8"}


def _check_import(tree: Path) -> None:
    where = subprocess.run([sys.executable, "-c", "import scriptor;print(scriptor.__file__)"],
                           capture_output=True, text=True, env=_env(tree), cwd=tree).stdout.strip()
    if not where or not Path(where).resolve().is_relative_to((tree / "src").resolve()):
        raise TreeError(f"{tree}: scriptor imports from {where or 'nowhere'}, not from this tree")


def prepare_side(tree: Path, commit: str, out: Path, force: bool) -> None:
    """One output folder per tree, stamped with its commit; mixing two is refused."""
    out.mkdir(parents=True, exist_ok=True)
    stamp = out / "COMMIT"
    if stamp.exists() and stamp.read_text(encoding="utf-8").strip() != commit and not force:
        raise TreeError(f"{out} holds outputs of {stamp.read_text().strip()[:10]}, "
                        f"not {commit[:10]}; pass --force or another --out")
    _check_import(tree)
    stamp.write_text(commit + "\n", encoding="utf-8")


def run_band(tree: Path, band: Band, out: Path, force: bool, log=_say) -> dict:
    """Reflow one band with one tree; an output with its log on disk is reused.

    The log is written after the process ends, so its presence marks a run
    that finished rather than one cut off half way.
    """
    target, errlog = out / f"{band.name}.md", out / f"{band.name}.stderr.txt"
    if target.exists() and errlog.exists() and not force:
        return {"rc": 0, "seconds": None}
    errlog.unlink(missing_ok=True)
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "scriptor.cli", "reflow", str(band.pages),
         "--out", str(target), "--format", "md"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=tree, env=_env(tree),
    )
    errlog.write_text(proc.stderr, encoding="utf-8")
    secs = round(time.time() - t0, 1)
    state = "ok" if proc.returncode == 0 else f"FAILED rc={proc.returncode}"
    log(f"  {out.name}: {state:>10}  {band.name}  {secs:.0f}s")
    return {"rc": proc.returncode, "seconds": secs}


# --- measuring one output -------------------------------------------------------

def _read(p: Path) -> str | None:
    return p.read_text(encoding="utf-8") if p.exists() else None


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def body(text: str) -> str:
    return FRONT.sub("", text)


def measure(md: Path) -> dict[str, int]:
    """The numbers a set value may be stated in."""
    text = _read(md) or ""
    lines = body(text).splitlines()
    got = {
        "notes": sum(1 for ln in lines if NOTE_DEF.match(ln)),
        "headings": sum(1 for ln in lines if HEADING.match(ln)),
    }
    pag = _json(Path(str(md) + ".pagination.json")) or {"pages": []}
    got["pages"] = len(pag["pages"])
    for src, n in Counter(p["source"] for p in pag["pages"]).items():
        got[f"{src}_labels"] = n
    notes = _json(Path(str(md) + ".notes.json")) or {"notes": []}
    got["synthetic_anchors"] = sum(1 for n in notes["notes"] if n.get("synthetic"))
    return got


def check_expect(got: dict[str, int], expect: dict[str, int]) -> list[str]:
    return [f"{k}: expected {v}, got {got.get(k, 0)}"
            for k, v in sorted(expect.items()) if got.get(k, 0) != v]


# --- comparing A and B ----------------------------------------------------------

def _labels(md: Path) -> dict[int, dict]:
    pag = _json(Path(str(md) + ".pagination.json"))
    return {p["pos"]: p for p in pag["pages"]} if pag else {}


def _entries_differing(a, b) -> int:
    """Entries of two sidecar documents that differ, list by list, key by key."""
    if a is None or b is None:
        return 0 if a is b else 1
    n = 0
    for key in sorted(set(a) | set(b)):
        va, vb = a.get(key), b.get(key)
        if isinstance(va, list) and isinstance(vb, list):
            n += sum(1 for x, y in zip(va, vb) if x != y) + abs(len(va) - len(vb))
        elif va != vb:
            n += 1
    return n


def normalise_log(text: str, *paths: Path) -> list[str]:
    """stderr lines with the run's own paths replaced, so A and B can be compared."""
    subs = []
    for p in paths:
        for form in {str(p), str(p.resolve()), str(p).replace("\\", "/")}:
            subs.append(form)
    subs.sort(key=len, reverse=True)
    out = []
    for line in text.splitlines():
        for s in subs:
            line = line.replace(s, "<path>")
        out.append(line)
    return out


def _ordered_minus(xs: list[str], ys: list[str]) -> list[str]:
    """Lines of xs not matched by a line of ys, in xs's order (multiset)."""
    rest = Counter(ys)
    out = []
    for x in xs:
        if rest[x]:
            rest[x] -= 1
        else:
            out.append(x)
    return out


def compare_band(band: Band, a_dir: Path, b_dir: Path) -> dict:
    a, b = a_dir / f"{band.name}.md", b_dir / f"{band.name}.md"
    ta, tb = _read(a), _read(b)
    row: dict = {"name": band.name, "eigenart": band.eigenart, "drawn": band.drawn}
    if ta is None or tb is None:
        row["missing"] = [s for s, t in (("a", ta), ("b", tb)) if t is None]
        return row
    row["identical"] = ta == tb
    # The text sidecars name their own output path in their head; that is the
    # one difference two sides always have, so it is taken out before comparing.
    row["sidecars_differing"] = [
        s for s in SIDECARS
        if normalise_log(_read(a_dir / f"{band.name}{s}") or "", a_dir)
        != normalise_log(_read(b_dir / f"{band.name}{s}") or "", b_dir)
    ]
    la, lb = _labels(a), _labels(b)
    row["labels_changed"] = [
        [pos, la.get(pos, {}).get("label"), lb.get(pos, {}).get("label")]
        for pos in sorted(set(la) | set(lb))
        if la.get(pos, {}).get("label") != lb.get(pos, {}).get("label")
    ]
    row["sources"] = [dict(Counter(p["source"] for p in la.values())),
                      dict(Counter(p["source"] for p in lb.values()))]
    row["measured"] = [measure(a), measure(b)]
    for name in ("notes", "structure"):
        ja = _json(a_dir / f"{band.name}.md.{name}.json")
        jb = _json(b_dir / f"{band.name}.md.{name}.json")
        row[f"{name}_json_differing"] = _entries_differing(ja, jb)
    wa = Counter(WORD.findall(body(ta)))
    wb = Counter(WORD.findall(body(tb)))
    lost, gained = wa - wb, wb - wa
    row["words"] = {"lost": sum(lost.values()), "gained": sum(gained.values()),
                    "lost_top": lost.most_common(25), "gained_top": gained.most_common(15)}
    al, bl = ta.splitlines(), tb.splitlines()
    row["lines_lost"] = _ordered_minus(al, bl)[:8]
    row["lines_gained"] = _ordered_minus(bl, al)[:4]
    ea = normalise_log(_read(a_dir / f"{band.name}.stderr.txt") or "", a_dir, band.pages)
    eb = normalise_log(_read(b_dir / f"{band.name}.stderr.txt") or "", b_dir, band.pages)
    row["log_identical"] = ea == eb
    row["log_lost"] = _ordered_minus(ea, eb)
    row["log_gained"] = _ordered_minus(eb, ea)
    return row


# --- report -------------------------------------------------------------------

def render_row(row: dict) -> list[str]:
    name = row["name"]
    if "missing" in row:
        return [f"!! {name}: no output in {', '.join(row['missing'])}"]
    ma, mb = row["measured"]
    head = (f"{name}: notes {ma['notes']}->{mb['notes']}, "
            f"headings {ma['headings']}->{mb['headings']}, "
            f"labels changed {len(row['labels_changed'])}")
    whole = row["identical"] and not row["sidecars_differing"] and row["log_identical"]
    out = []
    if whole:
        out.append(f"== {head} (byte-identical, log identical)")
    else:
        w = row["words"]
        state = "master identical" if row["identical"] else "master differs"
        out.append(f"\n## {head}, words -{w['lost']} +{w['gained']} ({state})")
        if row["sidecars_differing"]:
            out.append("   sidecars differing: " + ", ".join(row["sidecars_differing"]))
        for name_ in ("notes", "structure"):
            n = row[f"{name_}_json_differing"]
            if n:
                out.append(f"   {name_}.json: {n} entries differ")
        if row["sources"][0] != row["sources"][1]:
            out.append(f"   sources {row['sources'][0]} -> {row['sources'][1]}")
        for c in row["labels_changed"][:10]:
            out.append(f"   LABEL pos {c[0]}: {c[1]} -> {c[2]}")
        if w["lost"] or w["gained"]:
            out.append(f"   lost: {dict(w['lost_top'])}")
            out.append(f"   gained: {dict(w['gained_top'])}")
        for line in row["lines_lost"]:
            out.append("   - " + line[:170])
        for line in row["lines_gained"]:
            out.append("   + " + line[:170])
        for line in row["log_lost"]:
            out.append("   log- " + line[:170])
        for line in row["log_gained"]:
            out.append("   log+ " + line[:170])
    for miss in row.get("expect_missed", []):
        out.append(f"   SET VALUE MISSED  {miss}")
    return out


def run_ab(a_tree: Path, b_tree: Path, manifest_path: Path, out: Path,
           only: list[str] | None = None, n_random: int = 0, seed: int = 0,
           force: bool = False, log=_say, jobs: int = 1) -> int:
    # The reflows run with the tree as their working directory; a relative
    # path would land there instead of where the caller meant.
    a_tree, b_tree, out = a_tree.resolve(), b_tree.resolve(), out.resolve()
    manifest = load_manifest(manifest_path)
    bands = list(manifest.bands)
    if only:
        unknown = set(only) - {b.name for b in bands}
        if unknown:
            raise ValueError(f"--only names bands the manifest lacks: {sorted(unknown)}")
        bands = [b for b in bands if b.name in only]
    bands += draw_random(manifest, n_random, seed)
    missing = [b.name for b in bands if not b.pages.is_dir()]
    if missing:
        raise ValueError(f"page models not found for: {missing}")

    commits = {"a": tree_commit(a_tree), "b": tree_commit(b_tree)}
    log(f"a = {a_tree} @ {commits['a'][:10]}")
    log(f"b = {b_tree} @ {commits['b'][:10]}")
    trees = {"a": a_tree, "b": b_tree}
    for side, tree in trees.items():
        prepare_side(tree, commits[side], out / side, force)
    t0 = time.time()
    # Each reflow is its own process, so threads only wait on them; A and B
    # of a band are queued side by side.
    tasks = [(side, band) for band in bands for side in ("a", "b")]
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        done = pool.map(lambda t: run_band(trees[t[0]], t[1], out / t[0], force, log), tasks)
        runs: dict[str, dict] = {"a": {}, "b": {}}
        for (side, band), result in zip(tasks, done):
            runs[side][band.name] = result
    elapsed = round(time.time() - t0, 1)

    rows, failed, missed = [], [], 0
    for band in bands:
        for side in ("a", "b"):
            if runs[side][band.name]["rc"] != 0:
                failed.append(f"{band.name} ({side})")
        row = compare_band(band, out / "a", out / "b")
        if "measured" in row:
            row["expect_missed"] = check_expect(row["measured"][1], band.expect)
            missed += len(row["expect_missed"])
        row["seconds"] = [runs["a"][band.name]["seconds"], runs["b"][band.name]["seconds"]]
        rows.append(row)

    lines = [f"A/B  a {commits['a'][:10]}  b {commits['b'][:10]}  "
             f"({len(bands)} bands, {sum(b.drawn for b in bands)} drawn at random"
             + (f" with seed {seed}" if n_random else "") + ")"]
    for row in rows:
        lines.extend(render_row(row))
    same = sum(1 for r in rows if r.get("identical") and not r.get("sidecars_differing")
               and r.get("log_identical"))
    lines.append("")
    lines.append(f"{same} of {len(rows)} bands byte-identical; "
                 f"{missed} set value(s) missed in b; {len(failed)} run(s) failed"
                 + (f": {', '.join(failed)}" if failed else ""))
    lines.append(f"reflow time this call: {elapsed:.0f}s (reused outputs count as 0)")
    log("\n".join(lines))
    report = {"a": {"tree": str(a_tree), "commit": commits["a"]},
              "b": {"tree": str(b_tree), "commit": commits["b"]},
              "seed": seed if n_random else None, "seconds": elapsed,
              "failed": failed, "set_values_missed": missed, "bands": rows}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    return 1 if failed or missed else 0
