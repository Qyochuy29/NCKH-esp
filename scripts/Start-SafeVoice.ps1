param([switch]$Rebuild, [switch]$Gpu, [switch]$Cpu, [switch]$NoBrowser)
. "$PSScriptRoot/Docker-Common.ps1"
if ($Gpu -and $Cpu) { throw 'Chi chon Gpu hoac Cpu.' }
Initialize-Settings

if (!(Test-DockerEngine)) {
    $desktopPaths = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    )
    $desktop = $desktopPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (!$desktop) { throw 'Khong tim thay Docker Desktop.' }
    Write-Host 'Dang mo Docker Desktop...'
    Start-Process -FilePath $desktop -WindowStyle Hidden
    $deadline = (Get-Date).AddMinutes(3)
    do {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) { break }
    } while ((Get-Date) -lt $deadline)
}
Assert-DockerEngine
if ($Gpu) { [System.IO.File]::WriteAllText((Join-Path $script:ProjectRoot '.docker-gpu'), 'enabled') }
if ($Cpu -and (Test-Path -LiteralPath '.docker-gpu')) { Remove-Item -LiteralPath '.docker-gpu' }
$composeArgs = @(Get-ComposeArguments)
$aiImage = if (Test-Path -LiteralPath '.docker-gpu') { 'safevoice-ai-gpu:local' } else { 'safevoice-ai:local' }
foreach ($image in @('safevoice-web:local', $aiImage, 'safevoice-audio:local')) {
    if (!(Test-DockerImage $image)) { $Rebuild = $true; break }
}
$startArgs = $composeArgs + @('up', '-d', '--wait', '--wait-timeout', '1800')
if ($Rebuild) { $startArgs += '--build' }
Write-Host 'Khoi dong SafeVoice. Lan dau can tai image, thu vien va model AI; co the mat nhieu phut.'
Invoke-Docker @startArgs
Invoke-Docker @composeArgs ps
$portLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^WEB_PORT=' } | Select-Object -First 1
$webPort = if ($portLine) { ($portLine -split '=', 2)[1].Trim() } else { '3000' }
$url = "http://localhost:$webPort/dang-nhap.html"
Write-Host "He thong san sang: $url"
if (!$NoBrowser) { Start-Process $url }
