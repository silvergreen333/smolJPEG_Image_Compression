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

    $bazel = Get-Command bazel -ErrorAction SilentlyContinue
    if ($null -eq $bazel) {
        Write-Warning "bazel not found; skipping butteraugli source build."
        return
    }

    Write-Step "Building butteraugli with Bazel"
    try {
        Invoke-ExternalCommand -exe "bazel" -arguments @("build", "//butteraugli:butteraugli") -workingDir $sourceDir
    }
    catch {
        Write-Warning "Bazel build failed for butteraugli: $($_.Exception.Message)"
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

Try-Build-WithCMake -name "jpegli" -sourceDir $jpegliSource -buildDir $jpegliBuild -target "cjpegli"
Try-Build-WithCMake `
    -name "mozjpeg" `
    -sourceDir $mozjpegSource `
    -buildDir $mozjpegBuild `
    -target "cjpeg" `
    -extraConfigureArgs @("-DCMAKE_POLICY_VERSION_MINIMUM=3.5")
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
