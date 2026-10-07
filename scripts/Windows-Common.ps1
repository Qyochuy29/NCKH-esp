$ErrorActionPreference = 'Stop'
$script:Root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $script:Root
$script:Runtime = Join-Path $script:Root '.runtime'
$script:PgBin = Join-Path $script:Runtime 'postgresql/pgsql/bin'
$script:PgData = Join-Path $script:Runtime 'pgdata'
$script:Python = Join-Path $script:Root '.venv/Scripts/python.exe'
$script:Dotnet = Join-Path $env:ProgramFiles 'dotnet/dotnet.exe'
New-Item -ItemType Directory -Path "$script:Runtime/logs" -Force | Out-Null
$settingsPath = Join-Path $script:Runtime 'windows-settings.json'
if (!(Test-Path -LiteralPath $settingsPath)) {
    function New-WindowsSecret {
        $bytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        return -join ($bytes | ForEach-Object { $_.ToString('x2') })
    }
    $original = Get-Content "$script:Root/backend-csharp/appsettings.json" -Raw | ConvertFrom-Json
    $settings = @{ DatabasePassword=(New-WindowsSecret); JwtSecret=(New-WindowsSecret); RefreshSecret=(New-WindowsSecret); DeviceToken=$original.DeviceToken; DatabasePort=5433; WebPort=3000; AiPort=5000 }
    [IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
}
$script:Settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json

function Invoke-Native([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed: $LASTEXITCODE" }
}

function Wait-Website([string]$Url, [int]$Seconds=120) {
    $deadline=(Get-Date).AddSeconds($Seconds)
    do {
        try { $response=Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3; if($response.StatusCode -eq 200) { return } } catch {}
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "Khong san sang: $Url. Xem log trong .runtime/logs."
}

function Start-Managed([string]$Name, [string]$Exe, [string]$Arguments, [string]$WorkingDirectory) {
    $recordPath=Join-Path $script:Runtime "$Name-process.json"
    if(Test-Path -LiteralPath $recordPath) {
        $record=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
        $existing=Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        if($existing -and $existing.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.StartTicks) { return }
    }
    $process=Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -RedirectStandardOutput "$script:Runtime/logs/$Name.log" -RedirectStandardError "$script:Runtime/logs/$Name-error.log" -PassThru
    @{ Id=$process.Id; StartTicks=$process.StartTime.ToUniversalTime().Ticks.ToString() } | ConvertTo-Json | Set-Content -LiteralPath $recordPath
}

function Set-WindowsEnvironment {
    $env:PATH = $env:PATH + ';' + [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    $ffmpeg = Get-ChildItem "$env:LOCALAPPDATA/Microsoft/WinGet/Packages","$env:ProgramFiles/WinGet/Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if($ffmpeg) { $env:PATH = $ffmpeg.DirectoryName + ';' + $env:PATH }
    $env:ConnectionStrings__DefaultConnection="Host=127.0.0.1;Port=$($script:Settings.DatabasePort);Database=school_guardian;Username=sguser;Password=$($script:Settings.DatabasePassword)"
    $env:Jwt__Secret=$script:Settings.JwtSecret
    $env:Jwt__RefreshSecret=$script:Settings.RefreshSecret
    $env:DeviceToken=$script:Settings.DeviceToken
    $env:DEVICE_TOKEN=$script:Settings.DeviceToken
    $env:ASPNETCORE_URLS="http://0.0.0.0:$($script:Settings.WebPort)"
    $env:ASPNETCORE_ENVIRONMENT='Production'
    $env:Frontend__Path=Join-Path $script:Root 'frontend'
    $env:UPLOAD_DIR=Join-Path $script:Root 'backend-csharp/uploads'
    New-Item -ItemType Directory -Path $env:UPLOAD_DIR -Force | Out-Null
    $env:Storage__AudioPath=$env:UPLOAD_DIR
    $env:AiService__Url="http://127.0.0.1:$($script:Settings.AiPort)"
    $env:BACKEND_URL="http://127.0.0.1:$($script:Settings.WebPort)/api/alerts/analyze-existing"
    $env:WHISPER_DEVICE=if($script:Settings.WhisperDevice) { $script:Settings.WhisperDevice } else { 'auto' }
    $env:WHISPER_MODEL_SIZE=if($script:Settings.WhisperModel) { $script:Settings.WhisperModel } else { 'medium' }
    $env:ASR_MODE=if($script:Settings.AsrMode) { $script:Settings.AsrMode } else { 'local' }
    $env:REASONING_MODE=if($script:Settings.ReasoningMode) { $script:Settings.ReasoningMode } else { 'rules' }
    $env:TFHUB_CACHE_DIR=Join-Path $script:Runtime 'cache/tfhub'
    $env:HF_HOME=Join-Path $script:Runtime 'cache/huggingface'
    $env:PYTHONUNBUFFERED='1'
}
