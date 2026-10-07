. "$PSScriptRoot/Docker-Common.ps1"
Assert-DockerEngine
$composeArgs = @(Get-ComposeArguments)
Invoke-Docker @composeArgs stop
Write-Host 'Da tat SafeVoice. Database, audio va model AI duoc giu lai.'
