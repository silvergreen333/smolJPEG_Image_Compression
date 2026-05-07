# smolJPEG Image Compression

smolJPEG is a local Windows desktop app built to batch-compress images into JPEGs based entirely on your target file size, fully preserving the original image resolution.

Instead of relying on guesswork with vague "JPEG Quality" sliders, smolJPEG allows you to set a strict maximum file limit right from the start. The app then works intelligently behind the scenes to automatically generate the absolute best-looking image that fits perfectly within your designated size.

It is the ideal solution for social media uploads, websites, and digital archives that enforce strict file-size constraints, ensuring your pictures remain stunning without ever exceeding your limits.

---

## Features at a Glance

* **Size-Targeted Compression**: Hit your exact file size limits for sharing or storage.
* **Resolution Preservation**: Keeps the original pixel dimensions of your image completely intact.
* **Broad Input Support**: Reads BMP, DIB, JPG, JPEG, JPE, JFIF, PNG, TIF, TIFF, and WEBP formats.
* **Smart Skipping**: Automatically skips images that are already under your size limit, saving time.
* **Safe Saving**: Always outputs to `.jpg` and automatically renames files (e.g., `image__2.jpg`) to prevent accidental overwriting.
* **Clear Feedback**: Shows per-file results (Done, Skipped, Cancelled, Failed) and lets you stop a run safely while it is in progress.

---

## How It Works

The interface is designed for simplicity. 

1. Choose your source folder.
2. Choose your destination folder.
3. Enter your maximum file size (in MB).
4. Select a compression mode.
5. Click **Compress**.

> **Note:** The app currently only scans the top level of your source folder, and your destination folder must already exist before you start.

---

## Deep Dive: Compression Modes

smolJPEG offers two distinct engines depending on what you value most: speed or maximum visual quality.

### Performance Mode (Fast)
**Best for:** Web uploads, forums, chat apps, and everyday sharing.

Performance mode is built for speed and practicality. It uses a modern image library called Pillow to quickly test different quality settings. 

* It starts at a maximum quality of 99 and saves a test file.
* If the file is too big, it lowers the quality and tries again until the image fits your size limit.
* It conservatively preserves full color detail (known technically as "4:4:4 chroma subsampling") for predictable, good-looking results.
* **The Tradeoff:** Because it only does a simple search straight down, it doesn't explore complex encoding methods to squeeze out every last drop of visual quality. It simply finds a good, working JPEG fast.

## Compression Modes

smolJPEG features two distinct processing engines, allowing you to prioritize either blazing-fast processing or the absolute highest visual fidelity.

### Performance Mode (Fast)
**Built for:** Web uploads, forums, chat apps, and everyday sharing.

Performance mode is engineered for speed and practicality, utilizing the modern Pillow image library to rapidly deliver great-looking results. 

* **The Variables:** It tests one primary variable: the JPEG quality number. It locks the color detail at full fidelity (4:4:4 chroma subsampling) to guarantee a predictable, rich image without wasting time on advanced searches.
* **The Process:** It executes a single, straightforward search path. It starts at a maximum quality of 99, saves a test file, and checks the size. If the file exceeds your limit, it steps the quality down sequentially and tries again until the image fits.
* **The Tradeoff:** By relying on a direct search, it bypasses complex encoding techniques that could squeeze out slightly more visual detail. It is designed to find a highly capable, working JPEG as fast as possible.

### Quality Mode (Slow)
**Built for:** Archiving, reference copies, and achieving the absolute best visual quality under a strict, unforgiving size limit.

Quality mode acts as an automated, multi-engine image researcher. It tests multiple variables—encoder types, structural formats, color detail reductions, and precise visual loss metrics—to mathematically prove which image looks the best. 

* **Preparation:** It completely standardizes your image by converting it into uncompressed PNG and BMP working files. This ensures every subsequent test starts from a flawless, color-corrected baseline.

