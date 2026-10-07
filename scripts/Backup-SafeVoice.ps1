. "$PSScriptRoot/Docker-Common.ps1"
Assert-DockerEngine
$composeArgs = @(Get-ComposeArguments)
$destination = Join-Path $script:ProjectRoot ('backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $destination | Out-Null
$running = @(& $script:DockerExe @composeArgs ps --services --status running)
if ($LASTEXITCODE -ne 0 -or $running -notcontains 'postgres') { throw 'Bat he thong truoc khi sao luu.' }
$writers = @($running | Where-Object { $_ -in @('backend', 'audio-receiver', 'ai-service', 'redis') })
try {
    # Quiesce writers to keep database URLs and audio files consistent.
    if ($writers.Count) { Invoke-Docker @composeArgs stop @writers }
    Invoke-Docker @composeArgs exec -T postgres pg_dump -U sguser -d school_guardian -Fc -f /tmp/safevoice.dump
    Invoke-Docker @composeArgs cp postgres:/tmp/safevoice.dump (Join-Path $destination 'database.dump')
    Invoke-Docker @composeArgs run --rm --no-deps --entrypoint tar -v "${destination}:/backup" ai-service -czf /backup/audio.tar.gz -C /tai-lieu .
    Invoke-Docker @composeArgs run --rm --no-deps --entrypoint tar -v "${destination}:/backup" ai-service -czf /backup/ai-cache.tar.gz -C /root/.cache .
    Invoke-Docker @composeArgs run --rm --no-deps --entrypoint tar -v "${destination}:/backup" redis -czf /backup/redis.tar.gz -C /data .
    Invoke-Docker @composeArgs run --rm --no-deps --entrypoint tar -v "${destination}:/backup" backend -czf /backup/keys.tar.gz -C /root/.aspnet/DataProtection-Keys .
    Copy-Item -LiteralPath '.env' -Destination (Join-Path $destination '.env')
    Write-Host "Da sao luu database, audio, cache AI/Redis, keys va cau hinh: $destination"
} finally {
    if ($writers.Count) { Invoke-Docker @composeArgs start @writers }
}
