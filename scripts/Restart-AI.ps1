. "$PSScriptRoot/Windows-Common.ps1"
Set-WindowsEnvironment
$recordPath=Join-Path $script:Runtime 'ai-process.json'
if(Test-Path -LiteralPath $recordPath) {
    $record=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $process=Get-Process -Id $record.Id -ErrorAction SilentlyContinue
    if($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.StartTicks) {
        Stop-Process -Id $process.Id
        $process.WaitForExit(15000) | Out-Null
    }
    Remove-Item -LiteralPath $recordPath
}
Start-Managed 'ai' $script:Python "-m waitress --listen=127.0.0.1:$($script:Settings.AiPort) --threads=1 server:app" "$script:Root/ai-training"
Wait-Website "http://127.0.0.1:$($script:Settings.AiPort)/health" 1200
Write-Host 'AI da khoi dong lai; backend va database tiep tuc chay.'
