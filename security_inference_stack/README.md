# Security and Inference Stack

Git-backed Dockhand stack for local video security, audio classification, MQTT, inference aggregation, and Home Assistant on Quark.

Shared AI support services are deployed as a separate nested stack; see [`ai_tools/README.md`](ai_tools/README.md).

## Services

| Service | Role | Published access |
|---|---|---|
| `frigate` | Camera NVR, object detection, RTSP restream, and WebRTC | `8971`, `8554`, `8555/tcp`, `8555/udp` |
| `birdnet-go` | Bird-audio classification | `${BN_WEBPORT:-8080}` |
| `mosquitto` | Authenticated MQTT broker for stack-local messaging | No host port |
| `yawamf` | Frigate/BirdNET event aggregation and Intel inference | `9852` → container `8080` |
| `homeassistant` | Home automation and discovery | Host network; normally `8123` |

## Host and hardware requirements

- Compose file: `security_inference_stack/docker-compose.yml`
- Intended host: Quark / `dell-compute`.
- External network: `general_brg`.
- Intel GPU: `/dev/dri`, with `${RENDER_GID:-105}`.
- Intel NPU: `/dev/accel/accel0` for Frigate and YA-WAMF.
- Home Assistant uses host networking, privileged mode, and read-only D-Bus access for discovery/integrations.
- Frigate receives a 1 GiB shared-memory allocation and a 1 GB tmpfs cache.

Verify device nodes, ownership, and inference-provider compatibility before changing hardware mappings or runtime images.

## Persistent storage

| Host path | Purpose |
|---|---|
| `${DOCKERCONFIGPATH}/frigate/config` | Frigate configuration/database |
| `${DOCKERCONFIGPATH}/frigate/media` | Frigate working media |
| `${DOCKERCONFIGPATH}/frigate/models` | Detection models |
| `${SECURITY_EXPORT_PATH}/frigate/{clips,exports}` | Long-lived security exports |
| `${DOCKERCONFIGPATH}/birdnet-go/{config,data}` | BirdNET configuration and observations |
| `${DOCKERCONFIGPATH}/mosquitto/{config,data,log}` | MQTT configuration, persistence, and logs |
| `${DOCKERCONFIGPATH}/yawamf/{config,data}` | YA-WAMF configuration and state |
| `${SECURITY_EXPORT_PATH}/YA-WAMF/captures` | YA-WAMF retained captures |
| `${DOCKERCONFIGPATH}/homeassistant/config` | Home Assistant configuration/database |

Defaults are rooted at `/mnt/apps/docker` and `/mnt/apps/security_inference_stack`. Keep SQLite-heavy configuration local to Quark; use NAS-backed storage only for exports/backups where appropriate.

## Environment

Required secrets:

- `FRIGATE_CAMERA_PASSWORD`
- `MQTT_USERNAME`, `MQTT_PASSWORD`
- Camera/RTSP or Frigate authentication values required by the local configuration

Required site data:

- `BN_LAT`, `BN_LONG`

Common settings include `TZ`, `DOCKERCONFIGPATH`, `SECURITY_EXPORT_PATH`, `SECURITY_STACK_UID`, `SECURITY_STACK_GID`, `RENDER_GID`, BirdNET tuning, Frigate/BirdNET URLs, and `YAWAMF_INFERENCE_PROVIDER`.

Store credentials in Dockhand's encrypted variables. Never commit camera, MQTT, RTSP, or API credentials.

## Service relationships

- Mosquitto creates an authenticated listener on `general_brg` but does not publish port 1883 on the host.
- Frigate and BirdNET publish observations that YA-WAMF correlates.
- YA-WAMF defaults to the `intel_npu` provider on Quark but keeps the setting overridable for validated comparisons.
- Home Assistant is lifecycle-independent from the shared AI tools stack.

## Deployment and updates

Use the repository-level Git/Dockhand procedure in the [root README](../README.md). Do not run direct Docker lifecycle commands.

After deployment, verify:

1. Frigate health, camera feeds, recording paths, RTSP/WebRTC, and intended accelerator.
2. BirdNET health, audio inputs, MQTT publication, and plausible classification rate.
3. Mosquitto authentication and persistence without exposing credentials in logs.
4. YA-WAMF `/health`, provider activation, Frigate connectivity, and capture paths.
5. Home Assistant availability, configuration validity, discovery, and integration health.
6. Export paths have adequate space and expected retention.

## Rollback and recovery

Revert the relevant Git/image/configuration change, push, and redeploy through Dockhand. Camera and automation state lives in bind mounts; preserve it during image rollbacks. Restore databases/configuration only from verified backups and stop services through Dockhand before recovery. Avoid simultaneous changes to images, models, accelerator providers, and persistent configuration because that obscures the rollback boundary.

## Security and safety notes

- Frigate uses elevated capabilities and hardware access; do not broaden them without a specific requirement.
- Home Assistant is privileged and host-networked. Treat its token, configuration, and integrations as sensitive.
- Keep MQTT authenticated and private.
- Camera streams and exported clips are sensitive data; protect host paths and backups.
- Validate NPU/GPU support before making the selected provider authoritative.
