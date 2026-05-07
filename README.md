# smolJPEG Image Compression

smolJPEG is a standalone Windows 11 desktop app for batch JPEG compression by target file size.
You set a max size in MB, and the app finds the best result under that limit while keeping the original image resolution.

## What This App Is

- A Windows 11 image compression app.
- Same resolution, smaller file size.
- Runs locally (no cloud upload).
- Example: `3840x2160 image (30 MB) --> 3840x2160 image (8 MB)`

## Releases and Installation (Windows 11)

- Latest installer: `smolJPEG_Setup_0.1.9.exe`
- GitHub Releases page: <https://github.com/silvergreen333/smolJPEG_Image_Compression/releases>
- Download installers only from the official GitHub Releases page above.
- The installer is currently unsigned, so Windows SmartScreen may show a warning on first run. Use `More info` -> `Run anyway`.
- Run the installer EXE, follow the setup wizard, then launch `smolJPEG Image Compression` from Start Menu or Desktop shortcut.

## Performance and Quality Modes

smolJPEG gives you two modes with different priorities: fast batch turnaround or best visual quality under your size limit.
It is built this way so you do not have to manually guess JPEG settings for different image types.

### Performance (Fast)

- Uses Pillow (a library for image processing in Python) for a direct JPEG quality search.
- Checks quality levels quickly and keeps the first result that fits your max MB target.
- Preserves original resolution and skips files that are already under the limit.
- Minimizes heavy analysis so large folders finish faster.

Why this process:
- Fast path for big batches and repeated exports.
- Good visual results without long wait times.
- Predictable throughput when delivery speed matters.

Best for:
- Social media exports
- Web uploads
- Everyday bulk compression where speed matters most

### Quality (Slow)

- Builds a high-quality working copy of each image, then tests many candidates with `jpegli` (a modern encoder tuned for strong visual quality per byte) and `mozjpeg` (a widely used encoder tuned for high compression efficiency).
- Tries multiple chroma subsampling options plus both baseline and progressive MozJPEG variants.
- Uses `butteraugli` (a perceptual metric that estimates what differences people can actually notice) to score candidates, then keeps the best-looking result that still meets your max MB target.
- Preserves original resolution and automatically writes the winning candidate to output.

Why this process:
- Prioritizes detail retention during compression.
- Reduces manual trial-and-error by automatically comparing many options.
- Delivers more consistent "best possible under size cap" results across mixed image sets.

Best for:
- Archive/reference images
- Screenshots or artwork where fine detail matters
- Tight size limits where you still want the best possible look

In short:
- `Performance` = fastest path to "under size limit"
- `Quality` = most visual optimization before final save

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

## Notes

- This repository contains source code and packaging scripts.
- End users should use the packaged installer EXE.
- Installer/app bundles include `THIRD_PARTY_NOTICES.txt` and the
  `third_party_licenses` folder for open-source attribution.