#### Engine 1: The Jpegli Search
Jpegli is a modern, highly efficient encoder tested against the pristine PNG working file. Quality mode tests Jpegli across three different color detail reductions: 4:4:4, 4:2:2, and 4:2:0. For each of these, it runs a rigorous three-pass search based on a visual "distance" metric:

* **Pass 1 (Coarse Search):** Tests 15 specific preset distance values (ranging from 0.08 to 6.0) to find a general file size fit.
* **Pass 2 (Refinement Search):** Executes up to 10 precise binary search steps to zero in on the exact quality threshold before the file becomes too large.
* **Pass 3 (Dense Scan):** Generates a highly detailed, 9-point microscopic scan around the best result to extract the absolute maximum quality possible.

#### Engine 2: The MozJPEG Search
MozJPEG is an advanced web encoder evaluated using the uncompressed BMP file. Quality mode tests MozJPEG across the same three color detail settings (4:4:4, 4:2:2, 4:2:0), while also testing every combination as both *progressive* (loading in visual layers) and *baseline* (standard loading) formats.

* **Pass 1 (Binary Search):** Rapidly cuts the 1-to-100 quality range in half repeatedly until it finds the highest quality number that satisfies your size limit.
* **Pass 2 (Neighborhood Scan):** Once the threshold is located, the engine exhaustively tests a tight 7-point radius surrounding that number to ensure no optimization is left undiscovered.

#### The Butteraugli Showdown
After all passes are complete, smolJPEG immediately discards any generated file that exceeds your target size limit. The remaining successful candidates are passed to a perceptual scoring tool called **Butteraugli**. 

Butteraugli mathematically compares every candidate against your original image to measure which file looks the closest to the human eye. The app then crowns the file with the absolute best Butteraugli score as the winner, utilizing the exact file size as a final tiebreaker.
---

## What to Expect While Running

As the app processes your images, it uses plain English in the interface to tell you exactly what it is doing. You might see statuses like:

* **Getting image ready:** Creating temporary working files.
* **Compressing image:** Searching for the right size in Performance mode.
* **Testing best settings:** Searching through different encoders in Quality mode.
* **Checking image quality:** Running the Butteraugli visual comparison.

If you change your mind mid-batch, both modes support responsive cancellation. If you hit cancel, the app passes that command down to the external tools and safely stops what it is doing. 

---

## Under the Hood (Requirements)

To use **Quality Mode**, smolJPEG relies on specific external tools. The app searches for them automatically, but it will raise an error if they are missing. 

Ensure your project directory contains the following structure:

```text
tools/
  jpegli/
    cjpegli.exe
  mozjpeg/
    cjpeg.exe
  butteraugli/
    butteraugli.exe

## Windows Build and Packaging Workflow

The recommended Windows release flow is:

1. Build/stage runtime tool executables
2. Build a standalone app folder with `pyside6-deploy`
3. Create a single installer `.exe` (Inno Setup) that installs the app

### 1) Build and stage tool executables

```powershell
.\build_tools.ps1
```

This stages tool binaries into:

```text
tools/runtime/jpegli/cjpegli.exe
tools/runtime/mozjpeg/cjpeg.exe
tools/runtime/butteraugli/butteraugli.exe
```

### 2) Build standalone app folder

```powershell
.\package_standalone.ps1
```

This runs `pyside6-deploy` with `pysidedeploy.standalone.spec`, then copies `tools/runtime` into the packaged app directory.

Prerequisites for this step:

* Visual Studio C++ Build Tools (required by Nuitka on Windows)
* `dumpbin` in `PATH` (ships with MSVC build tools)

### 3) Build single installer EXE

Install [Inno Setup](https://jrsoftware.org/isinfo.php), then run:

```powershell
.\make_installer.ps1 -Version 0.1.0
```

Output:

```text
installer/output/smolJPEG_Setup_<version>.exe
```

### Why this flow

Subprocess helper tools (`cjpegli.exe`, `cjpeg.exe`, `butteraugli.exe`) are most stable when shipped as files in the installed app directory. The installer is still a single distributable `.exe` for end users.
