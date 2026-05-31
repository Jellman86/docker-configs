$ErrorActionPreference = "Stop"

$TaskName = "Daily Midnight Shutdown"
$TaskPath = "\Server Automation\"
$TaskFolderPath = "\Server Automation"

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

$Action = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\shutdown.exe" `
    -Argument '/s /t 60 /c "Scheduled midnight shutdown. Save your work now."'

$Trigger = New-ScheduledTaskTrigger -Daily -At "00:00"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Shut down this PC every day at 00:00." `
    -Force

Write-Host "Registered scheduled task: $TaskPath$TaskName"
