from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class ToolPaths:
    jpegli: Path
    mozjpeg: Path
    butteraugli: Path


@dataclass(slots=True)
class NormalizedImage:
    source_path: Path
    stem: str
    width: int
    height: int
    png_path: Path
    bmp_path: Path


@dataclass(slots=True)
class CandidateResult:
    encoder: str
    subsampling: str
    progressive: Optional[bool]
    quality_label: str
    output_path: Path
    size_bytes: int
    butteraugli_score: float
    command: str


@dataclass(slots=True)
class CompressionSummary:
    total_files: int
    compressed_files: int
    skipped_files: int
    failed_files: int
    cancelled: bool
