# Thermozona 💧🔥

<p align="center">
  <img src="https://raw.githubusercontent.com/thermozona/thermozona/main/assets/logo@2x.png" alt="Thermozona logo" height="256" />
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=thermozona&repository=thermozona&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and add Thermozona to HACS" />
  </a>
</p>

Welcome to **Thermozona**, the Home Assistant integration that keeps your floors smart, cozy, and energy-efficient. It steers both heating and cooling loops, so the same zoning logic works in summer and winter. With weather-aware control and a smooth HA experience, you get year-round comfort tailored to every room. 🏡✨

Learn more at [thermozona.com](https://thermozona.com).

I built Thermozona while upgrading my own home: every underfloor heating manifold now uses Zigbee relays to drive the actuators, so each circuit can be switched independently as a zone. This project wraps that setup into a reusable integration—whether you run Zigbee, KNX, or another transport, Thermozona coordinates the relays, sensors, and heat pump so your floors stay perfectly balanced.

On the heat source side I connected an Ecoforest EcoGeo B2 over Modbus, but Thermozona itself is heat-pump agnostic: it exposes the desired heating/cooling state and flow temperature so you can mirror them—via Modbus, KNX, MQTT, or anything else—into whichever unit you own.

<p align="center">
  <img src="https://raw.githubusercontent.com/thermozona/thermozona/main/docs/images/underfloorheating.jpg" alt="Thermozona-controlled underfloor heating manifolds" width="300" />
  <img src="https://raw.githubusercontent.com/thermozona/thermozona/main/docs/images/image-relais.jpg" alt="Underfloor heating manifold with four actuators" width="300" />
</p>


### Dashboard example 🖥️

<p align="center">
  <img src="https://raw.githubusercontent.com/thermozona/thermozona/main/docs/images/dashboard-thermozona.png" alt="Thermozona dashboard example" width="600" />
</p>

The dashboard shows one thermostat per zone you define in `configuration.yaml`. Each zone maps to a separate underfloor circuit (or group of circuits), giving you granular control from Home Assistant while Thermozona keeps the heat pump in sync.

## Highlights ⚡
- 🧠 **Smart controller** – Free tier includes manual and auto heat/cool switching.
- 🌡️ **Weather compensation** – Dynamically adjusts flow temperature based on the outdoor climate.
- 🧩 **Flexible zones** – Combine multiple circuits per room and bring your favorite temperature sensors.
- 🎛️ **Full climate entities** – Each zone shows up as a native climate entity inside Home Assistant.
- 🚀 **Tiered model** – Core stays free; advanced control features are unlocked with a local sponsorship key.

## Sponsorship model: Free vs Sponsor License

Thermozona is community-funded. The core integration stays open and free, while sponsor-required components unlock advanced control features.

| Free (MIT, HACS) | Sponsor License (license key) |
|---|---|
| Bang-bang regeling per zone | PWM/PI control mode |
| Handmatige + auto heat/cool mode | Runtime flow-curve tuning |
| Basis weather compensation | Advanced PWM diagnostics |
| Warmtepomp status entities | Stagger optimization across zones |
|  | Actuator delay compensation |

`license_key` must be a valid GitHub sponsor token and is validated locally at integration load time. There is no cloud dependency.

## Licensing transparency

- Core/open components are licensed under MIT (`LICENSE`).
- Sponsor-required components are excluded from MIT and licensed under `LICENSE-COMMERCIAL.md`.
- See `NOTICE` and file headers for component-level licensing.

## Installation 🚧

Thermozona does not require HACS. You can install it directly as a custom integration.

### Manual install (no HACS required)

1. Clone this repository.
2. Copy the integration into your Home Assistant config directory:

   ```bash
   ./scripts/install_manual.sh /path/to/home-assistant-config
   ```

   Run this command on the machine where you cloned this repository.

   Example:

   ```bash
   ./scripts/install_manual.sh /config
   ```

3. Edit `configuration.yaml` and add a `thermozona:` block with your zones.
4. Restart Home Assistant so it loads the integration.

To update manually later, pull the latest changes and run the same command again.

### Via HACS (optional)

If you already use HACS, Thermozona is listed in the default HACS store.

1. Open HACS in Home Assistant and choose `Integrations`.
2. Search for **Thermozona** and install it.
3. Restart Home Assistant so it loads the component.
4. Add a `thermozona:` block to your `configuration.yaml` (see [Configuration](#configuration-)).
5. Restart Home Assistant so it loads the integration with your YAML settings.

## Configuration 🔧
> ℹ️ Thermozona is configured **exclusively through YAML**. There is no Add Integration/Config Flow in the UI yet—Home Assistant will pick up your setup from `configuration.yaml` after a restart (or by reloading the integration).

Add this example configuration to `configuration.yaml` to get started:

```yaml
thermozona:
  outside_temp_sensor: sensor.outdoor
   license_key: eyJhbGciOi...<github_sponsor_token>  # Optional: unlocks Sponsor License features
  heating_base_offset: 3.0  # Optional: raise/lower the base heating offset
  cooling_base_offset: 2.5  # Optional: make cooling supply warmer/colder
  flow_curve_offset: 0.0    # Optional baseline for UI flow-curve tuning
  zones:
    living_room:
      circuits:
        - switch.manifold_living_left
        - switch.manifold_living_right
      temp_sensor: sensor.living_room
      hysteresis: 0.2
      control_mode: pwm        # Optional: bang_bang (free) or pwm (Sponsor License)
      pwm_cycle_time: 15       # Optional: 5-30 minutes (default 15)
      pwm_min_on_time: 3       # Optional: 1-10 minutes (default 3)
      pwm_min_off_time: 3      # Optional: 1-10 minutes (default 3)
      pwm_kp: 30.0             # Optional: proportional gain
      pwm_ki: 2.0              # Optional: integral gain
    bathroom:
      circuits:
        - switch.manifold_bathroom
      temp_sensor: sensor.bathroom
```
💡 *Tip*: Each `circuit` is a switch (or `input_boolean`) that opens a manifold loop for that zone. Combine multiple circuits per space for an even temperature.

#### Zones vs. circuits

Thermozona thinks in **zones** because that is how you want to control comfort—one thermostat card per space in Home Assistant. A zone typically maps to a single room, but it can just as well be a whole floor or an open-plan living area. Within every zone you list one or more **circuits**. Each circuit corresponds to a physical loop on your underfloor heating manifold (or any other controllable output) and is exposed as a switch entity in Home Assistant. When the zone demands heat or cooling, Thermozona toggles *all* circuits defined for that zone, so you get uniform flow across the entire space. Have a bedroom with three small loops? Group the three switches under the same zone and the integration treats them as a single thermostat with three synchronized actuators.

### Fine-tuning the heating curve

Thermozona starts its heating curve with a **3 K base offset** above the warmest active zone. Adjust `heating_base_offset` if your installation—radiators, thick screed floors, or fan coils—needs more or less supply temperature to stay comfortable.

### Fine-tuning the cooling curve

Prefer more aggressive or gentler cooling? Tweak `cooling_base_offset`. The default is **2.5 K below the coldest requested zone**. A lower offset (for example 2.0) keeps the supply water warmer for softer cooling, while a higher offset strengthens the cooling effect.
Need quick day-to-day adjustment without editing YAML? Use `number.thermozona_flow_curve_offset` in the UI to temporarily nudge the whole flow-temperature curve up or down (applied to both heating and cooling calculations). Thermozona resets this helper to the YAML value (`flow_curve_offset`) when the integration reloads/restarts, so YAML remains the source of truth.
🧮 *Need tighter control?* Override the per-zone `hysteresis` to change how far above/below the target temperature Thermozona waits before switching. Leave it out to keep the default ±0.3 °C deadband.


### Per-zone control strategy: Bang-bang vs PWM

Thermozona supports two zone control strategies:

- `bang_bang` (default, free): classic hysteresis switching using `hysteresis` around the setpoint.
- `pwm` (Sponsor License): PI-driven pulse-width modulation to reduce overshoot in high thermal-mass floors.

When `control_mode: pwm` is enabled on a zone, Thermozona calculates a duty cycle (0–100%) every PWM cycle and turns all zone circuits on/off for the corresponding time slice.

#### PWM options (per zone)

- `pwm_cycle_time` *(default: 15, range: 5-30 min)* — total cycle length.
- `pwm_min_on_time` *(default: 3, range: 1-10 min)* — minimum on pulse for thermal actuators.
- `pwm_min_off_time` *(default: 3, range: 1-10 min)* — minimum off pulse.
- `pwm_kp` *(default: 30.0)* — proportional gain (% output per °C error).
- `pwm_ki` *(default: 2.0)* — integral gain (% output per accumulated °C·minute).

Use `pwm` for slow floor loops that overshoot with on/off control; keep `bang_bang` for simpler zones where hysteresis already behaves well.

## Connecting Your Heat Pump 🔌

Thermozona exposes two key helpers for the plant side:
- `sensor.thermozona_heat_pump_status` reports the current demand direction (`heat`, `cool`, or `idle`). Use it to decide whether your heat pump should run and which mode it needs.
- `number.thermozona_flow_temperature` publishes the target flow temperature that Thermozona calculated from the active zones and weather curve. Push that value to your heat pump (or manifold) so the generated supply water matches the demand.
- `sensor.thermozona_flow_temperature` mirrors the same calculated flow temperature as a measurement sensor, so Home Assistant can keep long-term temperature history and statistics.
- `number.thermozona_flow_curve_offset` lets you temporarily shift the entire curve from the UI; reload/reset returns it to the YAML `flow_curve_offset` value.

Mirror these entities through the protocol your heat pump supports (Modbus, KNX, MQTT, …) so the physical unit follows Thermozona’s lead.

For physical heat pumps such as the Ecoforest, monitor `sensor.thermozona_heat_pump_status`: write `1` for heating, `2` for cooling, and `0` when it reports `idle` so the pump stops. Need the full walkthrough? See [`docs/heatpump-ecoforest.md`](docs/heatpump-ecoforest.md).

### Example: Ecoforest heat pump via Modbus
Looking for a full example that includes Modbus entities, helper scripts, and automations? Check out `docs/heatpump-ecoforest.md`.

You can mirror the same pattern for flow-temperature numbers or additional status sensors by mapping the relevant registers to Home Assistant entities and referencing them in Thermozona.

## Under the Hood 🛠️
- 🔄 `config_flow.py` imports YAML settings into a config entry and keeps setup YAML-first.
- 🌬️ `heat_pump.py` manages the heat pump, toggles it on/off, and tunes the optimal flow temperature based on demand and weather.
- 🌍 `climate.py` exposes every zone as a full-featured climate entity so you can control it from Lovelace, automations, or scripts.
- 🧰 `helpers.py` bundles utility logic to resolve circuits and sensors reliably.

## Debugging 🔎
- Enable logging in `configuration.yaml`:
  ```yaml
  logger:
    logs:
      custom_components.thermozona: debug
  ```
- Tail `home-assistant.log` to follow events in real time.
- Use Developer Tools to inspect the generated climate entities and helper sensors.
- Changed your YAML config and want to apply it without deleting the integration? Reload
  Thermozona from the Integrations UI (⋮ → **Reload**) or call the `thermozona.reload`
  service from Developer Tools → Services to re-import the latest configuration and
  reload the devices.
- Want to test the full Home Assistant UI locally in Docker? Follow
  [`docs/local-ui-testing-docker.md`](docs/local-ui-testing-docker.md).

## Roadmap 🧭
- 📉 Dynamic tariffs support *(Coming soon)*.
- ⏱️ Support for per-zone run-on times and hysteresis.
- 📊 Gorgeous Lovelace dashboards tailored for Thermozona.
- 🧪 Unit tests for the control algorithms.
- 🌐 Comprehensive docs hosted on GitHub Pages.

## Contributing 🙌
Issues, feature requests, and pull requests are very welcome! Share how you are using Thermozona and help us make it even better. 🤗

## Safety and liability ⚠️
- Thermozona is provided for DIY/home automation use at your own risk.
- You are responsible for correct installation, wiring, relay sizing, and safety protections in your electrical and hydronic system.
- Always follow local electrical/building codes and manufacturer guidance, and use a qualified installer when needed.
- The authors and contributors are not liable for any damages, losses, injuries, equipment failures, or incidents (including overheating, water damage, or fire) resulting from installation, configuration, or use.

## License 📄
This project is licensed under the MIT license for open components. See `LICENSE`.

Sponsor-required components are excluded from the MIT license and are licensed under `LICENSE-COMMERCIAL.md`.
See `NOTICE` and file license headers for component-level licensing.

Warm regards and have fun making your floors extra comfy! 🔥🧦
