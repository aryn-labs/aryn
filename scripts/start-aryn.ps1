[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipInstall,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$arynRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# Load .env into process environment so both child services share identical configuration
$envFile = Join-Path $arynRoot '.env'
if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $k = $matches[1]
            $v = $matches[2]
            if (-not (Get-Item "env:$k" -ErrorAction SilentlyContinue)) {
                Set-Item "env:$k" $v
            }
        }
    }
}
if (-not $env:ARYN_ENV) { $env:ARYN_ENV = 'development' }
if (-not $env:ARYN_STUDIO_HOST) { $env:ARYN_STUDIO_HOST = '127.0.0.1' }
if (-not $env:ARYN_STUDIO_PORT) { $env:ARYN_STUDIO_PORT = '8710' }
if (-not $env:ARYN_RUNTIME_BASE_URL) { $env:ARYN_RUNTIME_BASE_URL = 'http://127.0.0.1:8642' }
if (-not $env:ARYN_9ROUTER_BASE_URL) { $env:ARYN_9ROUTER_BASE_URL = 'http://127.0.0.1:20128/v1' }

# Generate ephemeral runtime authentication key inherited by both Runtime and Studio
if (-not $env:API_SERVER_KEY) {
    $arynKeyBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($arynKeyBytes)
    $env:API_SERVER_KEY = [Convert]::ToBase64String($arynKeyBytes)
}

& (Join-Path $PSScriptRoot 'start-runtime-9router.ps1')
& (Join-Path $PSScriptRoot 'start-studio.ps1') -NoBrowser:$NoBrowser -SkipInstall:$SkipInstall -SkipBuild:$SkipBuild
