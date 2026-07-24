# Monitoring and Management Stack

Git-backed Dockhand stack for Prometheus-based infrastructure monitoring and Grafana dashboards.

## Services

| Service | Role | Published access |
|---|---|---|
| `prometheus` | Metrics collection, storage, rules, and query API | `${PROMETHEUS_WEB_PORT:-9090}` |
| `snmp-exporter` | SNMP polling endpoint for Prometheus | `${SNMP_EXPORTER_WEB_PORT:-9116}` |
| `unpoller` | UniFi controller polling and Prometheus metrics | `${UNPOLLER_WEB_PORT:-9130}` |
| `grafana` | Dashboards and visualization | `${GRAFANA_WEB_PORT:-3000}` |

## Topology and storage

- Compose file: `monitoring_management/docker-compose.yml`
- External network: `general_brg`.
- All services run as `${PUID:-568}:${PGID:-568}`.
- `CONFIG_PATH` is required and must contain the configuration/data tree below.

| Host path under `${CONFIG_PATH}` | Purpose |
|---|---|
| `prometheus/prometheus.yml` | Prometheus configuration, read-only mount |
| `prometheus/snmp-targets.yml` | SNMP target file, read-only mount |
| `prometheus/rules/` | Alert/recording rules, read-only mount |
| `prometheus/data/` | Prometheus time-series database |
| `snmp-exporter/snmp.yml` | SNMP modules and auth profiles, read-only mount |
| `grafana/data/` | Grafana state/database |
| `grafana/provisioning/` | Provisioned data sources and dashboards |
| `grafana/dashboards/` | Dashboard definitions |

The Compose file deliberately uses `create_host_path: false` for these mounts. Create and permission the tree before first deployment; an absent path should fail rather than silently become an empty directory.

## Environment

Required or security-sensitive values:

- `CONFIG_PATH`
- `SNMPV3_USERNAME`, `SNMPV3_AUTH_PASSWORD`, `SNMPV3_PRIV_PASSWORD`
- `UNIFI_CONTROLLER_URL`, `UNIFI_CONTROLLER_USER`, `UNIFI_CONTROLLER_PASS`
- `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`

Optional settings include `PUID`, `PGID`, `TZ`, published ports, `PROMETHEUS_RETENTION`, UniFi site/DPI/debug options, and `UNIFI_VERIFY_SSL`.

Store SNMP, UniFi, and Grafana credentials as Dockhand secrets. The Compose fallback for Grafana is `admin`/`admin`; always override it before exposing Grafana. Use a dedicated read-only UniFi account and prefer SNMPv3.

## Configuration

Add SNMP devices to `prometheus/snmp-targets.yml`, using auth and module names present in the mounted `snmp.yml`. A typical target entry is:

```yaml
- targets:
    - switch.example.lan
  labels:
    auth: snmpv3_env
    module: if_mib
```

For UniFi OS consoles, set `UNIFI_CONTROLLER_URL` to the console base URL. Keep TLS verification enabled when the controller presents a trusted certificate; if it cannot be enabled, constrain the traffic to the trusted management network and document the certificate limitation.

## Deployment and updates

Use the Git-backed Dockhand workflow in the [root README](../README.md). Do not use direct `docker compose up` or `pull` commands on the host.

Before deployment, validate configuration files independently where practical. After deployment, verify:

1. Prometheus `/-/healthy` succeeds and all intended targets appear.
2. SNMP Exporter `/metrics` responds and a representative SNMP scrape succeeds.
3. Unpoller reports healthy and exports metrics for the expected UniFi site.
4. Grafana `/api/health` succeeds and its provisioned Prometheus datasource works.
5. Prometheus retention and disk growth match the host capacity plan.

## Rollback and backup

Revert the Git/image/configuration change, push, and redeploy through Dockhand. Back up `prometheus/data` and `grafana/data` according to their consistency requirements; configuration and dashboard source should remain in the managed configuration tree. Restore state only after stopping affected services through Dockhand.

## Security notes

- Published monitoring ports should remain on trusted management networks or behind an authenticated reverse proxy.
- Protect SNMPv3 and UniFi credentials; do not commit populated environment files.
- Avoid SNMPv2 community strings where SNMPv3 is available.
- Monitor the size of the Prometheus TSDB; the default retention is 30 days.
