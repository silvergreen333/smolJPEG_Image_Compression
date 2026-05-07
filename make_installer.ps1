param(
    [string]$AppDir = "",
    [string]$Version = "0.1.8",
    [string]$OutputDir = "installer\output",
    [string]$IsccPath = "",
    [string]$Publisher = "Silvergreen333",
    [switch]$EnableSigning,
    [string]$SignToolPath = "",
    [string]$CertFile = "",
    [string]$CertPassword = "",
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$FileDigest = "sha256",
    [string]$TimestampDigest = "sha256"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$issPath = Join-Path $projectRoot "installer\smoljpeg.iss"
$appExeName = "smolJPEG Image Compression.exe"

function Write-Step([string]$message) {
    Write-Host "`n==> $message" -ForegroundColor Cyan
}

function Resolve-SignToolExe([string]$requestedPath) {
    if (-not [string]::IsNullOrWhiteSpace($requestedPath)) {
        if (-not (Test-Path -LiteralPath $requestedPath)) {
            throw "Specified SignTool path does not exist: $requestedPath"
        }
        return (Resolve-Path -LiteralPath $requestedPath).Path
    }

    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        $cmd = Get-Command signtool -ErrorAction SilentlyContinue
    }
    if ($null -ne $cmd) {
        return $cmd.Source
    }

    $kitRoots = @(
        "C:\Program Files (x86)\Windows Kits\10\bin",
        "C:\Program Files\Windows Kits\10\bin"
    )
    foreach ($kitRoot in $kitRoots) {
        if (-not (Test-Path -LiteralPath $kitRoot)) {
            continue
        }

        $versionDirs = Get-ChildItem -Path $kitRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending
        foreach ($versionDir in $versionDirs) {
            foreach ($arch in @("x64", "x86")) {
                $candidate = Join-Path $versionDir.FullName "$arch\signtool.exe"
                if (Test-Path -LiteralPath $candidate) {
                    return $candidate
                }
            }
        }
    }

    return $null
}

function Get-LatestDistFolder([string]$root) {
    return Get-ChildItem -Path $root -Directory -Filter "*.dist" |
        Where-Object { $_.FullName -notlike "*\.venv\*" } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}

if (-not (Test-Path -LiteralPath $issPath)) {
    throw "Installer script not found: $issPath"
}

if ([string]::IsNullOrWhiteSpace($AppDir)) {
    Write-Step "Locating standalone app folder"
    $distFolder = Get-LatestDistFolder -root $projectRoot
    if ($null -eq $distFolder) {
        throw "Could not auto-detect standalone app folder. Pass -AppDir explicitly."
    }

    $AppDir = $distFolder.FullName
}

$resolvedAppDir = (Resolve-Path -LiteralPath $AppDir).Path
$outputDirPath = Join-Path $projectRoot $OutputDir
New-Item -ItemType Directory -Path $outputDirPath -Force | Out-Null
$resolvedOutputDir = (Resolve-Path -LiteralPath $outputDirPath).Path

if (-not [string]::IsNullOrWhiteSpace($IsccPath)) {
    if (-not (Test-Path -LiteralPath $IsccPath)) {
        throw "Specified ISCC path does not exist: $IsccPath"
    }
    $isccExe = (Resolve-Path -LiteralPath $IsccPath).Path
}
else {
    $isccExe = $null

    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($null -eq $iscc) {
        $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    }
    if ($null -ne $iscc) {
        $isccExe = $iscc.Source
    }

    if ($null -eq $isccExe) {
        $defaultCandidates = @(
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe"
        )
        foreach ($candidate in $defaultCandidates) {
            if (Test-Path -LiteralPath $candidate) {
                $isccExe = $candidate
                break
            }
        }
    }
}

if ($null -eq $isccExe) {
    throw "Inno Setup compiler (iscc.exe) not found in PATH."
}

$shouldSign = [bool]$EnableSigning -or
    (-not [string]::IsNullOrWhiteSpace($CertFile)) -or
    (-not [string]::IsNullOrWhiteSpace($CertThumbprint))

$isccArgs = @(
    "/DSourceDir=$resolvedAppDir",
    "/DOutputDir=$resolvedOutputDir",
    "/DMyAppVersion=$Version",
    "/DMyAppPublisher=$Publisher"
)

if ($shouldSign) {
    if ([string]::IsNullOrWhiteSpace($CertFile) -and [string]::IsNullOrWhiteSpace($CertThumbprint)) {
        throw "Signing enabled but no certificate provided. Use -CertFile or -CertThumbprint."
    }
    if ((-not [string]::IsNullOrWhiteSpace($CertFile)) -and (-not [string]::IsNullOrWhiteSpace($CertThumbprint))) {
        throw "Specify either -CertFile or -CertThumbprint, not both."
    }

    $signtoolExe = Resolve-SignToolExe -requestedPath $SignToolPath
    if ([string]::IsNullOrWhiteSpace($signtoolExe)) {
        throw "signtool.exe not found. Install Windows SDK / MSVC Build Tools, or pass -SignToolPath."
    }

    $signParts = @(
        "`$q$signtoolExe`$q",
        "sign",
        "/fd $FileDigest"
    )
    if (-not [string]::IsNullOrWhiteSpace($TimestampUrl)) {
        $signParts += "/tr `$q$TimestampUrl`$q"
        $signParts += "/td $TimestampDigest"
    }
    if (-not [string]::IsNullOrWhiteSpace($CertFile)) {
        $resolvedCertPath = (Resolve-Path -LiteralPath $CertFile).Path
        $signParts += "/f `$q$resolvedCertPath`$q"
        if (-not [string]::IsNullOrWhiteSpace($CertPassword)) {
            $signParts += "/p `$q$CertPassword`$q"
        }
    }
    else {
        $signParts += "/sha1 $CertThumbprint"
    }
    $signParts += "/d `$q$Publisher`$q"
    $signParts += "/du `$qhttps://github.com/silvergreen333/smolJPEG_Image_Compression`$q"
    $signParts += "`$f"

    $signCommand = $signParts -join " "
    $isccArgs += "/DEnableSigning=1"
    $isccArgs += "/Ssigntool=$signCommand"

    Write-Host "Code signing enabled using: $signtoolExe" -ForegroundColor Yellow
}
else {
    Write-Host "Code signing disabled (unsigned installer)." -ForegroundColor Yellow
}

$isccArgs += $issPath

Write-Step "Building installer"
Push-Location (Join-Path $projectRoot "installer")
try {
    & $isccExe @isccArgs

    if ($LASTEXITCODE -ne 0) {
        throw "ISCC failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$setup = Get-ChildItem -Path $resolvedOutputDir -File -Filter "*.exe" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1

Write-Step "Done"
if ($null -ne $setup) {
    Write-Host "Installer created: $($setup.FullName)"
}
else {
    Write-Host "Installer build completed. Check output folder: $resolvedOutputDir"
}
