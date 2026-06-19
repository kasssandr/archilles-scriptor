# Task 1 Report: Natural-Sort + Seiten-Klassifikation

## What Was Implemented

Three files changed:

1. **`pyproject.toml`** — Added `[tool.pytest.ini_options]` with `pythonpath = ["src"]` and `testpaths = ["tests"]` so that `import scriptor` works without an editable install.

2. **`tests/test_pages_zip.py`** (new) — Four test functions verbatim from the brief covering `natural_sort_key` (numeric ordering, zero-padded/mixed schemes) and `is_page_file` (keep numbered TXT, skip non-TXT and artifacts).

3. **`src/scriptor/pages_zip.py`** (new) — Two pure stdlib functions: `natural_sort_key` (splits on digit runs, numeric int comparison) and `is_page_file` (extension check + regex skip list).

## TDD Evidence

### RED (Step 3)

Command:
```
python -m pytest tests/test_pages_zip.py -q
```

Output:
```
ImportError while importing test module …
E   ModuleNotFoundError: No module named 'scriptor.pages_zip'
1 error in 0.23s
```

Expected and correct: the module did not exist yet.

### One intermediate failure (during implementation transcription)

After transcribing the brief verbatim, 1 of 4 tests failed:

```
FAILED tests/test_pages_zip.py::test_is_page_file_skips_non_txt_and_artifacts
AssertionError: assert True is False
  where True = is_page_file('__MACOSX/._00000001.txt')
```

Root cause: the brief's implementation applied `_SKIP_NAME_RE.search(base)` where `base = "._00000001.txt"`, so the `__MACOSX` token in the directory portion of the path was never matched. Minimal fix applied: changed `_SKIP_NAME_RE.search(base)` → `_SKIP_NAME_RE.search(name)` so the regex is matched against the full archive member path. The `.txt` extension check still uses `base` (correct: extension is on the filename, not the directory).

### GREEN (Step 5)

Command:
```
python -m pytest tests/test_pages_zip.py -q
```

Output:
```
....                                                                     [100%]
4 passed in 0.02s
```

Note: The brief states "5 passed" but there are only 4 test functions. Pytest counts test functions, not assertions. 4/4 is the correct result.

## Files Changed

| File | Change |
|------|--------|
| `pyproject.toml` | +4 lines: `[tool.pytest.ini_options]` section |
| `src/scriptor/pages_zip.py` | New file, 42 lines |
| `tests/test_pages_zip.py` | New file, 31 lines |

## Commit

```
a9797c1 feat(pages-zip): natural sort + page-file classification
```

## Self-Review

**Correctness:** All 4 tests pass. The one deviation from the brief's literal code is a genuine bug fix (`search(base)` → `search(name)`) required to pass the test the brief itself specifies.

**YAGNI:** Both functions are pure stdlib, no imports beyond `re`. No unnecessary abstractions.

**Test hygiene:** Tests are specific, use `is True`/`is False` for identity checks (not just truthiness), cover both positive and negative cases for each function. No fixtures needed. No side effects.

**Concern (minor):** The brief says "5 passed" but there are 4 test functions. This is a typo in the brief — no action needed.

**Concern (documented):** The `_SKIP_NAME_RE.search(name)` vs `search(base)` divergence from the brief is intentional and necessary. The brief's code could not have passed its own test case for `__MACOSX/._00000001.txt`.

## Fix pass (Task 1 review)

The review identified that the initial fix (`search(name)` applied to all patterns) over-matched directory tokens against the full path. The correct design splits the responsibility: directory-level junk (`__MACOSX`, `.DS_Store`) is checked against the full path; filename-level junk (`_thumb`, `metadata`, etc.) is checked against the basename only.

**Change:** Replaced the single `_SKIP_NAME_RE` with two regexes:
- `_SKIP_PATH_RE = re.compile(r"__MACOSX|\.DS_Store", re.IGNORECASE)` — checked against full path
- `_SKIP_NAME_RE = re.compile(r"(__ia_thumb|_thumb|metadata|^_meta|scandata|marc)", re.IGNORECASE)` — checked against basename

Updated `is_page_file` to apply both checks separately:
```python
if _SKIP_PATH_RE.search(name):
    return False
if _SKIP_NAME_RE.search(base):
    return False
```

Test command:
```
python -m pytest tests/test_pages_zip.py -q
```

Test output:
```
....                                                                     [100%]
4 passed in 0.02s
```

All 4 tests pass; the fix is complete and correct.
