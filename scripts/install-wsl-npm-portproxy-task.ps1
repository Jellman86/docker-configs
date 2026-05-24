$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

$taskName = 'WSL Native Docker NPM Portproxy'
$taskPath = '\Server Automation\'
$scriptPath = Join-Path $PSScriptRoot 'update-wsl-npm-portproxy.ps1'

if (-not (Test-Path $scriptPath)) {
    throw "Missing portproxy update script: $scriptPath"
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = 'PT30S'

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask `
    -TaskName $taskName `
    -TaskPath $taskPath `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'Refresh Windows portproxy rules for native Docker NPM running inside Ubuntu WSL.' `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName -TaskPath $taskPath
Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Select-Object TaskPath,TaskName,State
