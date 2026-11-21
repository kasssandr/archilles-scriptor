"""scriptor eval ab: two frozen trees, one stock, set values.

One throwaway git repository holds a committed copy of src/; both sides run
from it on the two-page golden fixture, so the subprocess path is exercised
exactly as in a real A/B.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scriptor.eval import ab

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "tests" / "fixtures" / "reflow_golden" / "pages"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    *args], check=True, capture_output=True)


@pytest.fixture(scope="module")
def tree(tmp_path_factory) -> Path:
    repo = tmp_path_factory.mktemp("tree")
    shutil.copytree(ROOT / "src" / "scriptor", repo / "src" / "scriptor",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "frozen")
    return repo


def _manifest(path: Path, expect: str = "") -> Path:
    pages = str(PAGES).replace("\\", "/")
    path.write_text(f'[[band]]\nname = "golden"\npages = "{pages}"\n'
                    f'eigenart = "two pages"\n{expect}', encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def run(tree, tmp_path_factory):
    """One A/B of the tree against itself; later tests reuse its outputs."""
    work = tmp_path_factory.mktemp("ab")
    out = work / "out"
    rc = ab.run_ab(tree, tree, _manifest(work / "ab.toml"), out, log=lambda *_: None,
                   jobs=2)
    return rc, out


def test_same_tree_is_byte_identical(run):
    rc, out = run
    assert rc == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    (row,) = report["bands"]
    assert row["identical"] and row["log_identical"]
    assert row["sidecars_differing"] == []
    assert report["a"]["commit"] == report["b"]["commit"]


def test_missed_set_value_fails_and_reuses_outputs(run, tree, tmp_path):
    _, out = run
    stamp = (out / "a" / "golden.md").stat().st_mtime_ns
    got = ab.measure(out / "b" / "golden.md")
    expect = f"[band.expect]\nnotes = {got['notes'] + 1}\npages = {got['pages']}\n"
    lines = []
    rc = ab.run_ab(tree, tree, _manifest(tmp_path / "ab.toml", expect), out,
                   log=lines.append)
    assert rc == 1
    assert "SET VALUE MISSED  notes" in "\n".join(lines)
    assert (out / "a" / "golden.md").stat().st_mtime_ns == stamp  # not recomputed


def test_met_set_values_pass(run, tree, tmp_path):
    _, out = run
    got = ab.measure(out / "b" / "golden.md")
    expect = "[band.expect]\n" + "".join(f"{k} = {v}\n" for k, v in got.items())
    rc = ab.run_ab(tree, tree, _manifest(tmp_path / "ab.toml", expect), out,
                   log=lambda *_: None)
    assert rc == 0


def test_relative_out_lands_beside_the_caller(tree, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = ab.run_ab(tree, tree, _manifest(tmp_path / "ab.toml"), Path("rel"),
                   log=lambda *_: None, jobs=2)
    assert rc == 0
    assert (tmp_path / "rel" / "b" / "golden.md").exists()


def test_dirty_tree_is_refused(tree, tmp_path):
    victim = tree / "src" / "scriptor" / "__init__.py"
    original = victim.read_bytes()
    victim.write_bytes(original + b"\n# local edit\n")
    try:
        with pytest.raises(ab.TreeError, match="uncommitted"):
            ab.run_ab(tree, tree, _manifest(tmp_path / "ab.toml"), tmp_path / "out",
                      log=lambda *_: None)
    finally:
        victim.write_bytes(original)
    assert not (tmp_path / "out").exists()  # refused before anything ran


def test_unknown_expect_key_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="unknown expect key"):
        ab.load_manifest(_manifest(tmp_path / "ab.toml", "[band.expect]\nnotez = 3\n"))


def test_random_draw_skips_listed_bands(tmp_path):
    pool = tmp_path / "pool"
    for name in ("one", "two", "three", "four"):
        (pool / name).mkdir(parents=True)
    (pool / "README.md").write_text("x", encoding="utf-8")
    manifest = tmp_path / "ab.toml"
    manifest.write_text(
        f'[random]\npool = "{str(pool).replace(chr(92), "/")}"\n'
        f'[[band]]\nname = "listed"\npages = "{str(pool / "two").replace(chr(92), "/")}"\n',
        encoding="utf-8")
    m = ab.load_manifest(manifest)
    drawn = ab.draw_random(m, 2, seed=7)
    assert len(drawn) == 2
    assert all(b.pages.name in {"one", "three", "four"} for b in drawn)
    assert [b.name for b in drawn] == [b.name for b in ab.draw_random(m, 2, seed=7)]


def test_log_paths_are_normalised(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    la = ab.normalise_log(f"Written: {a / 'x.md'}\nRunning footers removed (12)", a)
    lb = ab.normalise_log(f"Written: {b / 'x.md'}\nRunning footers removed (14)", b)
    assert la[0] == lb[0]
    assert ab._ordered_minus(la, lb) == ["Running footers removed (12)"]
