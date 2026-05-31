$ErrorActionPreference = "Stop"

$TaskName = "Start Docker Compose Stacks"
$TaskPath = "\Server Automation\"
$TaskFolderPath = "\Server Automation"
$StartupScript = Join-Path $PSScriptRoot "start-stacks-on-boot.ps1"
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$ScheduleService = New-Object -ComObject "Schedule.Service"
$ScheduleService.Connect()
$RootFolder = $ScheduleService.GetFolder("\")
try {
    $null = $ScheduleService.GetFolder($TaskFolderPath)
} catch {
    try {
        $null = $RootFolder.CreateFolder("Server Automation")
    } catch {
        if ($_.Exception.HResult -ne -2147024713) {
            throw
        }
    }
}

try {
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath "\" -Confirm:$false -ErrorAction Stop
} catch {
    # Task was not registered at the root path.
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartupScript`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Start Docker Desktop and Compose stacks in WSL after login, with gluetun first." `
    -Force

Write-Host "Registered scheduled task: $TaskPath$TaskName"
Write-Host "Startup script: $StartupScript"
Write-Host "Logon user: $CurrentUser"
