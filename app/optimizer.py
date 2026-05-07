from __future__ import annotations

import math
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Iterable, Optional

from PIL import Image

from .encoders import EncodeResult, EncoderRunner, OperationCancelled, compute_worker_slots
from .image_io import ImageNormalizer
from .models import CandidateResult, ToolPaths
from .scoring import ButteraugliScorer

LogFn = Callable[[str], None]
EtaFn = Callable[[float | None], None]
ProgressFn = Callable[[int], None]


class OptimizationError(RuntimeError):
    pass


@dataclass(slots=True)
class BranchEstimate:
    jpegli_ops: int = 0
    mozjpeg_ops: int = 0
    score_ops: int = 0
    finished: bool = False


@dataclass(slots=True)
class RollingAverage:
    fallback_seconds: float
    total_seconds: float = 0.0
    samples: int = 0

    @property
    def average(self) -> float:
        if self.samples <= 0:
            return self.fallback_seconds
        return self.total_seconds / self.samples

    def add(self, seconds: float) -> None:
        if seconds > 0:
            self.total_seconds += seconds
            self.samples += 1


class ParallelEtaEstimator:
    def __init__(
        self,
        max_workers: int,
        eta_callback: EtaFn | None,
        progress_callback: ProgressFn | None,
    ):
        self.max_workers = max(1, max_workers)
        self.eta_callback = eta_callback
        self.progress_callback = progress_callback
        self._lock = Lock()
        self._start_ts = time.monotonic()

        self._jpegli_avg = RollingAverage(6.5)
        self._mozjpeg_avg = RollingAverage(2.5)
        self._score_avg = RollingAverage(1.25)

        self._branches: dict[str, BranchEstimate] = {}
        self._last_emit_ts = 0.0
        self._last_eta_value: float | None = None
        self._last_progress_value: int | None = None

    def register_branch(
        self,
        branch_id: str,
        *,
        jpegli_ops: int = 0,
        mozjpeg_ops: int = 0,
        score_ops: int = 0,
    ) -> None:
        with self._lock:
            self._branches[branch_id] = BranchEstimate(
                jpegli_ops=max(0, jpegli_ops),
                mozjpeg_ops=max(0, mozjpeg_ops),
                score_ops=max(0, score_ops),
                finished=False,
            )
            self._emit_locked(force=True)

    def update_branch(
        self,
        branch_id: str,
        *,
        jpegli_ops: int | None = None,
        mozjpeg_ops: int | None = None,
        score_ops: int | None = None,
        finished: bool | None = None,
    ) -> None:
        with self._lock:
            branch = self._branches.setdefault(branch_id, BranchEstimate())
            if jpegli_ops is not None:
                branch.jpegli_ops = max(0, jpegli_ops)
            if mozjpeg_ops is not None:
                branch.mozjpeg_ops = max(0, mozjpeg_ops)
            if score_ops is not None:
                branch.score_ops = max(0, score_ops)
            if finished is not None:
                branch.finished = finished
            self._emit_locked()

    def record_duration(self, op_type: str, seconds: float) -> None:
        with self._lock:
            if op_type == "jpegli":
                self._jpegli_avg.add(seconds)
            elif op_type == "mozjpeg":
                self._mozjpeg_avg.add(seconds)
            elif op_type == "score":
                self._score_avg.add(seconds)
            self._emit_locked()

    def finish_branch(self, branch_id: str) -> None:
        with self._lock:
            branch = self._branches.setdefault(branch_id, BranchEstimate())
            branch.jpegli_ops = 0
            branch.mozjpeg_ops = 0
            branch.score_ops = 0
            branch.finished = True
            self._emit_locked(force=True)

    def _estimate_remaining_locked(self) -> float | None:
        unfinished = [b for b in self._branches.values() if not b.finished]
        if not unfinished:
            return 0.0

        per_branch_seconds: list[float] = []
        total_seconds = 0.0

        for branch in unfinished:
            seconds = (
                branch.jpegli_ops * self._jpegli_avg.average
                + branch.mozjpeg_ops * self._mozjpeg_avg.average
                + branch.score_ops * self._score_avg.average
            )
            per_branch_seconds.append(seconds)
            total_seconds += seconds

        parallelism = min(self.max_workers, len(unfinished))
        wall_estimate = max(max(per_branch_seconds, default=0.0), total_seconds / max(1, parallelism))
        return max(0.0, wall_estimate)

    def _progress_percent_locked(self, remaining_seconds: float | None) -> int:
        if remaining_seconds is None:
            return 0

        elapsed = max(0.0, time.monotonic() - self._start_ts)
        if remaining_seconds <= 0.05:
            return 100

        total_estimate = elapsed + remaining_seconds
        if total_estimate <= 0:
            return 0

        percent = int(round(100.0 * elapsed / total_estimate))
        return max(0, min(99, percent))

    def _emit_locked(self, force: bool = False) -> None:
        eta_value = self._estimate_remaining_locked()
        progress_value = self._progress_percent_locked(eta_value)
        now = time.monotonic()

        should_emit = force
        if not should_emit:
            if self._last_eta_value is None or eta_value is None:
                should_emit = True
            elif abs((eta_value or 0.0) - (self._last_eta_value or 0.0)) >= 2.0:
                should_emit = True
            elif self._last_progress_value is None or progress_value != self._last_progress_value:
                should_emit = True
            elif now - self._last_emit_ts >= 0.5:
                should_emit = True

        if should_emit:
            self._last_emit_ts = now
            self._last_eta_value = eta_value
            self._last_progress_value = progress_value

            if self.eta_callback is not None:
                self.eta_callback(eta_value)
            if self.progress_callback is not None:
                self.progress_callback(progress_value)


