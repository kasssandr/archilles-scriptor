"""Evaluation harness: measures what a converter did to the apparatus.

Pure file evaluation — the harness never imports or runs a converter. It
compares candidate outputs (prepared Markdown or foreign tool output)
against hand-authored ground truth (truth.toml). See
docs/PREPARED_FORMAT_SPEC.md for the format under test.
"""
