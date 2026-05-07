param(
    [string]$AppDir = "",
    [string]$Version = "0.1.2",
    [string]$OutputDir = "installer\output",
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$issPath = Join-Path $projectRoot "installer\smoljpeg.iss"
$appExeName = "smolJPEG Image Compression.exe"

function Write-Step([string]$message) {
    Write-Host "`n==> $message" -ForegroundColor Cyan
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

Write-Step "Building installer"
Push-Location (Join-Path $projectRoot "installer")
try {
    & $isccExe `
        "/DSourceDir=$resolvedAppDir" `
        "/DOutputDir=$resolvedOutputDir" `
        "/DMyAppVersion=$Version" `
        $issPath

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
