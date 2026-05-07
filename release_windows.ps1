param(
    [string]$Version = "0.1.9",
    [switch]$SkipToolBuild,
    [string]$Publisher = "Silvergreen333",
    [switch]$EnableSigning,
    [string]$SignToolPath = "",
    [string]$CertFile = "",
    [string]$CertPassword = "",
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n==> Building standalone app" -ForegroundColor Cyan
if ($SkipToolBuild) {
    & (Join-Path $projectRoot "package_standalone.ps1") -SkipToolBuild
}
else {
    & (Join-Path $projectRoot "package_standalone.ps1")
}
if ($LASTEXITCODE -ne 0) {
    throw "package_standalone.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "`n==> Building installer EXE" -ForegroundColor Cyan
& (Join-Path $projectRoot "make_installer.ps1") `
    -Version $Version `
    -Publisher $Publisher `
    -EnableSigning:$EnableSigning `
    -SignToolPath $SignToolPath `
    -CertFile $CertFile `
    -CertPassword $CertPassword `
    -CertThumbprint $CertThumbprint `
    -TimestampUrl $TimestampUrl
if ($LASTEXITCODE -ne 0) {
    throw "make_installer.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "`n==> Release workflow complete" -ForegroundColor Green
