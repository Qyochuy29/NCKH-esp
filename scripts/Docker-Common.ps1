$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $script:ProjectRoot

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$candidates = @(
    "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
    "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe"
)
$script:DockerExe = if ($dockerCommand) { $dockerCommand.Source } else {
    $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (!$script:DockerExe) { throw 'Chua tim thay Docker Desktop. Cai Docker Desktop va bat WSL 2 truoc.' }

function Invoke-Docker {
    & $script:DockerExe @args
    if ($LASTEXITCODE -ne 0) { throw "Docker failed (exit $LASTEXITCODE)." }
}

function Initialize-Settings {
    $envPath = Join-Path $script:ProjectRoot '.env'
    if (Test-Path -LiteralPath $envPath) { return }
    function New-Secret {
        $bytes = New-Object byte[] 48
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        return -join ($bytes | ForEach-Object { $_.ToString('x2') })
    }
    $token = 'your_secure_device_token_123'
    $configPath = Join-Path $script:ProjectRoot 'backend-csharp/appsettings.json'
    if (Test-Path -LiteralPath $configPath) {
        $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        if ($config.DeviceToken) { $token = $config.DeviceToken }
    }
    $lines = @(
        "POSTGRES_PASSWORD=$(New-Secret)",
        "JWT_SECRET=$(New-Secret)",
        "JWT_REFRESH_SECRET=$(New-Secret)",
        "DEVICE_TOKEN=$token",
        'WEB_PORT=3000', 'AUDIO_PORT=8765', 'WHISPER_MODEL_SIZE=medium', 'WHISPER_DEVICE=auto',
        'ASR_MODE=local', 'REASONING_MODE=rules', 'GROQ_API_KEY='
    )
    [System.IO.File]::WriteAllLines($envPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'Da tao .env voi mat khau/JWT rieng. Giu lai file nay cung du lieu Docker.'
}

function Assert-DockerEngine {
    if (!(Test-DockerEngine)) { throw 'Docker Engine chua san sang. Mo Docker Desktop, bat Linux containers/WSL 2, roi thu lai. Neu vua bat WSL, can khoi dong lai Windows.' }
}

function Test-DockerEngine {
    $ErrorActionPreference = 'Continue'
    $engineType = & $script:DockerExe info --format '{{.OSType}}' 2>$null
    return ($LASTEXITCODE -eq 0 -and $engineType -eq 'linux')
}

function Test-DockerImage([string]$Name) {
    $ErrorActionPreference = 'Continue'
    & $script:DockerExe image inspect $Name *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-ComposeArguments {
    $arguments = @('compose', '-f', 'docker-compose.yml')
    if (Test-Path -LiteralPath (Join-Path $script:ProjectRoot '.docker-gpu')) {
        $arguments += @('-f', 'docker-compose.gpu.yml')
    }
    return $arguments
}
