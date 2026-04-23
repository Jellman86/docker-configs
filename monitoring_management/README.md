# Monitoring Management

Prometheus-based SNMP monitoring stack for polling SNMP devices.

## Services

- `prometheus` - stores and queries metrics on port `9090`.
- `snmp-exporter` - polls SNMP devices for Prometheus on port `9116`.
- `grafana` - dashboards on port `3000`.

## Setup

1. Update `.env` with host paths, time zone, and Grafana credentials.
2. Add devices to `prometheus/snmp-targets.yml`.
3. Start the stack:

```bash
docker compose up -d
```

The starter target uses `auth: public_v2` and `module: if_mib`, both provided by the mounted `snmp-exporter/snmp.yml` configuration. Replace `192.168.1.1` before expecting successful scrapes.

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

Use SNMPv3 wherever possible. If you need custom auth profiles or vendor MIB modules, generate a custom `snmp.yml` with the `prometheus/snmp_exporter` generator and replace `snmp-exporter/snmp.yml`.

## Grafana

Grafana is provisioned with:

- A default Prometheus datasource.
- A starter `SNMP Monitoring Overview` dashboard.

Default login values come from `.env`. Change `GRAFANA_ADMIN_PASSWORD` before exposing Grafana beyond a trusted network.
