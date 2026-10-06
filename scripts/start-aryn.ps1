[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipInstall,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
# Both child services inherit the same ephemeral runtime authentication.
# This also works when invoked via powershell.exe -File, without persisting secrets.
& (Join-Path $PSScriptRoot 'start-runtime-9router.ps1')
& (Join-Path $PSScriptRoot 'start-studio.ps1') -NoBrowser:$NoBrowser -SkipInstall:$SkipInstall -SkipBuild:$SkipBuild
