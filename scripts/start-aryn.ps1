[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$arynRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

. (Join-Path $PSScriptRoot 'aryn-config.ps1')
Initialize-ArynConfiguration -Root $arynRoot
if ($env:ARYN_ENV -ne 'development') { throw 'Launcher gabungan khusus Local development; gunakan hosted OIDC entrypoint.' }
if ($env:ARYN_AUTH_MODE -and $env:ARYN_AUTH_MODE -ne 'local-development') { throw 'Local launcher tidak mengganti authentication mode yang telah dipilih.' }
# API_SERVER_KEY is inherited by both Runtime and Studio; never written to a file.
Initialize-ArynRuntimeAuthentication
& (Join-Path $PSScriptRoot 'start-runtime-9router.ps1') -CheckOnly:$CheckOnly
& (Join-Path $PSScriptRoot 'start-studio.ps1') -NoBrowser:$NoBrowser -SkipInstall:$SkipInstall -SkipBuild:$SkipBuild -CheckOnly:$CheckOnly
