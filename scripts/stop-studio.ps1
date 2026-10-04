[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$studioPidFile = Join-Path $studioRoot '.local\studio-process.json'
if (-not (Test-Path -LiteralPath $studioPidFile)) { Write-Host 'Tidak ada proses Studio yang dikelola launcher.'; return }
$studioRecord = Get-Content -LiteralPath $studioPidFile -Raw | ConvertFrom-Json
$studioProcess = Get-Process -Id $studioRecord.pid -ErrorAction SilentlyContinue
if ($studioProcess -and $studioProcess.StartTime.ToUniversalTime().Ticks -eq ([datetime]$studioRecord.started).ToUniversalTime().Ticks) {
    Stop-Process -Id $studioProcess.Id
    Write-Host 'ARYN Studio dihentikan. Database tetap tersimpan.'
} else { Write-Host 'Proses Studio sudah tidak berjalan.' }
Remove-Item -LiteralPath $studioPidFile
