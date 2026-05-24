$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    throw 'Run this script from an elevated Windows PowerShell session.'
}

$listenAddress = '0.0.0.0'
$ports = @(80, 81, 443)
$distro = 'Ubuntu'

$wslIp = $null
for ($attempt = 1; $attempt -le 30; $attempt++) {
    $wslIp = (& wsl.exe -d $distro hostname -I).Trim().Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries) |
        Where-Object { $_ -match '^172\.30\.' } |
        Select-Object -First 1

    if ($wslIp) {
        break
    }

    Start-Sleep -Seconds 2
}

if (-not $wslIp) {
    throw "Could not find the $distro WSL NAT address."
}

foreach ($port in $ports) {
    netsh interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$port | Out-Null
    netsh interface portproxy add v4tov4 listenaddress=$listenAddress listenport=$port connectaddress=$wslIp connectport=$port | Out-Null
}

$ruleName = 'WSL Native Docker NPM'
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existingRule) {
    Remove-NetFirewallRule -DisplayName $ruleName
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $ports `
    -Profile Any | Out-Null

for ($attempt = 1; $attempt -le 30; $attempt++) {
    $npmReady = (& wsl.exe -d $distro sh -lc 'curl -fsS --max-time 2 http://127.0.0.1:80 >/dev/null 2>&1 && echo ready || true').Trim()
    if ($npmReady -eq 'ready') {
        break
    }

    Start-Sleep -Seconds 2
}

netsh interface portproxy show v4tov4