class PillowPerformanceOptimizer:
    def __init__(self, tools: ToolPaths, cancel_event: Event | None = None):
        self.tools = tools
        self.cancel_event = cancel_event

    def _check_cancel(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise OperationCancelled("Compression cancelled.")

    def optimize_image(
        self,
        source_path: Path,
        destination_path: Path,
        target_bytes: int,
        log: LogFn,
        eta_callback: EtaFn | None = None,
        progress_callback: ProgressFn | None = None,
    ) -> CandidateResult:
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        if progress_callback is not None:
            progress_callback(0)
        if eta_callback is not None:
            eta_callback(None)

        start_ts = time.monotonic()
        self._check_cancel()

        with tempfile.TemporaryDirectory(prefix="pillow_optimizer_") as temp_root:
            temp_output = Path(temp_root) / f"{source_path.stem}.jpg"

            with Image.open(source_path) as image:
                rgb = image.convert("RGB")

                quality = 99
                last_size = None

                while quality >= 1:
                    self._check_cancel()

                    rgb.save(
                        temp_output,
                        "JPEG",
                        optimize=True,
                        quality=quality,
                        subsampling="4:4:4",
                    )
                    size_bytes = temp_output.stat().st_size
                    last_size = size_bytes

                    log(
                        f"[{source_path.name}] Pillow q={quality} -> "
                        f"{size_bytes / 1_000_000:.3f} MB"
                    )

                    if progress_callback is not None:
                        tested = 100 - quality
                        percent = int(round((tested / 98) * 100))
                        progress_callback(max(1, min(99, percent)))

                    if eta_callback is not None:
                        elapsed = max(0.001, time.monotonic() - start_ts)
                        steps_done = (100 - quality) + 1
                        avg_per_step = elapsed / steps_done
                        remaining_steps = max(0, quality - 1)
                        eta_callback(avg_per_step * remaining_steps)

                    if size_bytes <= target_bytes:
                        self._check_cancel()
                        shutil.copy2(temp_output, destination_path)

                        if progress_callback is not None:
                            progress_callback(100)
                        if eta_callback is not None:
                            eta_callback(0.0)

                        return CandidateResult(
                            encoder="pillow",
                            subsampling="444",
                            progressive=None,
                            quality_label=f"quality={quality}",
                            output_path=destination_path,
                            size_bytes=size_bytes,
                            butteraugli_score=-1.0,
                            command=f"Pillow JPEG optimize=True quality={quality} subsampling=4:4:4",
                        )

                    quality -= 1

        raise OptimizationError(
            f"Could not compress '{source_path.name}' under {target_bytes / 1_000_000:.3f} MB. "
            f"Last size was {0.0 if last_size is None else last_size / 1_000_000:.3f} MB."
        )


class JpegOptimizer:
    def __init__(self, tools: ToolPaths, cancel_event: Event | None = None):
        self.tools = tools
        self.cancel_event = cancel_event
        self.normalizer = ImageNormalizer()
        self.encoder = EncoderRunner(tools, cancel_event=cancel_event)
        self.scorer = ButteraugliScorer(tools, cancel_event=cancel_event)
        self.max_parallel_jobs = min(4, compute_worker_slots())
        self._log_lock = Lock()

    def _safe_log(self, log: LogFn, message: str) -> None:
        with self._log_lock:
            log(message)

    def _check_cancel(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise OperationCancelled("Compression cancelled.")

    def optimize_image(
        self,
        source_path: Path,
        destination_path: Path,
        target_bytes: int,
        log: LogFn,
        eta_callback: EtaFn | None = None,
        progress_callback: ProgressFn | None = None,
    ) -> CandidateResult:
        self._check_cancel()

        with tempfile.TemporaryDirectory(prefix="jpeg_optimizer_") as temp_root:
            temp_dir = Path(temp_root)
            normalized = self.normalizer.normalize(source_path, temp_dir)

            self._safe_log(
                log,
                f"Normalized {source_path.name} to {normalized.width}x{normalized.height} RGB working files.",
            )
            self._safe_log(log, f"[{source_path.name}] Jpegli input: {normalized.png_path}")
            self._safe_log(log, f"[{source_path.name}] MozJPEG input: {normalized.bmp_path}")
            self._safe_log(
                log,
                f"[{source_path.name}] Running parallel branch search with up to {self.max_parallel_jobs} workers...",
            )

            if not normalized.png_path.exists():
                raise OptimizationError(f"Missing normalized PNG working file for '{source_path.name}'.")
            if not normalized.bmp_path.exists():
                raise OptimizationError(f"Missing normalized BMP working file for '{source_path.name}'.")

            eta = ParallelEtaEstimator(self.max_parallel_jobs, eta_callback, progress_callback)
            candidates: list[CandidateResult] = []

            executor = ThreadPoolExecutor(
                max_workers=self.max_parallel_jobs,
                thread_name_prefix="jpeg_optimizer_branch",
            )
            try:
                jobs: list[tuple[str, object]] = []

                for subsampling in ("444", "422", "420"):
                    self._check_cancel()
                    branch_id = f"jpegli-{subsampling}"
                    eta.register_branch(branch_id, jpegli_ops=15 + 10 + 9, score_ops=0)
                    jobs.append(
                        (
                            f"jpegli {subsampling}",
                            executor.submit(
                                self._search_jpegli,
                                normalized.png_path,
                                normalized.png_path,
                                temp_dir,
                                target_bytes,
                                subsampling,
                                log,
                                eta,
                                branch_id,
                            ),
                        )
                    )

                for subsampling in ("444", "422", "420"):
                    for progressive in (True, False):
                        self._check_cancel()
                        label = "progressive" if progressive else "baseline"
                        branch_id = f"mozjpeg-{subsampling}-{label}"
                        eta.register_branch(branch_id, mozjpeg_ops=7 + 8, score_ops=0)
                        jobs.append(
                            (
                                f"mozjpeg {subsampling} {label}",
                                executor.submit(
                                    self._search_mozjpeg,
                                    normalized.bmp_path,
                                    normalized.png_path,
                                    temp_dir,
                                    target_bytes,
                                    subsampling,
                                    progressive,
                                    log,
                                    eta,
                                    branch_id,
                                ),
                            )
                        )

                future_to_label = {future: label for label, future in jobs}
                for future in as_completed(future_to_label):
                    self._check_cancel()
                    label = future_to_label[future]
                    try:
                        branch_candidates = future.result()
                    except OperationCancelled:
                        continue
                    except Exception as exc:
                        self._safe_log(log, f"[{source_path.name}] Branch {label} failed: {exc}")
                        continue
                    candidates.extend(branch_candidates)
                    self._safe_log(
                        log,
                        f"[{source_path.name}] Branch {label} finished with {len(branch_candidates)} feasible candidates.",
                    )
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            self._check_cancel()

            if not candidates:
                raise OptimizationError(
                    f"No candidate fit under the file-size budget for '{source_path.name}'."
                )

            self._safe_log(log, f"[{source_path.name}] Scored {len(candidates)} feasible candidates. Selecting winner...")
            winner = min(
                candidates,
                key=lambda c: (c.butteraugli_score, abs(target_bytes - c.size_bytes), c.size_bytes),
            )

            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(winner.output_path, destination_path)

            self._safe_log(
                log,
                f"[{source_path.name}] Winner: {winner.encoder} {winner.subsampling} {winner.quality_label}, "
                f"Butteraugli={winner.butteraugli_score:.6f}, size={winner.size_bytes / 1_000_000:.3f} MB",
            )

            return CandidateResult(
                encoder=winner.encoder,
                subsampling=winner.subsampling,
                progressive=winner.progressive,
                quality_label=winner.quality_label,
                output_path=destination_path,
                size_bytes=winner.size_bytes,
                butteraugli_score=winner.butteraugli_score,
                command=winner.command,
            )

    def _search_jpegli(
        self,
        source_png: Path,
        reference_png: Path,
        temp_dir: Path,
        target_bytes: int,
        subsampling: str,
        log: LogFn,
        eta: ParallelEtaEstimator,
        branch_id: str,
    ) -> list[CandidateResult]:
        self._check_cancel()

        coarse_distances = [
            0.08, 0.12, 0.16, 0.22, 0.30, 0.40, 0.55, 0.75,
            1.0, 1.35, 1.8, 2.4, 3.2, 4.5, 6.0,
        ]
        tested: dict[float, Optional[EncodeResult]] = {}

        def encode(distance: float) -> Optional[EncodeResult]:
            self._check_cancel()
            key = round(distance, 6)
            if key in tested:
                return tested[key]

            output = temp_dir / f"jpegli_{subsampling}_{key:.6f}.jpg"

            start = time.monotonic()
            try:
                result = self.encoder.encode_with_jpegli(
                    source_png,
                    output,
                    distance=key,
                    subsampling=subsampling,
                )
            except Exception as exc:
                self._safe_log(log, f"    Jpegli {subsampling} d={key:.6f} failed: {exc}")
                tested[key] = None
                return None
            finally:
                eta.record_duration("jpegli", time.monotonic() - start)

            tested[key] = result
            return result

        first_fit: Optional[float] = None
        previous_oversize: Optional[float] = None

        self._safe_log(log, f"[{source_png.stem}] Searching Jpegli candidates for {subsampling}...")

        for idx, distance in enumerate(coarse_distances):
            self._check_cancel()
            result = encode(distance)
            remaining_coarse = len(coarse_distances) - idx - 1
            eta.update_branch(branch_id, jpegli_ops=remaining_coarse + 10 + 9)

            if result is None:
                continue

            self._safe_log(
                log,
                f"    Jpegli {subsampling} d={distance:.3f} -> {result.size_bytes / 1_000_000:.3f} MB",
            )

            if result.size_bytes <= target_bytes:
                first_fit = distance
                break

            previous_oversize = distance

        if first_fit is None:
            eta.finish_branch(branch_id)
            return []

        candidates_to_score: list[EncodeResult] = []
        first_result = encode(first_fit)
        if first_result is not None and first_result.size_bytes <= target_bytes:
            candidates_to_score.append(first_result)

        lower = previous_oversize if previous_oversize is not None else max(0.02, first_fit / 2.0)
        upper = first_fit

        refine_done = 0
        for _ in range(10):
            self._check_cancel()
            probe = round((lower + upper) / 2.0, 6)
            if math.isclose(probe, lower, rel_tol=0.0, abs_tol=1e-6) or math.isclose(
                probe, upper, rel_tol=0.0, abs_tol=1e-6
            ):
                break

            result = encode(probe)
            refine_done += 1
            eta.update_branch(branch_id, jpegli_ops=(10 - refine_done) + 9)

            if result is None:
                break

            self._safe_log(
                log,
                f"    Jpegli refine {subsampling} d={probe:.6f} -> {result.size_bytes / 1_000_000:.3f} MB",
            )

            if result.size_bytes <= target_bytes:
                upper = probe
                candidates_to_score.append(result)
            else:
                lower = probe

        local_grid = self._dense_float_grid(max(0.02, upper * 0.75), max(0.02, upper * 1.25), 9)
        uncached_grid = [distance for distance in local_grid if round(distance, 6) not in tested]
        eta.update_branch(branch_id, jpegli_ops=len(uncached_grid), score_ops=0)

        for index, distance in enumerate(local_grid):
            self._check_cancel()
            was_cached = round(distance, 6) in tested
            result = encode(distance)
            if not was_cached:
                remaining_uncached = sum(1 for item in local_grid[index + 1:] if round(item, 6) not in tested)
                eta.update_branch(branch_id, jpegli_ops=remaining_uncached)

            if result is not None and result.size_bytes <= target_bytes:
                candidates_to_score.append(result)

        return self._score_unique_candidates(
            reference_png=reference_png,
            encode_results=candidates_to_score,
            encoder_name="jpegli",
            subsampling=subsampling,
            progressive=None,
            quality_formatter=lambda path: f"distance={self._quality_from_name(path):.6f}",
            log=log,
            eta=eta,
            branch_id=branch_id,
        )

    def _search_mozjpeg(
        self,
        source_bmp: Path,
        reference_png: Path,
        temp_dir: Path,
        target_bytes: int,
        subsampling: str,
        progressive: bool,
        log: LogFn,
        eta: ParallelEtaEstimator,
        branch_id: str,
    ) -> list[CandidateResult]:
        self._check_cancel()
        tested: dict[int, Optional[EncodeResult]] = {}

        def encode(quality: int) -> Optional[EncodeResult]:
            self._check_cancel()
            quality = max(1, min(100, quality))
            if quality in tested:
                return tested[quality]

            flavor = "prog" if progressive else "base"
            output = temp_dir / f"mozjpeg_{subsampling}_{flavor}_q{quality:03d}.jpg"

            start = time.monotonic()
            try:
                result = self.encoder.encode_with_mozjpeg(
                    source_bmp,
                    output,
                    quality=quality,
                    subsampling=subsampling,
                    progressive=progressive,
                )
            except Exception as exc:
                label = "progressive" if progressive else "baseline"
                self._safe_log(log, f"    MozJPEG {subsampling} {label} q={quality} failed: {exc}")
                tested[quality] = None
                return None
            finally:
                eta.record_duration("mozjpeg", time.monotonic() - start)

            tested[quality] = result
            return result

        low = 1
        high = 100
        best_quality: Optional[int] = None

        self._safe_log(
            log,
            f"[{source_bmp.stem}] Searching MozJPEG candidates for {subsampling}, "
            f"{'progressive' if progressive else 'baseline'}...",
        )

        while low <= high:
            self._check_cancel()
            mid = (low + high) // 2
            result = encode(mid)

            if result is None:
                high = mid - 1
                search_span = max(0, high - low + 1)
                search_iters_remaining = 0 if search_span <= 0 else (search_span - 1).bit_length()
                eta.update_branch(branch_id, mozjpeg_ops=search_iters_remaining + 8)
                continue

            self._safe_log(
                log,
                f"    MozJPEG {subsampling} {'progressive' if progressive else 'baseline'} q={mid} -> "
                f"{result.size_bytes / 1_000_000:.3f} MB",
            )

            if result.size_bytes <= target_bytes:
                best_quality = mid
                low = mid + 1
            else:
                high = mid - 1

            search_span = max(0, high - low + 1)
            search_iters_remaining = 0 if search_span <= 0 else (search_span - 1).bit_length()
            eta.update_branch(branch_id, mozjpeg_ops=search_iters_remaining + 8)

        if best_quality is None:
            eta.finish_branch(branch_id)
            return []

        qualities = sorted(set(range(max(1, best_quality - 5), min(100, best_quality + 2) + 1)))
        uncached_qualities = [q for q in qualities if q not in tested]
        eta.update_branch(branch_id, mozjpeg_ops=len(uncached_qualities), score_ops=0)

        candidates_to_score: list[EncodeResult] = []
        for q in qualities:
            self._check_cancel()
            result = encode(q)
            if q in uncached_qualities:
                remaining_uncached = sum(1 for item in uncached_qualities if item > q)
                eta.update_branch(branch_id, mozjpeg_ops=remaining_uncached)

            if result is not None and result.size_bytes <= target_bytes:
                candidates_to_score.append(result)

        return self._score_unique_candidates(
            reference_png=reference_png,
            encode_results=candidates_to_score,
            encoder_name="mozjpeg",
            subsampling=subsampling,
            progressive=progressive,
            quality_formatter=lambda path: f"quality={int(self._quality_from_name(path))}",
            log=log,
            eta=eta,
            branch_id=branch_id,
        )

    def _score_unique_candidates(
        self,
        *,
        reference_png: Path,
        encode_results: Iterable[EncodeResult],
        encoder_name: str,
        subsampling: str,
        progressive: Optional[bool],
        quality_formatter,
        log: LogFn,
        eta: ParallelEtaEstimator,
        branch_id: str,
    ) -> list[CandidateResult]:
        self._check_cancel()

        unique: dict[Path, EncodeResult] = {item.output_path: item for item in encode_results}
        unique_results = list(unique.values())

        eta.update_branch(branch_id, jpegli_ops=0, mozjpeg_ops=0, score_ops=len(unique_results))

        scored: list[CandidateResult] = []
        total_scores = len(unique_results)

        for index, result in enumerate(unique_results, start=1):
            self._check_cancel()
            start = time.monotonic()
            try:
                score = self.scorer.score(reference_png, result.output_path)
            except Exception as exc:
                self._safe_log(log, f"    Butteraugli scoring failed for {result.output_path.name}: {exc}")
                eta.record_duration("score", time.monotonic() - start)
                eta.update_branch(branch_id, score_ops=total_scores - index)
                continue

            eta.record_duration("score", time.monotonic() - start)
            eta.update_branch(branch_id, score_ops=total_scores - index)

            scored.append(
                CandidateResult(
                    encoder=encoder_name,
                    subsampling=subsampling,
                    progressive=progressive,
                    quality_label=quality_formatter(result.output_path),
                    output_path=result.output_path,
                    size_bytes=result.size_bytes,
                    butteraugli_score=score,
                    command=result.command,
                )
            )

        eta.finish_branch(branch_id)
        return scored

    @staticmethod
    def _dense_float_grid(start: float, stop: float, count: int) -> list[float]:
        if count <= 1:
            return [round(start, 6)]
        step = (stop - start) / (count - 1)
        return [round(start + idx * step, 6) for idx in range(count)]

    @staticmethod
    def _quality_from_name(path: Path) -> float:
        name = path.stem
        if "distance" in name:
            raise ValueError("Unexpected filename format.")
        if "jpegli" in name:
            return float(name.split("_")[-1])
        if "q" in name:
            return float(name.rsplit("q", 1)[-1])
        raise ValueError(f"Unable to infer quality label from {path.name}")