from __future__ import annotations

import re
from pathlib import Path
from threading import Event

from .encoders import render_command, run_external
from .models import ToolPaths


class ScoringError(RuntimeError):
    pass


class ButteraugliScorer:
    FLOAT_RE = re.compile(r"(?<![A-Za-z])([-+]?[0-9]*\.?[0-9]+)")

    def __init__(self, tools: ToolPaths, cancel_event: Event | None = None):
        self.tools = tools
        self.cancel_event = cancel_event

    def score(self, reference_image: Path, candidate_image: Path) -> float:
        cmd = [
            str(self.tools.butteraugli),
            str(reference_image),
            str(candidate_image),
        ]
        completed = run_external(cmd, cancel_event=self.cancel_event)
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        if completed.returncode != 0:
            raise ScoringError(
                f"Butteraugli failed with exit code {completed.returncode}.\n"
                f"Command: {render_command(cmd)}\n{output}"
            )

        score = self._extract_first_float(output)
        if score is None:
            raise ScoringError(
                "Butteraugli ran successfully, but no numeric score could be parsed from its output.\n"
                f"Command: {render_command(cmd)}\n{output}"
            )
        return score

    def _extract_first_float(self, text: str) -> float | None:
        match = self.FLOAT_RE.search(text)
        if not match:
            return None
        return float(match.group(1))