# UnderfloorHeating 💧🔥

Welcome to **UnderfloorHeating**, the Home Assistant integration that keeps your floors smart, cozy, and energy-efficient. With zoning, weather-aware control, and a smooth HA experience, you get year-round comfort tailored to every room. 🏡✨

## Highlights ⚡
- 🧠 **Smart controller** – Keeps an eye on every zone and automatically switches between heating and cooling.
- 🌡️ **Weather compensation** – Dynamically adjusts flow temperature based on the outdoor climate.
- 🧩 **Flexible zones** – Combine multiple circuits per room and bring your favorite temperature sensors.
- 🎛️ **Full climate entities** – Each zone shows up as a native climate entity inside Home Assistant.
- 🚀 **Instant demo** – Ships with sample configuration so you can start experimenting right away.

## Installation 🚧
1. Copy the `custom_components/underfloorheating` folder into your Home Assistant configuration directory.
2. Restart Home Assistant.
3. Go to `Settings -> Devices & Services -> Integrations -> +` and search for **Underfloor Heating**.
4. Follow the Config Flow to pick zones, sensors, and switches. 🪄

## Configuration 🔧
Prefer YAML? Use this snippet as a starting point:

```yaml
underfloorheating:
  outside_temp_sensor: sensor.outdoor
  flow_temp_sensor: input_number.flow_temp
  heat_pump_switch: input_boolean.heat_pump
  heat_pump_mode: input_select.heat_pump_mode
  zones:
    living_room:
      circuits:
        - switch.manifold_living_left
        - switch.manifold_living_right
      temp_sensor: sensor.living_room
    bathroom:
      circuits:
        - switch.manifold_bathroom
      temp_sensor: sensor.bathroom
```
💡 *Tip*: Each `circuit` is a switch that controls a manifold loop for that zone. Combine multiple circuits per space for an even temperature.

## Under the Hood 🛠️
- 🔄 `config_flow.py` walks you through adding zones and entities step by step.
- 🌬️ `heat_pump.py` manages the heat pump, toggles it on/off, and tunes the optimal flow temperature based on demand and weather.
- 🌍 `climate.py` exposes every zone as a full-featured climate entity so you can control it from Lovelace, automations, or scripts.
- 🧰 `helpers.py` bundles utility logic to resolve circuits and sensors reliably.

## Debugging 🔎
- Enable logging in `configuration.yaml`:
  ```yaml
  logger:
    logs:
      custom_components.underfloorheating: debug
  ```
- Tail `home-assistant.log` to follow events in real time.
- Use Developer Tools to inspect the generated climate entities and helper sensors.

## Roadmap 🧭
- ⏱️ Support for per-zone run-on times and hysteresis.
- 📊 Gorgeous Lovelace dashboards for underfloor heating.
- 🧪 Unit tests for the control algorithms.
- 🌐 Comprehensive docs hosted on GitHub Pages.

## Contributing 🙌
Issues, feature requests, and pull requests are very welcome! Share how you are using UnderfloorHeating and help us make it even better. 🤗

## License 📄
Released under the MIT license. See `LICENSE` for details.

Warm regards and have fun making your floors extra comfy! 🔥🧦
