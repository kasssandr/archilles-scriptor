"""The measuring path stays stdlib-only.

authoring.py may use pymupdf because it prepares material for humans. The
metric modules may not: they must run anywhere a candidate file can be read,
including on machines that never open a PDF.
"""
import ast
from pathlib import Path

import pytest

METRIC_MODULES = [
    "adapters.py", "anchors.py", "citations.py", "flags.py",
    "ground_truth.py", "labels.py", "normalize.py", "report.py", "runner.py",
]


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("module", METRIC_MODULES)
def test_metric_modules_do_not_import_pymupdf(module):
    path = Path(__file__).parent.parent / "src" / "scriptor" / "eval" / module
    assert "pymupdf" not in _imported_names(path)
    assert "fitz" not in _imported_names(path)
