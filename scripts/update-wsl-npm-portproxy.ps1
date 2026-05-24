param(
    [switch] $LaunchOnly
)

$ErrorActionPreference = 'Stop'

$distro = 'Ubuntu'
$listenAddress = '0.0.0.0'

# Update this section when you need to expose more services through the Windows host.
#
# TCP ports:
# - Add ports here when a TCP service runs inside Ubuntu WSL/Docker and must be reachable
#   from another machine by connecting to the Windows host IP.
# - Keep normal HTTP/HTTPS apps behind Nginx Proxy Manager when possible. These defaults
#   expose NPM itself: 80=http, 81=NPM admin UI, 443=https.
# - Examples for direct TCP access, if you intentionally want them outside NPM:
#   1883 = Mosquitto MQTT, 8554 = Frigate/go2rtc RTSP, 8555 = Frigate/go2rtc WebRTC TCP.
# - Example edit:
#   $tcpPortProxyPorts = @(80, 81, 443, 1883, 8554, 8555)
$tcpPortProxyPorts = @(80, 81, 443)

# UDP ports:
# - netsh interface portproxy only supports TCP. Putting UDP ports in the TCP list will not
#   forward UDP traffic.
# - Add UDP ports here only to open Windows Firewall for UDP ports that are already being
#   published/listened on by Windows/Docker Desktop.
# - If a UDP-only service is reachable only inside WSL, use a real UDP relay/NAT solution
#   or publish the UDP port through Docker Desktop; this script cannot create UDP portproxy
#   mappings.
# - Example, only if Docker/Desktop is already publishing it: 8555 = Frigate/go2rtc WebRTC UDP.
# - Example edit:
#   $udpFirewallOnlyPorts = @(8555)
$udpFirewallOnlyPorts = @()

$wslExe = Join-Path $env:WINDIR 'System32\wsl.exe'
$stateDir = Join-Path $env:LOCALAPPDATA 'WSL-NPM-Portproxy'
$logFile = Join-Path $stateDir 'update.log'
$ipFile = Join-Path $stateDir 'wsl-ip.txt'

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

function Write-Log {
    param([string] $Message)

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $logFile -Value "[$timestamp] $Message"
}

function Invoke-Wsl {
    param([string[]] $Arguments)

    & $wslExe @Arguments
}

function Start-WslDistro {
    $bootstrapResult = (Invoke-Wsl @('-d', $distro, '--exec', 'sh', '-lc', 'nohup sleep 2147483647 >/dev/null 2>&1 & echo started')).Trim()
    Write-Log "WSL bootstrap result: $bootstrapResult"
}

function Get-WslNatAddress {
    $addresses = (Invoke-Wsl @('-d', $distro, 'hostname', '-I')).Trim().Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)

    $addresses |
        Where-Object {
            $_ -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)' -and
            $_ -notmatch '^172\.(17|18|19)\.'
        } |
        Select-Object -First 1
}

function Save-WslNatAddress {
    param([string] $Address)

    Set-Content -Path $ipFile -Value $Address -Encoding ascii
    Write-Log "Saved WSL IP $Address to $ipFile."
}

function Get-SavedWslNatAddress {
    if (-not (Test-Path $ipFile)) {
        return $null
    }

    $savedAddress = (Get-Content -Path $ipFile -Raw).Trim()
    if ($savedAddress -notmatch '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)') {
        return $null
    }

    $savedAddress
}

function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

try {
    if (-not (Test-Path $wslExe)) {
        throw "Could not find wsl.exe at $wslExe"
    }

    Write-Log "Starting portproxy update for $distro. LaunchOnly=$LaunchOnly"

    if ($LaunchOnly) {
        Start-WslDistro
        $wslIp = Get-WslNatAddress
        if (-not $wslIp) {
            throw "Could not find the $distro WSL NAT address."
        }

        Save-WslNatAddress -Address $wslIp
        Write-Log 'Launch-only WSL bootstrap finished.'
        return
    }

    if (-not (Test-IsAdmin)) {
        throw 'Run this script from an elevated Windows PowerShell session.'
    }

    $wslIp = $null
    $wslAvailable = $true

    try {
        Start-WslDistro
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            $wslIp = Get-WslNatAddress
            if ($wslIp) {
                Save-WslNatAddress -Address $wslIp
                break
            }

            Start-Sleep -Seconds 2
        }
    } catch {
        $wslAvailable = $false
        Write-Log "Elevated WSL call failed, falling back to saved IP if present: $($_.Exception.Message)"
        $wslIp = Get-SavedWslNatAddress
    }

    if (-not $wslIp) {
        throw "Could not find the $distro WSL NAT address."
    }

    Write-Log "Using WSL IP $wslIp."

    foreach ($port in $tcpPortProxyPorts) {
        netsh interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$port | Out-Null
        netsh interface portproxy add v4tov4 listenaddress=$listenAddress listenport=$port connectaddress=$wslIp connectport=$port | Out-Null
        Write-Log "Mapped $listenAddress`:$port to $wslIp`:$port."
    }

    $legacyRuleName = 'WSL Native Docker NPM'
    $existingLegacyRule = Get-NetFirewallRule -DisplayName $legacyRuleName -ErrorAction SilentlyContinue
    if ($existingLegacyRule) {
        Remove-NetFirewallRule -DisplayName $legacyRuleName
    }

    $tcpRuleName = 'WSL Native Docker NPM TCP'
    $existingTcpRule = Get-NetFirewallRule -DisplayName $tcpRuleName -ErrorAction SilentlyContinue
    if ($existingTcpRule) {
        Remove-NetFirewallRule -DisplayName $tcpRuleName
    }

    New-NetFirewallRule `
        -DisplayName $tcpRuleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $tcpPortProxyPorts `
        -Profile Any | Out-Null

    $udpRuleName = 'WSL Native Docker NPM UDP'
    $existingUdpRule = Get-NetFirewallRule -DisplayName $udpRuleName -ErrorAction SilentlyContinue
    if ($existingUdpRule) {
        Remove-NetFirewallRule -DisplayName $udpRuleName
    }

    if ($udpFirewallOnlyPorts.Count -gt 0) {
        New-NetFirewallRule `
            -DisplayName $udpRuleName `
            -Direction Inbound `
            -Action Allow `
            -Protocol UDP `
            -LocalPort $udpFirewallOnlyPorts `
            -Profile Any | Out-Null

        Write-Log "Opened UDP firewall ports: $($udpFirewallOnlyPorts -join ', ')."
    }

    if ($wslAvailable) {
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            $npmReady = (Invoke-Wsl @('-d', $distro, 'sh', '-lc', 'curl -fsS --max-time 2 http://127.0.0.1:80 >/dev/null 2>&1 && echo ready || true')).Trim()
            if ($npmReady -eq 'ready') {
                Write-Log 'NPM is responding inside WSL on port 80.'
                break
            }

            Start-Sleep -Seconds 2
        }
    } else {
        Write-Log 'Skipped in-WSL NPM readiness check because elevated WSL calls are unavailable.'
    }

    $portProxyOutput = netsh interface portproxy show v4tov4
    $portProxyOutput | ForEach-Object { Write-Log $_ }
    $portProxyOutput
    Write-Log 'Portproxy update finished.'
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    throw
}
