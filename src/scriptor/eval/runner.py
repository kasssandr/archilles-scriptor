"""Orchestration: one (truth, candidate file) pair -> VolumeReport."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scriptor.eval.adapters import ADAPTERS
from scriptor.eval.anchors import AnchorResult, evaluate_anchors
from scriptor.eval.citations import CitationResult, evaluate_citations
from scriptor.eval.flags import FlagResult, evaluate_flags
from scriptor.eval.ground_truth import load_truth
from scriptor.eval.labels import LabelResult, evaluate_labels


@dataclass
class VolumeReport:
    volume: str
    candidate: str
    anchors: AnchorResult
    labels: LabelResult
    flags: FlagResult
    citations: CitationResult


def evaluate_file(truth_path: Path, candidate_path: Path, adapter: str) -> VolumeReport:
    truth = load_truth(Path(truth_path))
    text = Path(candidate_path).read_text(encoding="utf-8")
    doc = ADAPTERS[adapter](text)
    return VolumeReport(
        volume=truth.volume,
        candidate=Path(candidate_path).name.removesuffix(".md"),
        anchors=evaluate_anchors(truth, doc),
        labels=evaluate_labels(truth, doc),
        flags=evaluate_flags(truth, doc),
        citations=evaluate_citations(truth, doc),
    )


def _adapter_for(path: Path) -> str:
    name = path.name
    return "prepared" if (name.endswith(".review.md") or name.endswith(".prepared.md")) else "plain"


def evaluate_suite(golden_dirs: list[Path], outputs_dir: Path) -> list[VolumeReport]:
    reports: list[VolumeReport] = []
    for gdir in golden_dirs:
        for truth_path in sorted(Path(gdir).glob("*/truth.toml")):
            volume_dir = Path(outputs_dir) / truth_path.parent.name
            if not volume_dir.is_dir():
                continue
            for cand in sorted(volume_dir.glob("*.md")):
                reports.append(evaluate_file(truth_path, cand, _adapter_for(cand)))
    return reports
