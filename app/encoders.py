from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Sequence

from .models import ToolPaths


class EncoderError(RuntimeError):
    pass


class OperationCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class EncodeResult:
    output_path: Path
    size_bytes: int
    command: str


def compute_worker_slots() -> int:
    total = os.cpu_count() or 2
    if total <= 2:
        return 1
    return max(1, total - 2)


def render_command(cmd: Sequence[str]) -> str:
    return subprocess.list2cmdline(list(cmd))


def _set_affinity_windows(pid: int, logical_cpus: int) -> None:
    logical_cpus = max(1, logical_cpus)
    logical_cpus = min(logical_cpus, 63)

    mask = (1 << logical_cpus) - 1

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    set_affinity = kernel32.SetProcessAffinityMask
    close_handle = kernel32.CloseHandle

    PROCESS_SET_INFORMATION = 0x0200
    PROCESS_QUERY_INFORMATION = 0x0400

    handle = open_process(PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        return

    try:
        set_affinity(handle, mask)
    finally:
        close_handle(handle)


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    try:
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                startupinfo=startupinfo,
            )
        else:
            proc.terminate()
    except Exception:
        pass

    try:
        proc.wait(timeout=1.0)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_external(
    cmd: Sequence[str],
    *,
    cancel_event: Event | None = None,
    poll_interval: float = 0.2,
) -> subprocess.CompletedProcess[str]:
    creationflags = 0
    startupinfo = None

    if sys.platform == "win32":
        creationflags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )

    if sys.platform == "win32":
        _set_affinity_windows(proc.pid, compute_worker_slots())

    while True:
        if cancel_event is not None and cancel_event.is_set():
            _terminate_process(proc)
            try:
                stdout, stderr = proc.communicate(timeout=0.2)
            except Exception:
                stdout, stderr = "", ""
            raise OperationCancelled(
                "Operation cancelled.\n"
                f"Command: {render_command(cmd)}\n"
                f"{stdout}{stderr}".strip()
            )

        try:
            stdout, stderr = proc.communicate(timeout=poll_interval)
            return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue


class EncoderRunner:
    def __init__(self, tools: ToolPaths, cancel_event: Event | None = None):
        self.tools = tools
        self.cancel_event = cancel_event
        self.max_worker_slots = compute_worker_slots()

    def encode_with_jpegli(
        self,
        source_image: Path,
        output_jpg: Path,
        *,
        distance: float,
        subsampling: str,
    ) -> EncodeResult:
        subsampling_arg = self._jpegli_subsampling_arg(subsampling)
        cmd = [
            str(self.tools.jpegli),
            str(source_image),
            str(output_jpg),
            "-d",
            f"{distance:.6f}",
            f"--chroma_subsampling={subsampling_arg}",
        ]
        self._run(cmd)
        return EncodeResult(
            output_path=output_jpg,
            size_bytes=output_jpg.stat().st_size,
            command=render_command(cmd),
        )

    def encode_with_mozjpeg(
        self,
        source_bmp: Path,
        output_jpg: Path,
        *,
        quality: int,
        subsampling: str,
        progressive: bool,
    ) -> EncodeResult:
        cmd = [
            str(self.tools.mozjpeg),
            "-outfile",
            str(output_jpg),
            "-quality",
            str(quality),
            "-optimize",
            "-sample",
            self._mozjpeg_sample_arg(subsampling),
        ]
        if progressive:
            cmd.append("-progressive")
        cmd.append(str(source_bmp))
        self._run(cmd)
        return EncodeResult(
            output_path=output_jpg,
            size_bytes=output_jpg.stat().st_size,
            command=render_command(cmd),
        )

    @staticmethod
    def _jpegli_subsampling_arg(subsampling: str) -> str:
        mapping = {
            "444": "444",
            "422": "422",
            "420": "420",
        }
        try:
            return mapping[subsampling]
        except KeyError as exc:
            raise EncoderError(f"Unsupported Jpegli subsampling value: {subsampling}") from exc

    @staticmethod
    def _mozjpeg_sample_arg(subsampling: str) -> str:
        mapping = {
            "444": "1x1",
            "422": "2x1",
            "420": "2x2",
        }
        try:
            return mapping[subsampling]
        except KeyError as exc:
            raise EncoderError(f"Unsupported MozJPEG subsampling value: {subsampling}") from exc

    def _run(self, cmd: Sequence[str]) -> None:
        completed = run_external(cmd, cancel_event=self.cancel_event)
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            combined = "\n".join(part for part in (stdout, stderr) if part)
            raise EncoderError(
                f"External encoder failed with exit code {completed.returncode}.\n"
                f"Command: {render_command(cmd)}\n{combined}"
            )