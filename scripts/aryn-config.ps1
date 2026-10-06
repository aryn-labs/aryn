# Shared launcher configuration. Python owns validation and development defaults.
function Initialize-ArynConfiguration {
    param([string]$Root, [string]$Python)
    $envFile = Join-Path $Root '.env'
    if (Test-Path -LiteralPath $envFile) {
        Get-Content -LiteralPath $envFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith('#') -and $line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $name = $matches[1]
                # Runtime authentication is ephemeral, never loaded from .env.
                if ($name -ne 'API_SERVER_KEY' -and -not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) {
                    Set-Item "env:$name" $matches[2]
                }
            }
        }
    }
    if (-not $Python) {
        $Python = Join-Path $Root '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $Python)) {
            $Python = (Get-Command python.exe -ErrorAction Stop).Source
        }
    }
    Push-Location $Root
    try {
        $configuration = & $Python -m packages.config
        if ($LASTEXITCODE -ne 0) { throw 'Centralized settings menolak konfigurasi launcher.' }
        $settings = $configuration | ConvertFrom-Json
        foreach ($property in $settings.PSObject.Properties) {
            Set-Item "env:$($property.Name)" ([string]$property.Value)
        }
    } finally { Pop-Location }
}

function Initialize-ArynRuntimeAuthentication {
    if (-not $env:API_SERVER_KEY) {
        $arynKeyBytes = New-Object byte[] 32
        $arynRandom = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $arynRandom.GetBytes($arynKeyBytes) } finally { $arynRandom.Dispose() }
        $env:API_SERVER_KEY = [Convert]::ToBase64String($arynKeyBytes)
    }
}
