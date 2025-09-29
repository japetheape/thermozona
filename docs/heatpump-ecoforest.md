# Ecoforest Heat Pump Setup

This guide shows how to pair an Ecoforest heat pump with Thermozona using Home Assistant's Modbus integration. Adapt the IP address, slave IDs, and register ranges to match your own unit.


## 1. Map Ecoforest registers with Modbus

```yaml
modbus:
  - name: ecoforest
    type: tcp
    host: 192.168.1.120
    port: 502
    numbers:
      - name: Heatpump BUS DG1 Demand
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


## 2. Drive the Ecoforest mode register from real demand

Thermozona offers two helper entities:

- `sensor.thermozona_heat_pump_status` reflects the current demand direction and takes the values `heat`, `cool`, or `idle`.
- `select.thermozona_heat_pump_mode` lets you choose which operating mode the heat pump should use (`auto`, `heat`, `cool`, `off`).

Combine them so register 5224 only switches to *heat* or *cool* while there is an actual demand. The snippet below honours manual `heat`/`cool` selections and also supports `auto`: when you leave the select on `auto`, Thermozona drives the status sensor based on the zones’ needs. When the status falls back to `idle`, the automation writes `0` so the Ecoforest stops.

```yaml
automation:
  - alias: Drive Ecoforest mode register from Thermozona status
    trigger:
      - platform: state
        entity_id:
          - sensor.thermozona_heat_pump_status
    action:
      - service: modbus.write_register
        data:
          hub: ecoforest
          slave: 17
          address: 5224
          value: >-
            {% set state = states('sensor.thermozona_heat_pump_status') %}
            {% if state == 'cool' %}2{% elif state == 'heat' %}1{% else %}0{% endif %}
```

If you also switch modes from the Ecoforest front end, add a second automation that writes the Modbus value back into `select.thermozona_heat_pump_mode` (0 → off, 1 → heat, 2 → cool). Leave it out if Thermozona is the single source of truth.

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
              - condition: template
                value_template: "{{ states('sensor.thermozona_heat_pump_status') == 'cool' }}"
            sequence:
              - service: modbus.write_register
                data:
                  hub: ecoforest
                  slave: 17
                  address: 139
                  value: "{{ (trigger.to_state.state | float(0) * 10) | round(0) | int }}"
          - conditions:
              - condition: template
                value_template: "{{ states('sensor.thermozona_heat_pump_status') == 'heat' }}"
            sequence:
              - service: modbus.write_register
                data:
                  hub: ecoforest
                  slave: 17
                  address: 135
                  value: "{{ (trigger.to_state.state | float(0) * 10) | round(0) | int }}"
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
