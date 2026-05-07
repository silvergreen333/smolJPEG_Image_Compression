from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from .models import ToolPaths


class ToolDiscoveryError(RuntimeError):
    pass


APP_NAME = "smolJPEG Image Compression"
SUPPORTED_EXTENSIONS = {
    ".bmp",
    ".dib",
    ".jpg",
    ".jpeg",
    ".jpe",
    ".jfif",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def app_root() -> Path:
    # Works for both source runs and Nuitka onefile data extraction.
    return Path(__file__).resolve().parent.parent


def tools_root() -> Path:
    return app_root() / "tools"


def _program_dir() -> Path:
    try:
        return Path(sys.argv[0]).resolve().parent
    except Exception:
        return app_root()


def _compiled_containing_dir() -> Path | None:
    # Nuitka exposes __compiled__.containing_dir in compiled builds.
    compiled = globals().get("__compiled__")
    if compiled is None:
        return None
    containing_dir = getattr(compiled, "containing_dir", None)
    if not containing_dir:
        return None
    try:
        return Path(str(containing_dir)).resolve()
    except Exception:
        return None


def _candidate_tools_roots() -> list[Path]:
    roots: list[Path] = []

    compiled_dir = _compiled_containing_dir()
    if compiled_dir is not None:
        roots.append(compiled_dir / "tools")

    roots.append(_program_dir() / "tools")
    roots.append(tools_root())

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _tool_candidate_score(path: Path) -> int:
    text = path.as_posix().lower()
    score = 0
    if "/runtime/" in text:
        score += 60
    if "/build/" in text:
        score += 40
    if "/out/" in text:
        score += 20
    if "/release/" in text:
        score += 20
    if "/relwithdebinfo/" in text:
        score += 15
    if "/debug/" in text:
        score -= 25
    return score


def _existing_unique(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        if not path.is_file():
            continue
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _find_tool_executable(
    *,
    root: Path,
    runtime_relative_path: Path,
    executable_name: str,
    fallback_relative_path: Path,
    source_roots: tuple[Path, ...],
    preferred_globs: tuple[str, ...],
) -> Path | None:
    runtime_candidate = root / runtime_relative_path
    if runtime_candidate.is_file():
        return runtime_candidate

    candidates: list[Path] = []

    for source_root in source_roots:
        if not source_root.exists():
            continue
        for pattern in preferred_globs:
            candidates.extend(source_root.glob(pattern))
        candidates.extend(source_root.glob(f"**/{executable_name}"))

    ranked = _existing_unique(candidates)
    ranked.sort(
        key=lambda p: (_tool_candidate_score(p), -len(p.parts), p.as_posix().lower()),
        reverse=True,
    )
    if ranked:
        return ranked[0]

    fallback = root / fallback_relative_path
    if fallback.is_file():
        return fallback
    return None


def discover_tool_paths() -> ToolPaths:
    resolved: dict[str, Path | None] = {
        "jpegli": None,
        "mozjpeg": None,
        "butteraugli": None,
    }

    roots = _candidate_tools_roots()
    for root in roots:
        if resolved["jpegli"] is None:
            resolved["jpegli"] = _find_tool_executable(
                root=root,
                runtime_relative_path=Path("runtime") / "jpegli" / "cjpegli.exe",
                executable_name="cjpegli.exe",
                fallback_relative_path=Path("jpegli") / "cjpegli.exe",
                source_roots=(root / "jpegli" / "jpegli-main", root / "jpegli"),
                preferred_globs=(
                    "build/**/cjpegli.exe",
                    "out/**/cjpegli.exe",
                    "tools/**/cjpegli.exe",
                ),
            )

        if resolved["mozjpeg"] is None:
            resolved["mozjpeg"] = _find_tool_executable(
                root=root,
                runtime_relative_path=Path("runtime") / "mozjpeg" / "cjpeg.exe",
                executable_name="cjpeg.exe",
                fallback_relative_path=Path("mozjpeg") / "cjpeg.exe",
                source_roots=(root / "mozjpeg" / "mozjpeg-4.1.1", root / "mozjpeg"),
                preferred_globs=(
                    "build/**/cjpeg.exe",
                    "out/**/cjpeg.exe",
                    "**/cjpeg.exe",
                ),
            )

        if resolved["butteraugli"] is None:
            resolved["butteraugli"] = _find_tool_executable(
                root=root,
                runtime_relative_path=Path("runtime") / "butteraugli" / "butteraugli.exe",
                executable_name="butteraugli.exe",
                fallback_relative_path=Path("butteraugli") / "butteraugli.exe",
                source_roots=(root / "butteraugli" / "butteraugli-master", root / "butteraugli"),
                preferred_globs=(
                    "build/**/butteraugli.exe",
                    "out/**/butteraugli.exe",
                    "**/butteraugli.exe",
                ),
            )

    missing: list[str] = []
    if resolved["jpegli"] is None:
        missing.append("tools/runtime/jpegli/cjpegli.exe (or tools/jpegli/cjpegli.exe)")
    if resolved["mozjpeg"] is None:
        missing.append("tools/runtime/mozjpeg/cjpeg.exe (or tools/mozjpeg/cjpeg.exe)")
    if resolved["butteraugli"] is None:
        missing.append("tools/runtime/butteraugli/butteraugli.exe (or tools/butteraugli/butteraugli.exe)")

    if missing:
        joined = "\n".join(missing)
        searched = "\n".join(str(path) for path in roots)
        raise ToolDiscoveryError(
            "Missing required encoder/scorer binaries. Expected these files:\n"
            f"{joined}\n\nSearched tool roots:\n{searched}\n\n"
            "Build the binaries from the local source trees under tools/, or place the Windows "
            "executables in the tool root folders shown above and restart the app."
        )

    return ToolPaths(
        jpegli=resolved["jpegli"],
        mozjpeg=resolved["mozjpeg"],
        butteraugli=resolved["butteraugli"],
    )
