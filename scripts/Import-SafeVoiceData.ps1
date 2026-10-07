param([string]$DatabaseDump, [string]$AudioDirectory)
. "$PSScriptRoot/Docker-Common.ps1"
if (!$DatabaseDump -and !$AudioDirectory) { throw 'Can -DatabaseDump (pg_dump -Fc) va/hoac -AudioDirectory.' }
if ($DatabaseDump) { $DatabaseDump = (Resolve-Path -LiteralPath $DatabaseDump).Path }
if ($AudioDirectory) {
    $AudioDirectory = (Resolve-Path -LiteralPath $AudioDirectory).Path
    if (!(Test-Path -LiteralPath $AudioDirectory -PathType Container)) { throw 'AudioDirectory phai la thu muc.' }
}
Initialize-Settings
Assert-DockerEngine
$composeArgs = @(Get-ComposeArguments)
$running = @(& $script:DockerExe @composeArgs ps --services --status running)
if ($running | Where-Object { $_ -in @('backend', 'ai-service', 'audio-receiver') }) {
    throw 'Tat website bang Tat_He_Thong.bat truoc khi nhap du lieu.'
}
Invoke-Docker @composeArgs up -d --wait postgres
if ($DatabaseDump) {
    $tableCount = & $script:DockerExe @composeArgs exec -T postgres psql -U sguser -d school_guardian -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
    if ($LASTEXITCODE -ne 0) { throw 'Khong kiem tra duoc database dich.' }
    if ([int]$tableCount -ne 0) { throw 'Database Docker da co bang. Khong ghi de du lieu; nhap vao database moi truoc lan khoi dong dau tien.' }
    Invoke-Docker @composeArgs cp $DatabaseDump postgres:/tmp/import.dump
    Invoke-Docker @composeArgs exec -T postgres pg_restore -U sguser -d school_guardian --no-owner --no-privileges --single-transaction /tmp/import.dump
}
if ($AudioDirectory) {
    if (!(Test-DockerImage 'safevoice-ai:local')) {
        Invoke-Docker compose -f docker-compose.yml build ai-service
    }
    # Validate against collisions first; copy only into an empty shared volume.
    Invoke-Docker compose -f docker-compose.yml run --rm --no-deps --entrypoint python -v "${AudioDirectory}:/source:ro" ai-service -c "import pathlib,shutil; src=pathlib.Path('/source'); dst=pathlib.Path('/tai-lieu'); assert not any(dst.iterdir()), 'Audio volume is not empty'; shutil.copytree(src,dst,dirs_exist_ok=True)"
}
Write-Host 'Da nhap du lieu. Chay Chay_He_Thong.bat de bat website.'
