param([switch]$NoBrowser)
. "$PSScriptRoot/Windows-Common.ps1"
Set-WindowsEnvironment
if(!(Test-Path $script:Python) -or !(Test-Path "$script:Runtime/backend/SchoolGuardian.Api.dll")) { throw 'Chay Cai_Dat_Website.bat truoc.' }
$probePreference=$ErrorActionPreference
$ErrorActionPreference='Continue'
& "$script:PgBin/pg_ctl.exe" status -D $script:PgData *> $null
$pgRunning=$LASTEXITCODE -eq 0
$ErrorActionPreference=$probePreference
if(!$pgRunning) {
    Invoke-Native "$script:PgBin/pg_ctl.exe" @('start','-D',$script:PgData,'-l',"$script:Runtime/logs/postgres.log",'-w','-t','60')
}
$env:PGPASSWORD=$script:Settings.DatabasePassword
$dbExists=& "$script:PgBin/psql.exe" -h 127.0.0.1 -p $script:Settings.DatabasePort -U sguser -d postgres -At -c "SELECT 1 FROM pg_database WHERE datname='school_guardian';"
if($LASTEXITCODE -ne 0) { throw 'Khong ket noi duoc PostgreSQL.' }
if($dbExists -ne '1') {
    Invoke-Native "$script:PgBin/createdb.exe" @('-h','127.0.0.1','-p',"$($script:Settings.DatabasePort)",'-U','sguser','school_guardian')
}
Start-Managed 'backend' $script:Dotnet ('"' + "$script:Runtime/backend/SchoolGuardian.Api.dll" + '"') "$script:Root/backend-csharp"
Wait-Website "http://127.0.0.1:$($script:Settings.WebPort)/health"
Write-Host 'Backend va database da san sang. Dang tai/khoi dong model AI...'
Start-Managed 'ai' $script:Python "-m waitress --listen=127.0.0.1:$($script:Settings.AiPort) --threads=1 server:app" "$script:Root/ai-training"
Wait-Website "http://127.0.0.1:$($script:Settings.AiPort)/health" 1200
Start-Managed 'receiver' $script:Python 'websocket_receiver.py' "$script:Root/websocket"
$url="http://localhost:$($script:Settings.WebPort)/dang-nhap.html"
Write-Host "Website va AI san sang: $url"
if(!$NoBrowser) { Start-Process $url }
