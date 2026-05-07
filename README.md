# smolJPEG Image Compression

smolJPEG is a standalone Windows 11 desktop app for batch JPEG compression by target file size.
You set a max size in MB, and the app finds the best result under that limit while keeping the original image resolution.

## What This App Is

- Local-first desktop app (no cloud upload).
- Built and packaged for Windows 11 distribution.
- Single installer EXE output for sharing to end users.

## Speed and Quality Modes

smolJPEG gives you two operating modes so you can choose speed or maximum visual quality.

### Performance (Fast)

- Uses Pillow for quick JPEG quality search.
- Optimized for fast throughput on large batches.
- Best for social/web workflows where speed matters most.

### Quality (Slow)

- Uses `jpegli`, `mozjpeg`, and `butteraugli` tooling.
- Tries more candidate encodes and compares perceptual quality.
- Best for archive/reference outputs under strict size limits.

## Core Workflow (In App)

1. Choose source folder.
2. Choose destination folder.
3. Set max file size (MB).
4. Pick mode (`Performance` or `Quality`).
5. Click `Compress`.

UI controls include `Compress`, `Cancel`, `Open destination folder`, and `Reset` (restores batch settings defaults).

## Supported Input Formats

- BMP
- DIB
- JPG / JPEG / JPE / JFIF
- PNG
- TIF / TIFF
- WEBP

## Output Behavior

- Output format is always `.jpg`.
- Original pixel dimensions are preserved.
- Existing names are not overwritten (`image__2.jpg`, etc.).
- Files already under target size are skipped.

## Windows 11 Build and Release

The release pipeline is designed for Windows 11 and produces an installer EXE.

### Prerequisites

- Python virtual environment with project dependencies.
- Visual Studio 2022 Build Tools (C++ workload, includes `dumpbin`).
- Inno Setup 6 (`ISCC.exe`).

### Recommended Release Flow

From project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\release_windows.ps1 -Version 0.1.0
```

This does:

1. Build/stage runtime tool executables.
2. Build standalone app folder via `pyside6-deploy`.
3. Build installer EXE with Inno Setup.

Installer output:

```text
installer/output/smolJPEG_Setup_<version>.exe
```

## Strict Source-Built Tooling (Current Behavior)

`build_tools.ps1` now runs in strict mode by default:

- Accepts tool binaries from source build outputs only (`build` / `bazel-bin`).
- Does not silently reuse legacy prebuilt EXEs from `tools/<tool>/`.
- Writes `tools/runtime/build_manifest.json` with staged file hashes.

`package_standalone.ps1` verifies that runtime manifest before packaging.

Optional fallback mode (not recommended):

```powershell
.\build_tools.ps1 -AllowPrebuiltFallback
.\package_standalone.ps1 -AllowPrebuiltFallback
```

## Repository Notes

- Runtime packaged tools are staged under `tools/runtime/` during build.
- Legacy root-level tool EXEs under `tools/jpegli`, `tools/mozjpeg`, and `tools/butteraugli` were removed to avoid accidental reuse.

