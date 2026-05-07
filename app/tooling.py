from __future__ import annotations

from pathlib import Path

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


def discover_tool_paths() -> ToolPaths:
    root = tools_root()
    jpegli = root / "jpegli" / "cjpegli.exe"
    mozjpeg = root / "mozjpeg" / "cjpeg.exe"
    butteraugli = root / "butteraugli" / "butteraugli.exe"

    missing = [p for p in (jpegli, mozjpeg, butteraugli) if not p.exists()]
    if missing:
        joined = "\n".join(str(p) for p in missing)
        raise ToolDiscoveryError(
            "Missing required encoder/scorer binaries. Expected these files:\n"
            f"{joined}\n\n"
            "Rebuild the packaged app with the bundled tools, or put the Windows executables "
            "in the tools/ folder shown above and restart the app."
        )

    return ToolPaths(
        jpegli=jpegli,
        mozjpeg=mozjpeg,
        butteraugli=butteraugli,
    )