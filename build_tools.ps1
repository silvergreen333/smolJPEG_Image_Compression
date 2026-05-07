param(
    [ValidateSet("Release", "RelWithDebInfo", "Debug")]
    [string]$Configuration = "Release",
    [switch]$SkipBuild,
    [switch]$AllowPrebuiltFallback
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolsRoot = Join-Path $projectRoot "tools"
$runtimeRoot = Join-Path $toolsRoot "runtime"

function Write-Step([string]$message) {
    Write-Host "`n==> $message" -ForegroundColor Cyan
}

function Ensure-Directory([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

function Reset-Directory([string]$path) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

function Invoke-ExternalCommand(
    [string]$exe,
    [string[]]$arguments,
    [string]$workingDir
) {
    Push-Location $workingDir
    try {
        & $exe @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $exe $($arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Ensure-JpegliDependencies([string]$jpegliSourceDir) {
    $thirdPartyDir = Join-Path $jpegliSourceDir "third_party"
    if (-not (Test-Path -LiteralPath $thirdPartyDir)) {
        Write-Warning "jpegli third_party folder not found: $thirdPartyDir"
        return
    }

    $deps = @(
        @{
            Name = "highway"
            RelativePath = "third_party\highway"
            Marker = "CMakeLists.txt"
            Repo = "google/highway"
            Sha = "271a9a0ed9de1232d9117f1572c3fe28f8542ec1"
        },
        @{
            Name = "skcms"
            RelativePath = "third_party\skcms"
            Marker = "skcms.h"
            Repo = "google/skcms"
            Sha = "96d9171c94b937a1b5f0293de7309ac16311b722"
        },
        @{
            Name = "sjpeg"
            RelativePath = "third_party\sjpeg"
            Marker = "CMakeLists.txt"
            Repo = "webmproject/sjpeg"
            Sha = "94e0df6d0f8b44228de5be0ff35efb9f946a13c9"
        },
        @{
            Name = "zlib"
            RelativePath = "third_party\zlib"
            Marker = "CMakeLists.txt"
            Repo = "madler/zlib"
            Sha = "51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf"
        },
        @{
            Name = "libpng"
            RelativePath = "third_party\libpng"
            Marker = "CMakeLists.txt"
            Repo = "glennrp/libpng"
            Sha = "872555f4ba910252783af1507f9e7fe1653be252"
        },
        @{
            Name = "libjpeg-turbo"
            RelativePath = "third_party\libjpeg-turbo"
            Marker = "CMakeLists.txt"
            Repo = "libjpeg-turbo/libjpeg-turbo"
            Sha = "8ecba3647edb6dd940463fedf38ca33a8e2a73d1"
        }
    )

    $tarExe = Get-Command tar -ErrorAction SilentlyContinue
    if ($null -eq $tarExe) {
        Write-Warning "tar command not found; cannot auto-provision jpegli dependencies."
        return
    }

    $downloadsDir = Join-Path $jpegliSourceDir "downloads"
    Ensure-Directory $downloadsDir

    foreach ($dep in $deps) {
        $depRoot = Join-Path $jpegliSourceDir $dep.RelativePath
        $markerPath = Join-Path $depRoot $dep.Marker
        if (Test-Path -LiteralPath $markerPath) {
            continue
        }

        Write-Step "Provisioning jpegli dependency: $($dep.Name)"
        Ensure-Directory $depRoot
        Get-ChildItem -Path $depRoot -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

        $archivePath = Join-Path $downloadsDir "$($dep.Sha).tar.gz"
        if (-not (Test-Path -LiteralPath $archivePath)) {
            $url = "https://github.com/$($dep.Repo)/tarball/$($dep.Sha)"
            Write-Host "Downloading $url"
            Invoke-WebRequest -Uri $url -OutFile $archivePath
        }

        Invoke-ExternalCommand -exe $tarExe.Source -arguments @(
            "-xzf",
            $archivePath,
            "-C",
            $depRoot,
            "--strip-components=1"
        ) -workingDir $projectRoot
    }
}

function Get-PathScore([string]$fullName) {
    $path = $fullName.ToLowerInvariant()
    $score = 0

    if ($path -like "*\runtime\*") { $score += 300 }
    if ($path -like "*\build\*") { $score += 120 }
    if ($path -like "*\release\*") { $score += 60 }
    if ($path -like "*\relwithdebinfo\*") { $score += 40 }
    if ($path -like "*\debug\*") { $score -= 100 }

    return $score
}

function Find-BestExecutable([string]$searchRoot, [string]$exeName) {
    if (-not (Test-Path -LiteralPath $searchRoot)) {
        return $null
    }

    $candidates = Get-ChildItem -Path $searchRoot -Recurse -File -Filter $exeName -ErrorAction SilentlyContinue
    if (-not $candidates) {
        return $null
    }

    return $candidates |
        Sort-Object `
            @{ Expression = { Get-PathScore $_.FullName }; Descending = $true }, `
            @{ Expression = { $_.LastWriteTimeUtc }; Descending = $true } |
        Select-Object -First 1
}

function Try-Build-WithCMake(
    [string]$name,
    [string]$sourceDir,
    [string]$buildDir,
    [string]$target,
    [string[]]$extraConfigureArgs = @()
) {
    if ($SkipBuild) {
        Write-Host "Skipping build for $name (SkipBuild enabled)."
        return
    }

    if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
        Write-Warning "cmake not found; skipping build for $name."
        return
    }

    if (-not (Test-Path -LiteralPath $sourceDir)) {
        Write-Warning "$name source folder not found: $sourceDir"
        return
    }

    Ensure-Directory $buildDir

    $configureArgs = @(
        "-S", $sourceDir,
        "-B", $buildDir,
        "-DCMAKE_BUILD_TYPE=$Configuration"
    ) + $extraConfigureArgs

    Write-Step "Configuring $name"
    try {
        Invoke-ExternalCommand -exe "cmake" -arguments $configureArgs -workingDir $projectRoot
    }
    catch {
        Write-Warning "CMake configure failed for ${name}: $($_.Exception.Message)"
        return
    }

    Write-Step "Building $name target '$target'"
    try {
        Invoke-ExternalCommand -exe "cmake" -arguments @("--build", $buildDir, "--config", $Configuration, "--target", $target) -workingDir $projectRoot
    }
    catch {
        Write-Warning "CMake build failed for ${name}: $($_.Exception.Message)"
    }
}

function Try-Build-Butteraugli([string]$sourceDir) {
    if ($SkipBuild) {
        Write-Host "Skipping build for butteraugli (SkipBuild enabled)."
        return
    }

    if (-not (Test-Path -LiteralPath $sourceDir)) {
        Write-Warning "butteraugli source folder not found: $sourceDir"
        return
    }

    $bazelExe = $null
    $bazel = Get-Command bazel -ErrorAction SilentlyContinue
    if ($null -ne $bazel) {
        $bazelExe = $bazel.Source
    }

    if ($null -eq $bazelExe) {
        $fallbackCandidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Bazelisk\bazel.exe"),
            (Join-Path $env:LOCALAPPDATA "Programs\Bazelisk\bazelisk.exe"),
            (Join-Path $env:ProgramFiles "Bazelisk\bazel.exe"),
            (Join-Path $env:ProgramFiles "Bazelisk\bazelisk.exe")
        )
        foreach ($candidate in $fallbackCandidates) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                $bazelExe = $candidate
                break
            }
        }
    }

    if ($null -eq $bazelExe) {
        Write-Warning "bazel not found; skipping butteraugli source build."
        return
    }

    Write-Step "Building butteraugli with Bazel ($bazelExe)"
    $oldUseBazelVersion = $env:USE_BAZEL_VERSION
    $env:USE_BAZEL_VERSION = "8.4.2"
    try {
        Invoke-ExternalCommand -exe $bazelExe -arguments @(
            "build",
            "--enable_workspace=true",
            "--enable_bzlmod=false",
            "//:butteraugli"
        ) -workingDir $sourceDir
    }
    catch {
        Write-Warning "Bazel build failed for butteraugli: $($_.Exception.Message)"
    }
    finally {
        if ($null -eq $oldUseBazelVersion) {
            Remove-Item Env:USE_BAZEL_VERSION -ErrorAction SilentlyContinue
        }
        else {
            $env:USE_BAZEL_VERSION = $oldUseBazelVersion
        }
    }
}

function Stage-Tool(
    [string]$toolName,
    [string]$exeName,
    [string[]]$searchRoots,
    [string]$destinationDir
) {
    Ensure-Directory $destinationDir

    $selected = $null
    foreach ($root in $searchRoots) {
        $candidate = Find-BestExecutable -searchRoot $root -exeName $exeName
        if ($null -ne $candidate) {
            $selected = $candidate
            break
        }
    }

    if ($null -eq $selected) {
        Write-Warning "No $exeName found for $toolName. Search roots:`n  $($searchRoots -join "`n  ")"
        return $null
    }

    $dest = Join-Path $destinationDir $exeName
    Copy-Item -LiteralPath $selected.FullName -Destination $dest -Force
    Write-Host "$toolName staged: $($selected.FullName) -> $dest"
    return [PSCustomObject]@{
        toolName = $toolName
        exeName = $exeName
        sourcePath = $selected.FullName
        destinationPath = $dest
        sourceLastWriteTimeUtc = $selected.LastWriteTimeUtc.ToString("o")
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $dest).Hash
    }
}

$jpegliSource = Join-Path $toolsRoot "jpegli\jpegli-main"
$mozjpegSource = Join-Path $toolsRoot "mozjpeg\mozjpeg-4.1.1"
$butterSource = Join-Path $toolsRoot "butteraugli\butteraugli-master"

$jpegliBuild = Join-Path $jpegliSource "build"
$mozjpegBuild = Join-Path $mozjpegSource "build"

Ensure-JpegliDependencies -jpegliSourceDir $jpegliSource

Try-Build-WithCMake `
    -name "jpegli" `
    -sourceDir $jpegliSource `
    -buildDir $jpegliBuild `
    -target "cjpegli" `
    -extraConfigureArgs @(
        "-DBUILD_TESTING=OFF",
        "-DJPEGLI_ENABLE_DOXYGEN=OFF",
        "-DJPEGLI_ENABLE_MANPAGES=OFF",
        "-DJPEGLI_ENABLE_JNI=OFF",
        "-DJPEGLI_ENABLE_BENCHMARK=OFF",
        "-DJPEGLI_ENABLE_TOOLS=ON",
        "-DJPEGLI_ENABLE_SKCMS=ON"
    )
Try-Build-WithCMake `
    -name "mozjpeg" `
    -sourceDir $mozjpegSource `
    -buildDir $mozjpegBuild `
    -target "cjpeg" `
    -extraConfigureArgs @(
        "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",
        "-DPNG_SUPPORTED=OFF",
        "-DWITH_TURBOJPEG=OFF"
    )
Try-Build-Butteraugli -sourceDir $butterSource

Write-Step "Staging runtime tools"
$strictSourceOnly = -not $AllowPrebuiltFallback
if ($strictSourceOnly) {
    Write-Host "Mode: strict source build only (no prebuilt fallback)." -ForegroundColor Yellow
}
else {
    Write-Warning "Mode: prebuilt fallback enabled."
}

Reset-Directory -path $runtimeRoot

$jpegliRoots = @($jpegliBuild)
$mozjpegRoots = @($mozjpegBuild)
$butterRoots = @((Join-Path $butterSource "bazel-bin"))

if ($AllowPrebuiltFallback) {
    $jpegliRoots += @($jpegliSource, (Join-Path $toolsRoot "jpegli"))
    $mozjpegRoots += @($mozjpegSource, (Join-Path $toolsRoot "mozjpeg"))
    $butterRoots += @($butterSource, (Join-Path $toolsRoot "butteraugli"))
}

$jpegliResult = Stage-Tool `
    -toolName "jpegli" `
    -exeName "cjpegli.exe" `
    -searchRoots $jpegliRoots `
    -destinationDir (Join-Path $runtimeRoot "jpegli")

$mozjpegResult = Stage-Tool `
    -toolName "mozjpeg" `
    -exeName "cjpeg.exe" `
    -searchRoots $mozjpegRoots `
    -destinationDir (Join-Path $runtimeRoot "mozjpeg")

$butterResult = Stage-Tool `
    -toolName "butteraugli" `
    -exeName "butteraugli.exe" `
    -searchRoots $butterRoots `
    -destinationDir (Join-Path $runtimeRoot "butteraugli")

Write-Step "Done"
if (($null -eq $jpegliResult) -or ($null -eq $mozjpegResult) -or ($null -eq $butterResult)) {
    Write-Warning "One or more runtime tools were not staged. Check warnings above."
    if ($strictSourceOnly) {
        if ($null -eq $jpegliResult) {
            Write-Host "Hint: jpegli source build did not produce cjpegli.exe." -ForegroundColor Yellow
        }
        if ($null -eq $mozjpegResult) {
            Write-Host "Hint: mozjpeg source build did not produce cjpeg.exe." -ForegroundColor Yellow
        }
        if ($null -eq $butterResult) {
            $hasBazelPath = $null -ne (Get-Command bazel -ErrorAction SilentlyContinue)
            $hasBazelLocalInstall = Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA "Programs\Bazelisk\bazel.exe")
            if (-not ($hasBazelPath -or $hasBazelLocalInstall)) {
                Write-Host "Hint: install Bazelisk (or Bazel) so butteraugli can be built from source." -ForegroundColor Yellow
            }
            else {
                Write-Host "Hint: butteraugli source build did not produce butteraugli.exe." -ForegroundColor Yellow
            }
        }
    }
    exit 1
}

$manifestPath = Join-Path $runtimeRoot "build_manifest.json"
$manifest = [PSCustomObject]@{
    generatedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    configuration = $Configuration
    skipBuild = [bool]$SkipBuild
    strictSourceOnly = $strictSourceOnly
    tools = @($jpegliResult, $mozjpegResult, $butterResult)
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "Runtime manifest: $manifestPath"
Write-Host "All runtime tools are ready under: $runtimeRoot"
exit 0
