$ErrorActionPreference = "Stop"

$Distro = $env:WSL_DISTRO
if ([string]::IsNullOrWhiteSpace($Distro)) {
    $Distro = "Ubuntu"
}

$ScriptPath = "/mnt/c/Users/ServerAdmin/Documents/GitHub/docker-configs/scripts/start-stacks-on-boot.sh"
$LogDir = "$env:USERPROFILE\docker-startup-logs"
$LogFile = Join-Path $LogDir ("docker-stacks-startup-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$InitialDelaySeconds = 30

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-StartupLog {
    param([string]$Message)

    $Line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding utf8
}

Write-StartupLog "Docker stack startup task is running."
Write-StartupLog "Log file: $LogFile"

$DockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
if (Test-Path $DockerDesktop) {
    Write-StartupLog "Launching Docker Desktop if it is not already running."
    Start-Process -FilePath $DockerDesktop -WindowStyle Minimized
} else {
    Write-StartupLog "Docker Desktop executable was not found at: $DockerDesktop"
}

Write-StartupLog "Waiting $InitialDelaySeconds seconds before starting WSL orchestration."
Start-Sleep -Seconds $InitialDelaySeconds

Write-StartupLog "Starting WSL orchestration in distro: $Distro"
& wsl.exe -d $Distro -- bash -lc "chmod +x '$ScriptPath' && '$ScriptPath' 2>&1" 2>&1 |
    ForEach-Object {
        $Line = $_.ToString()
        Write-Host $Line
        Add-Content -Path $LogFile -Value $Line -Encoding utf8
    }

$ExitCode = $LASTEXITCODE
Write-StartupLog "WSL orchestration exited with code $ExitCode."

exit $ExitCode
