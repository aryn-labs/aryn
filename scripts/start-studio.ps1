[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8710,
    [switch]$NoBrowser,
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$UseSystemPython
)
$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$studioLocal = Join-Path $studioRoot '.local'
New-Item -ItemType Directory -Path $studioLocal -Force | Out-Null
$studioUrl = "http://127.0.0.1:$Port"
$studioPidFile = Join-Path $studioLocal 'studio-process.json'
$studioExisting = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($studioExisting) {
    if (Test-Path -LiteralPath $studioPidFile) {
        $studioRecord = Get-Content -LiteralPath $studioPidFile -Raw | ConvertFrom-Json
        $studioRecordedProcess = Get-Process -Id $studioRecord.pid -ErrorAction SilentlyContinue
        if ($studioRecord.port -eq $Port -and $studioExisting.OwningProcess -contains $studioRecord.pid -and $studioRecordedProcess -and $studioRecordedProcess.StartTime.ToUniversalTime().Ticks -eq ([datetime]$studioRecord.started).ToUniversalTime().Ticks) {
            Write-Host "ARYN Studio sudah berjalan: $studioUrl"
            if (-not $NoBrowser) { Start-Process $studioUrl }
            return
        }
    }
    throw "Port $Port sedang digunakan proses lain. Pilih -Port yang berbeda."
}
Push-Location $studioRoot
try {
    if ($UseSystemPython) {
        $studioPython = (Get-Command python.exe -ErrorAction Stop).Source
    } else {
        $studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $studioPython)) {
            & python -m venv (Join-Path $studioRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Pembuatan virtual environment Python gagal.' }
        }
    }
    if (-not $SkipInstall) {
        & $studioPython -m pip install -e '.[dev]'
        if ($LASTEXITCODE -ne 0) { throw 'Instalasi dependensi API gagal.' }
    }
    Push-Location (Join-Path $studioRoot 'apps\web')
    try {
        if (-not $SkipInstall) {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'Instalasi dependensi frontend gagal.' }
        }
        if (-not $SkipBuild) {
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Build frontend gagal.' }
        }
    } finally { Pop-Location }
    $studioProcess = Start-Process -FilePath $studioPython -ArgumentList @('-m','services.api','--port',"$Port") -WorkingDirectory $studioRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $studioLocal 'studio.stdout.log') -RedirectStandardError (Join-Path $studioLocal 'studio.stderr.log')
    @{pid=$studioProcess.Id;port=$Port;started=$studioProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $studioPidFile
    $studioReady = $false
    for ($studioAttempt = 0; $studioAttempt -lt 60; $studioAttempt++) {
        if ($studioProcess.HasExited) { throw "API berhenti. Periksa $studioLocal\studio.stderr.log" }
        try {
            $studioResponse = Invoke-WebRequest -Uri $studioUrl -UseBasicParsing -TimeoutSec 2
            if ($studioResponse.StatusCode -eq 200) { $studioReady = $true; break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $studioReady) { throw "API belum siap. Periksa $studioLocal\studio.stderr.log" }
    # Windows virtualenv's python.exe can delegate to a child interpreter. Track
    # the actual loopback listener so stop/restart never leaves the API orphaned.
    $studioListener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen | Select-Object -First 1
    $studioListenerProcess = Get-Process -Id $studioListener.OwningProcess
    $studioListenerInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($studioListenerProcess.Id)"
    if ($studioListenerProcess.Id -ne $studioProcess.Id -and $studioListenerInfo.ParentProcessId -ne $studioProcess.Id) {
        throw 'Listener tidak cocok dengan proses Studio yang dijalankan launcher.'
    }
    @{pid=$studioListenerProcess.Id;port=$Port;started=$studioListenerProcess.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $studioPidFile
    Write-Host "ARYN Studio siap: $studioUrl"
    Write-Host 'Sesi development lokal. Identitas dan kredensial runtime tetap di server.'
    Write-Host 'Hentikan dengan .\scripts\stop-studio.ps1'
    if (-not $NoBrowser) { Start-Process $studioUrl }
} finally { Pop-Location }
