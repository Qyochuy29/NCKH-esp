. "$PSScriptRoot/Windows-Common.ps1"
foreach($name in @('receiver','ai','backend')) {
    $recordPath=Join-Path $script:Runtime "$name-process.json"
    if(!(Test-Path -LiteralPath $recordPath)) { continue }
    $record=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $process=Get-Process -Id $record.Id -ErrorAction SilentlyContinue
    if($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.StartTicks) {
        Stop-Process -Id $process.Id
    }
    Remove-Item -LiteralPath $recordPath
}
$ErrorActionPreference='Continue'
& "$script:PgBin/pg_ctl.exe" status -D $script:PgData *> $null
if($LASTEXITCODE -eq 0) {
    & "$script:PgBin/pg_ctl.exe" stop -D $script:PgData -m fast -w
    if($LASTEXITCODE -ne 0) { throw 'Khong dung duoc PostgreSQL. Xem log.' }
}
Write-Host 'Da tat website. Du lieu duoc giu lai.'
