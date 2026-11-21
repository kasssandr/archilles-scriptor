"""The run log: what a reflow reports on stderr, kept beside its output.

``with run_log(out_path):`` doubles ``sys.stderr`` for the duration of the
run and writes ``<out_path>.run.txt`` when it ends -- the console still shows
the same. A run that fails writes its log too, with the traceback appended,
since that is the log one most wants to read. Nested, only the outermost
writes: ``pipeline.run_all`` wraps extract and reflow so the backend's
messages go in as well, and the reflow inside it adds nothing of its own.

The log is not part of the format contract; it is a record of the run.
"""
from __future__ import annotations

import io
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

_depth = 0


class _Tee(io.TextIOBase):
    def __init__(self, console, record: io.StringIO):
        self._console = console
        self._record = record

    def write(self, text: str) -> int:
        self._record.write(text)
        return self._console.write(text)

    def flush(self) -> None:
        self._console.flush()

    @property
    def encoding(self):
        return getattr(self._console, "encoding", "utf-8")


def log_path(out_path: str | Path) -> Path:
    out = Path(out_path)
    return out.with_name(out.name + ".run.txt")


def header() -> str:
    from scriptor import __version__
    from scriptor.reflow.regions import FORMAT_VERSION

    return f"# scriptor {__version__}, format {FORMAT_VERSION}\n"


@contextmanager
def run_log(out_path: str | Path):
    global _depth
    if _depth:
        yield
        return
    record = io.StringIO()
    console = sys.stderr
    sys.stderr = _Tee(console, record)
    _depth += 1
    failed = None
    try:
        yield
    except BaseException:
        failed = traceback.format_exc()
        raise
    finally:
        sys.stderr = console
        _depth -= 1
        path = log_path(out_path)
        if path.parent.is_dir():
            text = header() + record.getvalue() + (failed or "")
            path.write_text(text, encoding="utf-8")
