# Monitoring Management

Prometheus-based SNMP monitoring stack for polling SNMP devices.

## Services

- `prometheus` - stores and queries metrics on port `9090`.
- `snmp-exporter` - polls SNMP devices for Prometheus on port `9116`.
- `unpoller` - polls the UniFi Network API and exposes richer Prometheus metrics on port `9130`.
- `grafana` - dashboards on port `3000`.

## Setup

1. Update `.env` with host paths, time zone, and Grafana credentials.
2. Add devices to `prometheus/snmp-targets.yml`.
3. Set `UNIFI_CONTROLLER_URL`, `UNIFI_CONTROLLER_USER`, and `UNIFI_CONTROLLER_PASS` if using Unpoller.
4. Start the stack:

```bash
docker compose up -d
```

The starter target uses `auth: public_v2` and `module: if_mib`, both provided by the mounted `${CONFIG_PATH}/snmp-exporter/snmp.yml` configuration. Replace `192.168.1.1` before expecting successful scrapes.

## SNMP Polling

Edit `prometheus/snmp-targets.yml` to add routers, switches, access points, UPS devices, printers, or other SNMP-enabled devices:

```yaml
- targets:
    - 192.168.1.1
    - switch.example.lan
  labels:
    auth: public_v2
    module: if_mib
```

Use SNMPv3 wherever possible. The default SNMPv3 auth profile is `snmpv3_env`, which reads `SNMPV3_USERNAME`, `SNMPV3_AUTH_PASSWORD`, and `SNMPV3_PRIV_PASSWORD` from `.env`. If you need different auth protocols or vendor MIB modules, generate a custom `snmp.yml` with the `prometheus/snmp_exporter` generator and replace `${CONFIG_PATH}/snmp-exporter/snmp.yml`.

## UniFi API Polling

Unpoller provides richer UniFi metrics than SNMP, including sites, clients, gateways, APs, switches, and optional DPI. Create a limited/read-only UniFi Network user, then set:

```env
UNIFI_CONTROLLER_URL=https://192.168.211.254
UNIFI_CONTROLLER_USER=unpoller
UNIFI_CONTROLLER_PASS=change-me
```

For UniFi OS controllers such as UDM, UXG, CloudKey Gen2, or newer consoles, use the base URL without `:8443`.

## Grafana

Grafana is provisioned with:

- A default Prometheus datasource.
- A starter `SNMP Monitoring Overview` dashboard.

Default login values come from `.env`. Change `GRAFANA_ADMIN_PASSWORD` before exposing Grafana beyond a trusted network.
