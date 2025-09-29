# Ecoforest Heat Pump Setup

This guide shows how to pair an Ecoforest heat pump with Thermozona using Home Assistant's Modbus integration. Adapt the IP address, slave IDs, and register ranges to match your own unit.

![Underfloor heating manifold with four actuators](images/image-relais.jpg)
*Example manifold: one circuit serves the bathroom, one the landing, and two feed the attic. Each actuator can be switched individually by Thermozona to balance the zones.*

## 1. Map Ecoforest registers with Modbus

```yaml
modbus:
  - name: ecoforest
    type: tcp
    host: 192.168.1.120
    port: 502
    coils:
      - name: Ecoforest Heat Pump Enable
        slave: 17
        coil: 3          # Optional on/off control (start/stop)
    numbers:
      - name: Ecoforest Heat Pump Mode Raw
        slave: 17
        address: 5224        # 0=off, 1=heat, 2=cool (set & get)
        data_type: int16
        min_value: 0
        max_value: 2
        step: 1
      - name: Ecoforest Cooling Setpoint
        unit_of_measurement: "°C"
        slave: 17
        address: 139         # Cooling flow temp (set & get)
        data_type: int16
        scale: 0.1
        precision: 1
        min_value: 10
        max_value: 35
      - name: Ecoforest Heating Setpoint
        unit_of_measurement: "°C"
        slave: 17
        address: 135         # Heating flow temp (set & get)
        data_type: int16
        scale: 0.1
        precision: 1
        min_value: 10
        max_value: 45
```

> ℹ️ A coil for `Ecoforest Heat Pump Enable` is optional—use it if you want manual start/stop control. Thermozona itself no longer needs a dedicated on/off switch.

## 2. Keep the Ecoforest mode register in sync

Thermozona exposes `select.thermozona_heat_pump_mode` (options: `auto`, `heat`, `cool`, `off`). Mirror that value to register 5224 and back so both systems stay aligned.

You can also watch `binary_sensor.thermozona_heat_pump_demand`, which flips on whenever any zone requests the pump—use it in automations if you want to stop the Ecoforest when there is no demand.

```yaml
automation:
  - alias: Push Thermozona mode to Ecoforest register
    trigger:
      - platform: state
        entity_id: select.thermozona_heat_pump_mode
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state in ['auto', 'heat', 'cool'] }}"
    action:
      - service: number.set_value
        target:
          entity_id: number.ecoforest_heat_pump_mode_raw
        data:
          value: >-
            {% if trigger.to_state.state == 'heat' %}1{% elif trigger.to_state.state == 'cool' %}2{% else %}0{% endif %}

  - alias: Mirror Ecoforest register back to Thermozona mode
    trigger:
      - platform: state
        entity_id: number.ecoforest_heat_pump_mode_raw
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state not in ['unknown', 'unavailable'] }}"
    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ trigger.to_state.state | int == 0 }}"
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.thermozona_heat_pump_mode
                data:
                  option: off
          - conditions:
              - condition: template
                value_template: "{{ trigger.to_state.state | int == 1 }}"
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.thermozona_heat_pump_mode
                data:
                  option: heat
          - conditions:
              - condition: template
                value_template: "{{ trigger.to_state.state | int == 2 }}"
            sequence:
              - service: select.select_option
                target:
                  entity_id: select.thermozona_heat_pump_mode
                data:
                  option: cool
        default:
          - service: select.select_option
            target:
              entity_id: select.thermozona_heat_pump_mode
            data:
              option: auto
```

Optional: add a template sensor to display the decoded Modbus mode in Lovelace.

## 3. Push Thermozona's flow setpoint to the Ecoforest registers

Thermozona exposes `number.thermozona_flow_temperature`. Use a small automation to route that value to the heating or cooling register based on the active mode.

```yaml
automation:
  - alias: Push Thermozona flow temp to Ecoforest setpoints
    trigger:
      - platform: state
        entity_id: number.thermozona_flow_temperature
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state not in ['unknown', 'unavailable'] }}"
    action:
      - choose:
          - conditions:
              - condition: state
                entity_id: select.thermozona_heat_pump_mode
                state: cool
            sequence:
              - service: number.set_value
                target:
                  entity_id: number.ecoforest_cooling_setpoint
                data:
                  value: "{{ trigger.to_state.state | float(0) }}"
          - conditions:
              - condition: state
                entity_id: select.thermozona_heat_pump_mode
                state: heat
            sequence:
              - service: number.set_value
                target:
                  entity_id: number.ecoforest_heating_setpoint
                data:
                  value: "{{ trigger.to_state.state | float(0) }}"
```

If you prefer to log or visualise the values, add extra actions (e.g. `system_log.write`) inside the sequences.

## 4. Wire Thermozona to the Ecoforest entities

```yaml
thermozona:
  outside_temp_sensor: sensor.outdoor
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

Thermozona now calculates the optimal flow temperature, exposes it via `number.thermozona_flow_temperature`, and your automation mirrors it to the correct Ecoforest Modbus register. Adjust the automation logic to cover additional operating modes or heating circuits if needed.
