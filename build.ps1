# Windows wrapper for tools\build.py; settings (patch, pnach, Docker image, install folder) are in
# config.toml.  Usage: .\build.ps1 [-Install]   (-Install copies the pnach into PCSX2's patches folder)
param([switch]$Install)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$buildArgs = @()
if ($Install) { $buildArgs += '--install' }

py -3 tools\build.py @buildArgs
if ($LASTEXITCODE -ne 0) { throw "build failed" }
