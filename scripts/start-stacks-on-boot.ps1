$ErrorActionPreference = "Stop"

$Distro = $env:WSL_DISTRO
if ([string]::IsNullOrWhiteSpace($Distro)) {
    $Distro = "Ubuntu"
}

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir
$LogDir = "$env:USERPROFILE\docker-startup-logs"
$LogFile = Join-Path $LogDir ("docker-stacks-startup-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$InitialDelaySeconds = 30
$LockWhenComplete = $env:LOCK_AFTER_DOCKER_STARTUP -ne "0"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function ConvertTo-WslPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $FullPath = [System.IO.Path]::GetFullPath($Path)
    if ($FullPath -match '^([A-Za-z]):\\(.*)$') {
        $Drive = $Matches[1].ToLowerInvariant()
        $Rest = $Matches[2] -replace '\\', '/'
        return "/mnt/$Drive/$Rest"
    }

    throw "Unable to convert path to WSL format: $Path"
}

function Quote-BashString {
    param([Parameter(Mandatory = $true)][string]$Value)

    return "'" + ($Value -replace "'", "'\''") + "'"
}

function Write-StartupLog {
    param([string]$Message)

    $Line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $Line
    Add-Content -Path $LogFile -Value $Line -Encoding utf8
}

Write-StartupLog "Docker stack startup task is running."
Write-StartupLog "Log file: $LogFile"

$WslScriptPath = ConvertTo-WslPath (Join-Path $ScriptDir "start-stacks-on-boot.sh")
$WslRepoRoot = ConvertTo-WslPath $RepoRoot
Write-StartupLog "Repo root: $RepoRoot"
Write-StartupLog "WSL repo root: $WslRepoRoot"

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
$QuotedScriptPath = Quote-BashString $WslScriptPath
$QuotedRepoRoot = Quote-BashString $WslRepoRoot
& wsl.exe -d $Distro -- bash -lc "chmod +x $QuotedScriptPath && ROOT=$QuotedRepoRoot $QuotedScriptPath 2>&1" 2>&1 |
    ForEach-Object {
        $Line = $_.ToString()
        Write-Host $Line
        Add-Content -Path $LogFile -Value $Line -Encoding utf8
    }

$ExitCode = $LASTEXITCODE
Write-StartupLog "WSL orchestration exited with code $ExitCode."

if ($LockWhenComplete) {
    Write-StartupLog "Locking workstation so another user can sign in without stopping Docker."
    rundll32.exe user32.dll,LockWorkStation
}

exit $ExitCode
