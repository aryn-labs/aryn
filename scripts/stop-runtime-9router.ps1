[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$arynRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$arynRecordPath = Join-Path $arynRoot '.local\runtime-process.json'
if (-not (Test-Path -LiteralPath $arynRecordPath)) {
    Write-Host 'Tidak ada ARYN Runtime yang dikelola launcher 9Router.'
    return
}
$arynRecord = Get-Content -LiteralPath $arynRecordPath -Raw | ConvertFrom-Json
$arynProcess = Get-Process -Id $arynRecord.pid -ErrorAction SilentlyContinue
if ($arynProcess) {
    $arynInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($arynProcess.Id)"
    if ($arynProcess.StartTime.ToUniversalTime().Ticks -ne ([datetime]$arynRecord.started).ToUniversalTime().Ticks -or
        $arynInfo.CommandLine -notlike '*hermes-9router.py*') {
        throw 'Identitas proses tidak cocok; runtime tidak dihentikan.'
    }
    Stop-Process -Id $arynProcess.Id
    Write-Host 'ARYN Runtime dihentikan. Core akan menandai run terputus saat restart tanpa mengklaim pembatalan berhasil.'
} else {
    Write-Host 'Proses ARYN Runtime sudah tidak berjalan.'
}
Remove-Item -LiteralPath $arynRecordPath
