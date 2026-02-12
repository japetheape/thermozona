# Local UI testing with Home Assistant Docker

This guide runs Home Assistant locally so you can test Thermozona in the real UI.

## What is included

This repository now includes:

- `docker-compose.yml`
- `ha-config/configuration.yaml`
- `ha-config/automations.yaml`
- `ha-config/scripts.yaml`
- `ha-config/scenes.yaml`

The compose setup mounts:

- `./ha-config` to `/config`
- `./custom_components` to `/config/custom_components`

That means code changes in this repo are immediately visible to the container.

## Start Home Assistant

From the repository root:

```bash
docker compose up -d
docker compose logs -f homeassistant
```

Open Home Assistant:

- `http://localhost:8123`

On first run, onboarding is done automatically by the `homeassistant-onboarding`
sidecar service. Use this local test account:

- Username: `test`
- Password: `test12345`

If you want different credentials, override the `HA_TEST_USER_*` environment
variables in `docker-compose.yml`.

## Test workflow

1. Open Dashboard and Developer Tools.
2. Verify entities such as:
   - `climate.thermozona_...`
   - `sensor.thermozona_heat_pump_status`
   - `number.thermozona_flow_temperature`
   - `number.thermozona_flow_curve_offset`
3. Change target temperatures in climate cards to validate behavior.

## Reload after changes

- YAML-only changes in `ha-config/configuration.yaml`:
  - Call service `thermozona.reload`, or restart the container.
- Python code changes in `custom_components/thermozona/*.py`:
  - Restart Home Assistant container:

```bash
docker compose restart homeassistant
```

## Useful commands

```bash
docker compose ps
docker compose logs -f homeassistant
docker compose restart homeassistant
docker compose down
```

## Notes

- This setup is for local development/testing only.
- Persistent test data is stored under `ha-config/`.
- If you want a clean state, stop the stack and remove generated state files under `ha-config/`.
