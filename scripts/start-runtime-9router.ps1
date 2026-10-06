[CmdletBinding()]
param(
    [string]$HermesSource = (Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent'),
    [ValidateRange(1024, 65535)][int]$Port = 0,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$arynRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'aryn-config.ps1')
Initialize-ArynConfiguration -Root $arynRoot
$arynHermesSource = (Resolve-Path -LiteralPath $HermesSource).Path
$arynHermesCommand = (Get-Command hermes.exe -ErrorAction Stop).Source
$arynRuntimeCommand = (& $arynHermesCommand --print-runtime-command | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $arynRuntimeCommand[0])) {
    throw 'Interpreter instalasi Hermes belum tersedia.'
}

# Determine runtime host and port from ARYN_RUNTIME_BASE_URL or -Port
$runtimeUri = [System.Uri]$env:ARYN_RUNTIME_BASE_URL
$runtimeHost = $runtimeUri.Host.ToLowerInvariant()
if ($runtimeHost -notin @('127.0.0.1', 'localhost', '::1')) {
    throw "Runtime lokal hanya mengizinkan host loopback. Host '$runtimeHost' ditolak."
}
if ($runtimeUri.Scheme -notin @('http', 'https')) {
    throw "Skema runtime harus http atau https."
}
if ($runtimeUri.UserInfo) {
    throw "Kredensial dalam runtime URL ditolak."
}
if ($runtimeUri.Query -or ($env:ARYN_RUNTIME_BASE_URL -match '\?')) {
    throw "Query parameters dalam runtime URL ditolak."
}

$configuredPort = $runtimeUri.Port
if ($Port -eq 0) {
    $Port = $configuredPort
} elseif ($Port -ne $configuredPort) {
    $runtimeOverride = New-Object System.UriBuilder($runtimeUri)
    $runtimeOverride.Port = $Port
    $env:ARYN_RUNTIME_BASE_URL = $runtimeOverride.Uri.AbsoluteUri.TrimEnd('/')
    Initialize-ArynConfiguration -Root $arynRoot
}

# API_SERVER_KEY remains process-only authentication.
Initialize-ArynRuntimeAuthentication
$arynEntry = Join-Path $PSScriptRoot 'hermes-9router.py'
& $arynRuntimeCommand[0] -I $arynEntry --hermes-source $arynHermesSource --port $Port --check
if ($LASTEXITCODE -ne 0) { throw 'Integrasi Hermes belum kompatibel atau confinement belum valid.' }
if ($CheckOnly) { return }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port runtime $Port sedang digunakan. Hentikan runtime lama secara sengaja; launcher tidak menggantinya otomatis."
}
$arynLocal = Join-Path $arynRoot '.local'
New-Item -ItemType Directory -Path $arynLocal -Force | Out-Null
$arynArguments = @('-I', ('"' + $arynEntry + '"'), '--hermes-source', ('"' + $arynHermesSource + '"'), '--port', "$Port")
$arynProcess = Start-Process -FilePath $arynRuntimeCommand[0] -ArgumentList $arynArguments -WorkingDirectory $arynRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $arynLocal 'runtime.stdout.log') -RedirectStandardError (Join-Path $arynLocal 'runtime.stderr.log')
$arynReady = $false
$gatewayCheckUri = "$($env:ARYN_RUNTIME_BASE_URL.TrimEnd('/'))/aryn/gateway"
for ($arynAttempt = 0; $arynAttempt -lt 40; $arynAttempt++) {
    if ($arynProcess.HasExited) { throw 'ARYN Runtime berhenti sebelum siap. Periksa log runtime lokal.' }
    try {
        $arynBinding = Invoke-RestMethod -Uri $gatewayCheckUri -Headers @{Authorization="Bearer $env:API_SERVER_KEY"} -TimeoutSec 2
        if ($arynBinding.gateway -eq '9Router' -and $arynBinding.runtime_backend -eq 'Hermes' -and
            $arynBinding.exact_model_enforced -eq $true -and $arynBinding.base_url -eq $env:ARYN_9ROUTER_BASE_URL.TrimEnd('/')) {
            $arynReady = $true
            break
        }
    } catch { Start-Sleep -Milliseconds 250 }
}
if (-not $arynReady) {
    Stop-Process -Id $arynProcess.Id -ErrorAction SilentlyContinue
    throw 'Routing ARYN Runtime ke 9Router belum dapat diverifikasi. Periksa log runtime lokal.'
}
@{pid=$arynProcess.Id;port=$Port;started=$arynProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $arynLocal 'runtime-process.json')
Write-Host "ARYN Runtime dimulai melalui Hermes pada port $Port dengan gateway 9Router."
Write-Host 'Jalankan start-studio.ps1 dari sesi PowerShell yang sama agar autentikasi runtime cocok.'
