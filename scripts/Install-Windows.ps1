. "$PSScriptRoot/Windows-Common.ps1"
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
function Install-Package([string]$Id) {
    Invoke-Native 'winget.exe' @('install','--id',$Id,'--exact','--source','winget','--accept-package-agreements','--accept-source-agreements','--silent','--disable-interactivity')
}
if(!(Test-Path -LiteralPath $script:Dotnet)) { Install-Package 'Microsoft.DotNet.SDK.9' }
$pythonPaths=@("$env:LOCALAPPDATA/Programs/Python/Python311/python.exe", "$env:ProgramFiles/Python311/python.exe")
$basePython=$pythonPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if(!$basePython) {
    Install-Package 'Python.Python.3.11'
    $basePython=$pythonPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
Set-WindowsEnvironment
if(!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Install-Package 'Gyan.FFmpeg'; Set-WindowsEnvironment }
if(!(Test-Path -LiteralPath "$script:PgBin/initdb.exe")) {
    New-Item -ItemType Directory -Path "$script:Runtime/downloads" -Force | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri 'https://get.enterprisedb.com/postgresql/postgresql-15.19-1-windows-x64-binaries.zip' -OutFile "$script:Runtime/downloads/postgresql.zip"
    Expand-Archive -LiteralPath "$script:Runtime/downloads/postgresql.zip" -DestinationPath "$script:Runtime/postgresql" -Force
}
if(!$basePython -or !(Test-Path -LiteralPath $script:Dotnet)) { throw 'Can cai Python 3.11 va .NET SDK 9 truoc.' }
if(!(Test-Path -LiteralPath $script:Python)) { Invoke-Native $basePython @('-m','venv',"$script:Root/.venv") }
Invoke-Native $script:Python @('-m','pip','install','--upgrade','pip')
Invoke-Native $script:Python @('-m','pip','install','-r',"$script:Root/ai-training/requirements-windows.txt")
Invoke-Native $script:Dotnet @('publish',"$script:Root/backend-csharp/SchoolGuardian.Api.csproj",'-c','Release','-o',"$script:Runtime/backend")
if(!(Test-Path -LiteralPath "$script:PgData/PG_VERSION")) {
    if(!(Test-Path -LiteralPath "$script:PgBin/initdb.exe")) { throw 'Chua co PostgreSQL binaries trong .runtime/postgresql.' }
    $passwordFile=Join-Path $script:Runtime 'init-password.tmp'
    try {
        [IO.File]::WriteAllText($passwordFile,$script:Settings.DatabasePassword,(New-Object Text.UTF8Encoding($false)))
        Invoke-Native "$script:PgBin/initdb.exe" @('-D',$script:PgData,'-U','sguser','--pwfile',$passwordFile,'--auth=scram-sha-256','--encoding=UTF8','--locale=C')
    } finally { if(Test-Path -LiteralPath $passwordFile) { Remove-Item -LiteralPath $passwordFile } }
    Add-Content -LiteralPath "$script:PgData/postgresql.conf" -Value "`nlisten_addresses = '127.0.0.1'`nport = $($script:Settings.DatabasePort)"
}
Write-Host 'Da cai xong thu vien va build backend. Chay Chay_Website_Windows.bat.'
