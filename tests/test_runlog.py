"""The run log: stderr of a reflow, word for word, beside its output."""
from pathlib import Path

import pytest

from scriptor import __version__
from scriptor._runlog import log_path, run_log
from scriptor.reflow.core import main as reflow_main
from scriptor.reflow.regions import FORMAT_VERSION

PAGES = Path(__file__).parent / "fixtures" / "reflow_golden" / "pages"
HEAD = f"# scriptor {__version__}, format {FORMAT_VERSION}\n"


@pytest.mark.parametrize("fmt", ["md", "txt"])
def test_reflow_writes_what_the_console_showed(tmp_path, capsys, fmt):
    out = tmp_path / f"book.{fmt}"
    reflow_main(str(PAGES), str(out), fmt)
    shown = capsys.readouterr().err
    assert "Output format" in shown
    assert (tmp_path / f"book.{fmt}.run.txt").read_text(encoding="utf-8") == HEAD + shown


def test_nested_logs_write_once_with_everything(tmp_path, capsys):
    import sys

    out = tmp_path / "book.md"
    with run_log(out):
        print("backend: 3 pages without a text layer", file=sys.stderr)
        reflow_main(str(PAGES), str(out), "md")
    text = log_path(out).read_text(encoding="utf-8")
    assert text.startswith(HEAD + "backend: 3 pages without a text layer\n")
    assert text.count(HEAD) == 1
    assert text == HEAD + capsys.readouterr().err


def test_a_failed_run_keeps_its_log_and_the_traceback(tmp_path):
    import sys

    out = tmp_path / "book.md"
    before = sys.stderr
    with pytest.raises(ValueError, match="broken page"):
        with run_log(out):
            print("Reading 2 pages", file=sys.stderr)
            raise ValueError("broken page")
    assert sys.stderr is before
    text = log_path(out).read_text(encoding="utf-8")
    assert "Reading 2 pages" in text
    assert "ValueError: broken page" in text
    # After a failure the next run logs again: the nesting count came back down.
    with run_log(tmp_path / "next.md"):
        print("second run", file=sys.stderr)
    assert "second run" in log_path(tmp_path / "next.md").read_text(encoding="utf-8")


def test_log_goes_beside_the_output():
    assert log_path("x/book.md") == Path("x/book.md.run.txt")
