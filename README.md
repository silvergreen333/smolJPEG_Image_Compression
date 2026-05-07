# smolJPEG Image Compression

smolJPEG is a standalone Windows 11 desktop app for batch JPEG compression by target file size.
You set a max size in MB, and the app finds the best result under that limit while keeping the original image resolution.

## What This App Is

- Local-first desktop app (no cloud upload).
- Built and packaged for Windows 11 distribution.
- Single installer EXE output for sharing to end users.

## Releases

- Latest installer: `smolJPEG_Setup_0.1.2.exe`
- GitHub Releases page: <https://github.com/silvergreen333/smolJPEG_Image_Compression/releases>

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

## Installation (Windows 11)

Use the packaged installer EXE to install and run smolJPEG on Windows 11.

When a release is shared, run:

```text
smolJPEG_Setup_<version>.exe
```

Then follow the setup wizard and launch `smolJPEG Image Compression` from Start Menu or Desktop shortcut.

## Notes

- This repository contains source code and packaging scripts.
- End users should use the packaged installer EXE.
- Legacy root-level tool EXEs under `tools/jpegli`, `tools/mozjpeg`, and `tools/butteraugli` were removed.
