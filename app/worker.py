from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal

from .encoders import OperationCancelled, compute_worker_slots
from .models import CompressionSummary
from .optimizer import JpegOptimizer, PillowPerformanceOptimizer
from .tooling import SUPPORTED_EXTENSIONS, discover_tool_paths


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class CompressionWorker(QThread):
    log = Signal(str)
    progress = Signal(int, int)
    image_progress = Signal(int)
    file_started = Signal(str)
    file_finished = Signal(str, str, str, str, str, str)
    activity_changed = Signal(str)
    row_activity_changed = Signal(str, str)
    eta_changed = Signal(str)
    run_finished = Signal(object)
    fatal_error = Signal(str)

    def __init__(
        self,
        source_dir: Path,
        destination_dir: Path,
        max_size_mb: float,
        mode: str = "performance",
    ):
        super().__init__()
        self.source_dir = source_dir
        self.destination_dir = destination_dir
        self.max_size_mb = max_size_mb
        self.mode = mode
        self._cancel_requested = False
        self._cancel_event = Event()
        self.max_worker_slots = compute_worker_slots()

        self._durations: list[float] = []
        self._current_index = 0
        self._total_files = 0
        self._latest_current_eta: float | None = None
        self._current_activity: str = "Getting image ready"

    def cancel(self) -> None:
        self._cancel_requested = True
        self._cancel_event.set()
        self.log.emit("Stopping now...")
        self.activity_changed.emit("Stopping now...")

    def run(self) -> None:
        try:
            tools = discover_tool_paths()
            self.log.emit(f"Jpegli tool: {tools.jpegli}")
            self.log.emit(f"MozJPEG tool: {tools.mozjpeg}")
            self.log.emit(f"Butteraugli tool: {tools.butteraugli}")
            if self.mode == "quality":
                optimizer = JpegOptimizer(tools, cancel_event=self._cancel_event)
            else:
                optimizer = PillowPerformanceOptimizer(tools, cancel_event=self._cancel_event)
        except Exception as exc:
            self.fatal_error.emit(str(exc))
            return

        files = [
            path
            for path in sorted(self.source_dir.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        total = len(files)
        self._total_files = total

        if total == 0:
            self.fatal_error.emit("No supported image files were found in the selected source folder.")
            return

        compressed = 0
        skipped = 0
        failed = 0
        target_bytes = int(self.max_size_mb * 1_000_000)

        self.log.emit(
            f"Found {total} image(s). Max size: {self.max_size_mb:.3f} MB. "
            f"Mode: {'Quality' if self.mode == 'quality' else 'Performance'}."
        )
        self.activity_changed.emit("Ready")
        self.eta_changed.emit("Time left: estimating...")
        self.image_progress.emit(0)

        for index, source_path in enumerate(files, start=1):
            if self._cancel_event.is_set():
                break

            file_name = source_path.name
            self._current_index = index
            self._latest_current_eta = None
            self._current_activity = "Getting image ready"

            self.file_started.emit(file_name)
            self.progress.emit(index - 1, total)
            self.image_progress.emit(0)
            self.activity_changed.emit(f"{file_name} - Getting image ready")
            self.row_activity_changed.emit(file_name, "Getting image ready")
            self.eta_changed.emit(self._compose_eta_label(None))
            self.log.emit(f"Starting {file_name}")

            last_stage_logged: str | None = None
            displayed_eta: float | None = None
            last_image_progress = 0

            def log_callback(message: str) -> None:
                nonlocal last_stage_logged

                stage = self._stage_from_message(file_name, message)
                if stage:
                    self._current_activity = stage
                    self.activity_changed.emit(f"{file_name} - {stage}")
                    self.row_activity_changed.emit(
                        file_name,
                        self._compose_row_activity(stage, self._latest_current_eta),
                    )

                    if stage != last_stage_logged:
                        self.log.emit(f"{file_name}: {stage}")
                        last_stage_logged = stage

            def eta_callback(current_eta: float | None) -> None:
                nonlocal displayed_eta
                if current_eta is None:
                    displayed_eta = None
                else:
                    current_eta = max(0.0, current_eta)
                    if displayed_eta is None:
                        displayed_eta = current_eta
                    elif current_eta <= displayed_eta:
                        displayed_eta = current_eta
                    else:
                        max_increase = max(2.0, displayed_eta * 0.12)
                        displayed_eta = min(current_eta, displayed_eta + max_increase)

                self._latest_current_eta = displayed_eta
                self.eta_changed.emit(self._compose_eta_label(displayed_eta))
                self.row_activity_changed.emit(
                    file_name,
                    self._compose_row_activity(self._current_activity, displayed_eta),
                )

            def progress_callback(current_percent: int) -> None:
                nonlocal last_image_progress
                current_percent = max(0, min(100, int(current_percent)))
                last_image_progress = max(last_image_progress, current_percent)
                self.image_progress.emit(last_image_progress)

            file_start_ts = time.monotonic()

            source_size_bytes = source_path.stat().st_size
            if source_size_bytes <= target_bytes:
                elapsed_text = _format_duration(time.monotonic() - file_start_ts)
                skipped += 1
                self.image_progress.emit(100)

                self.file_finished.emit(
                    file_name,
                    "Skipped",
                    elapsed_text,
                    f"{source_size_bytes / 1_000_000:.3f} MB",
                    "Original kept",
                    "No compression needed",
                )
                self.activity_changed.emit(f"{file_name} - Skipped")
                self.log.emit(f"Skipped {file_name}: already under size limit")

                self._durations.append(time.monotonic() - file_start_ts)
                self.progress.emit(index, total)
                self.eta_changed.emit(self._compose_eta_label(None))
                continue

            try:
                destination_path = self._build_destination_path(source_path)
                result = optimizer.optimize_image(
                    source_path=source_path,
                    destination_path=destination_path,
                    target_bytes=target_bytes,
                    log=log_callback,
                    eta_callback=eta_callback,
                    progress_callback=progress_callback,
                )
                elapsed_text = _format_duration(time.monotonic() - file_start_ts)
                compressed += 1
                self.image_progress.emit(100)

                quality_text = (
                    self._friendly_quality_label(result.butteraugli_score)
                    if result.butteraugli_score >= 0
                    else "Fast"
                )

                details_text = (
                    "Best version saved"
                    if self.mode == "quality"
                    else "Fast version saved"
                )

                self.file_finished.emit(
                    file_name,
                    "Done",
                    elapsed_text,
                    f"{result.size_bytes / 1_000_000:.3f} MB",
                    quality_text,
                    details_text,
                )
                self.activity_changed.emit(f"{file_name} - Done")
                self.log.emit(f"Finished {file_name} in {elapsed_text}")

            except OperationCancelled:
                elapsed_text = _format_duration(time.monotonic() - file_start_ts)
                self.image_progress.emit(0)
                self.file_finished.emit(
                    file_name,
                    "Cancelled",
                    elapsed_text,
                    "-",
                    "-",
                    "Stopped by user",
                )
                self.activity_changed.emit(f"{file_name} - Cancelled")
                self.log.emit(f"Cancelled {file_name}")
                break

            except Exception as exc:
                elapsed_text = _format_duration(time.monotonic() - file_start_ts)
                failed += 1
                self.image_progress.emit(100)
                self.file_finished.emit(
                    file_name,
                    "Failed",
                    elapsed_text,
                    "-",
                    "-",
                    "Could not process this image",
                )
                self.log.emit(f"Could not process {file_name}")
                self.log.emit(f"{file_name} error: {exc}")
                self.activity_changed.emit(f"{file_name} - Failed")

            self._durations.append(time.monotonic() - file_start_ts)
            self.progress.emit(index, total)
            self.eta_changed.emit(self._compose_eta_label(None))

        summary = CompressionSummary(
            total_files=total,
            compressed_files=compressed,
            skipped_files=skipped,
            failed_files=failed,
            cancelled=self._cancel_requested or self._cancel_event.is_set(),
        )
        self.run_finished.emit(summary)

    def _compose_row_activity(self, activity: str, current_eta: float | None) -> str:
        if current_eta is None:
            return activity
        return f"{activity} - about {_format_duration(current_eta)} left"

    def _compose_eta_label(self, current_image_eta: float | None) -> str:
        parts: list[str] = []

        if current_image_eta is not None:
            parts.append(f"This image: about {_format_duration(current_image_eta)}")
        else:
            parts.append("This image: estimating...")

        remaining_after_current = max(0, self._total_files - self._current_index)

        if self._durations and remaining_after_current > 0:
            avg = sum(self._durations) / len(self._durations)
            run_eta = (current_image_eta or 0.0) + (avg * remaining_after_current)
            parts.append(f"Remaining: about {_format_duration(run_eta)}")
        elif remaining_after_current > 0 and current_image_eta is not None:
            projected = current_image_eta * (remaining_after_current + 1)
            parts.append(f"Remaining: about {_format_duration(projected)}")

        return " | ".join(parts)

    @staticmethod
    def _friendly_quality_label(score: float) -> str:
        if score <= 1.2:
            return "Excellent"
        if score <= 1.8:
            return "Very good"
        if score <= 2.6:
            return "Good"
        if score <= 3.5:
            return "Fair"
        return "Lower"

    def _stage_from_message(self, filename: str, raw_message: str) -> str | None:
        text = raw_message.strip()
        prefix = f"[{filename}] "
        if text.startswith(prefix):
            text = text[len(prefix):]

        if self.mode == "performance":
            if text.startswith("Pillow q="):
                return "Compressing image"
            return None

        if text.startswith("Normalized "):
            return "Getting image ready"
        if text.startswith("Jpegli input:"):
            return "Getting image ready"
        if text.startswith("MozJPEG input:"):
            return "Getting image ready"
        if text.startswith("Running parallel branch search with up to "):
            return "Testing best settings"
        if text.startswith("Searching Jpegli candidates for "):
            return "Testing best settings"
        if text.startswith("Searching MozJPEG candidates for "):
            return "Testing best settings"
        if text.startswith("Jpegli refine "):
            return "Fine-tuning file size"
        if text.startswith("Jpegli "):
            return "Testing best settings"
        if text.startswith("MozJPEG "):
            return "Testing best settings"
        if text.startswith("Scored "):
            return "Checking image quality"
        if text.startswith("Winner:"):
            return "Saving final image"
        return None

    def _build_destination_path(self, source_path: Path) -> Path:
        self.destination_dir.mkdir(parents=True, exist_ok=True)
        candidate = self.destination_dir / f"{source_path.stem}.jpg"
        if not candidate.exists():
            return candidate

        index = 2
        while True:
            versioned = self.destination_dir / f"{source_path.stem}__{index}.jpg"
            if not versioned.exists():
                return versioned
            index += 1


