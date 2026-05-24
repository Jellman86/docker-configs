$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

$launcherTaskName = 'WSL Native Docker NPM Launcher'
$portproxyTaskName = 'WSL Native Docker NPM Portproxy'
$taskPath = '\Server Automation\'
$scriptPath = Join-Path $PSScriptRoot 'update-wsl-npm-portproxy.ps1'
$powerShellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$wslExe = Join-Path $env:WINDIR 'System32\wsl.exe'

if (-not (Test-Path $scriptPath)) {
    throw "Missing portproxy update script: $scriptPath"
}

if (-not (Test-Path $powerShellExe)) {
    throw "Missing Windows PowerShell executable: $powerShellExe"
}

if (-not (Test-Path $wslExe)) {
    throw "Missing WSL executable: $wslExe"
}

$launcherAction = New-ScheduledTaskAction `
    -Execute $wslExe `
    -Argument '-d Ubuntu --exec sleep infinity' `
    -WorkingDirectory $PSScriptRoot

$portproxyAction = New-ScheduledTaskAction `
    -Execute $powerShellExe `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$scriptPath`"" `
    -WorkingDirectory $PSScriptRoot

$launcherTrigger = New-ScheduledTaskTrigger -AtLogOn
$launcherTrigger.Delay = 'PT30S'

$portproxyTrigger = New-ScheduledTaskTrigger -AtLogOn
$portproxyTrigger.Delay = 'PT90S'

$launcherPrincipal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$portproxyPrincipal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

$launcherSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$portproxySettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $launcherTaskName `
    -TaskPath $taskPath `
    -Action $launcherAction `
    -Trigger $launcherTrigger `
    -Principal $launcherPrincipal `
    -Settings $launcherSettings `
    -Description 'Launch Ubuntu WSL and save its NAT address for the NPM portproxy task.' `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName $portproxyTaskName `
    -TaskPath $taskPath `
    -Action $portproxyAction `
    -Trigger $portproxyTrigger `
    -Principal $portproxyPrincipal `
    -Settings $portproxySettings `
    -Description 'Refresh Windows portproxy rules for native Docker NPM running inside Ubuntu WSL.' `
    -Force | Out-Null

Start-ScheduledTask -TaskName $launcherTaskName -TaskPath $taskPath
Start-Sleep -Seconds 5
Start-ScheduledTask -TaskName $portproxyTaskName -TaskPath $taskPath
Get-ScheduledTask -TaskPath $taskPath |
    Where-Object { $_.TaskName -in @($launcherTaskName, $portproxyTaskName) } |
    Select-Object TaskPath,TaskName,State
