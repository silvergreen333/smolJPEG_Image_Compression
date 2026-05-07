param(
    [string]$SpecFile = "pysidedeploy.standalone.spec",
    [switch]$SkipToolBuild,
    [switch]$SkipDeploy,
    [switch]$AllowPrebuiltFallback
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$specPath = Join-Path $projectRoot $SpecFile
$runtimeRoot = Join-Path $projectRoot "tools\runtime"
$appExeName = "smolJPEG Image Compression.exe"

function Write-Step([string]$message) {
    Write-Host "`n==> $message" -ForegroundColor Cyan
}

function Invoke-PySideDeploy([string]$root, [string]$spec) {
    $cmd = Get-Command pyside6-deploy -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        & $cmd.Source -f -c $spec
        if ($LASTEXITCODE -ne 0) {
            throw "pyside6-deploy failed with exit code $LASTEXITCODE"
        }
        return
    }

    $venvExe = Join-Path $root ".venv\Scripts\pyside6-deploy.exe"
    if (Test-Path -LiteralPath $venvExe) {
        & $venvExe -f -c $spec
        if ($LASTEXITCODE -ne 0) {
            throw "pyside6-deploy failed with exit code $LASTEXITCODE"
        }
        return
    }

    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    $venvScript = Join-Path $root ".venv\Scripts\pyside6-deploy-script.py"
    if ((Test-Path -LiteralPath $venvPython) -and (Test-Path -LiteralPath $venvScript)) {
        & $venvPython $venvScript -f -c $spec
        if ($LASTEXITCODE -ne 0) {
            throw "pyside6-deploy failed with exit code $LASTEXITCODE"
        }
        return
    }

    throw "pyside6-deploy not found in PATH or .venv\\Scripts."
}

function Get-LatestDistFolder([string]$root) {
    return Get-ChildItem -Path $root -Directory -Filter "*.dist" |
        Where-Object { $_.FullName -notlike "*\.venv\*" } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
}

function Assert-ValidRuntimeManifest([string]$runtimeDir, [bool]$allowPrebuiltFallback) {
    $manifestPath = Join-Path $runtimeDir "build_manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw "Missing runtime manifest at $manifestPath. Run build_tools.ps1 before packaging."
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($null -eq $manifest) {
        throw "Runtime manifest could not be parsed: $manifestPath"
    }

    if ((-not $allowPrebuiltFallback) -and (-not [bool]$manifest.strictSourceOnly)) {
        throw "Runtime manifest is not strict-source mode. Rebuild tools without prebuilt fallback."
    }

    $requiredTools = @("jpegli", "mozjpeg", "butteraugli")
    foreach ($toolName in $requiredTools) {
        $toolEntry = $manifest.tools | Where-Object { $_.toolName -eq $toolName } | Select-Object -First 1
        if ($null -eq $toolEntry) {
            throw "Runtime manifest missing required tool entry: $toolName"
        }

        if (-not (Test-Path -LiteralPath $toolEntry.destinationPath)) {
            throw "Runtime manifest destination missing for ${toolName}: $($toolEntry.destinationPath)"
        }

        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $toolEntry.destinationPath).Hash
        if ($actualHash -ne $toolEntry.sha256) {
            throw "Runtime hash mismatch for ${toolName}: expected $($toolEntry.sha256), got $actualHash"
        }
    }

    Write-Host "Runtime manifest verified: $manifestPath"
}

if (-not (Test-Path -LiteralPath $specPath)) {
    throw "Spec file not found: $specPath"
}

if (-not $SkipToolBuild) {
    Write-Step "Building/staging runtime tool executables"
    if ($AllowPrebuiltFallback) {
        & (Join-Path $projectRoot "build_tools.ps1") -AllowPrebuiltFallback
    }
    else {
        & (Join-Path $projectRoot "build_tools.ps1")
    }
    if ($LASTEXITCODE -ne 0) {
        throw "build_tools.ps1 failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $runtimeRoot)) {
    throw "Runtime tool folder not found: $runtimeRoot"
}
Assert-ValidRuntimeManifest -runtimeDir $runtimeRoot -allowPrebuiltFallback ([bool]$AllowPrebuiltFallback)

if (-not $SkipDeploy) {
    $nuitkaCacheDir = Join-Path $projectRoot "artifacts\nuitka-cache"
    New-Item -ItemType Directory -Path $nuitkaCacheDir -Force | Out-Null
    $oldNuitkaCacheDir = $env:NUITKA_CACHE_DIR
    $env:NUITKA_CACHE_DIR = $nuitkaCacheDir

    Write-Step "Running pyside6-deploy"
    Push-Location $projectRoot
    try {
        Invoke-PySideDeploy -root $projectRoot -spec $specPath
    }
    finally {
        Pop-Location
        if ($null -eq $oldNuitkaCacheDir) {
            Remove-Item Env:NUITKA_CACHE_DIR -ErrorAction SilentlyContinue
        }
        else {
            $env:NUITKA_CACHE_DIR = $oldNuitkaCacheDir
        }
    }
}

Write-Step "Locating packaged app folder"
$distFolder = Get-LatestDistFolder -root $projectRoot
if ($null -eq $distFolder) {
    throw "Could not find any .dist output folder under $projectRoot"
}

$rootExeCandidates = Get-ChildItem -Path $distFolder.FullName -File -Filter "*.exe"
if (-not $rootExeCandidates) {
    throw "No .exe files found in packaged folder: $($distFolder.FullName)"
}

$exeCandidate = $rootExeCandidates | Where-Object { $_.Name -ieq $appExeName } | Select-Object -First 1
if ($null -eq $exeCandidate) {
    $exeCandidate = $rootExeCandidates | Where-Object { $_.Name -ieq "main.exe" } | Select-Object -First 1
}
if ($null -eq $exeCandidate) {
    $exeCandidate = $rootExeCandidates |
        Sort-Object @{ Expression = { $_.Length }; Descending = $true }, @{ Expression = { $_.LastWriteTimeUtc }; Descending = $true } |
        Select-Object -First 1
}

$desiredExePath = Join-Path $distFolder.FullName $appExeName
if ($exeCandidate.Name -ine $appExeName) {
    if (Test-Path -LiteralPath $desiredExePath) {
        Remove-Item -LiteralPath $desiredExePath -Force
    }
    Rename-Item -LiteralPath $exeCandidate.FullName -NewName $appExeName
    $exeCandidate = Get-Item -LiteralPath $desiredExePath
}

$appDir = $distFolder.FullName
Write-Host "Packaged app folder: $appDir"
Write-Host "Main executable: $($exeCandidate.Name)"

Write-Step "Copying runtime tools into packaged app"
$destToolsRuntime = Join-Path $appDir "tools\runtime"
New-Item -ItemType Directory -Path $destToolsRuntime -Force | Out-Null
Copy-Item -Path (Join-Path $runtimeRoot "*") -Destination $destToolsRuntime -Recurse -Force

Write-Step "Done"
Write-Host "Standalone app ready at: $appDir"
