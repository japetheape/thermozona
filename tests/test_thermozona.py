from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from custom_components.thermozona.helpers import resolve_circuits
from custom_components.thermozona.heat_pump import HeatPumpController
from custom_components.thermozona.thermostat import ThermozonaThermostat
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE


class DummyNumber:
    def __init__(self):
        self.values: list[float] = []

    def set_calculated_value(self, value: float) -> None:
        self.values.append(value)


class DummySensor:
    def __init__(self):
        self.states: list[str] = []

    def update_state(self, state: str) -> None:
        self.states.append(state)


class DummySelect:
    def __init__(self):
        self.entity_id = "select.mode"
        self.options: list[str] = []

    def update_current_option(self, option: str) -> None:
        self.options.append(option)


class DummyThermostat:
    def __init__(self):
        self.calls = 0

    def async_schedule_control(self) -> None:
        self.calls += 1

    async def async_update_mode_listener(self) -> None:
        return None


def _config(**overrides):
    base = {
        "outside_temp_sensor": "sensor.outside",
        "flow_temp_sensor": "input_number.flow",
        "zones": {
            "living_room": {
                "circuits": ["switch.zone_1"],
                "temp_sensor": "sensor.living",
            }
        },
    }
    base.update(overrides)
    return base


def test_resolve_circuits_supports_new_and_legacy_keys():
    assert resolve_circuits({"circuits": ["switch.a"]}) == ["switch.a"]
    assert resolve_circuits({"groups": ["switch.b"]}) == ["switch.b"]
    assert resolve_circuits({}) == []


def test_auto_mode_and_flow_temperature_calculation_uses_zone_status():
    controller = HeatPumpController(SimpleNamespace(states=None), _config())
    controller.update_zone_status("living", target=21, current=19, active=True)
    assert controller.determine_auto_mode() == HVACMode.HEAT

    flow = controller.determine_flow_temperature(HVACMode.HEAT, outside_temp=5)
    assert flow > 24

    controller.update_zone_status("living", target=21, current=23, active=True)
    assert controller.determine_auto_mode() == HVACMode.COOL
    cool_flow = controller.determine_flow_temperature(HVACMode.COOL, outside_temp=30)
    assert 15 <= cool_flow <= 25


def test_get_operation_mode_maps_external_states(fake_hass):
    controller = HeatPumpController(fake_hass, _config(heat_pump_mode="sensor.mode"))

    fake_hass.states.set("sensor.mode", "heating")
    assert controller.get_operation_mode() == "heat"

    fake_hass.states.set("sensor.mode", "cooling")
    assert controller.get_operation_mode() == "cool"

    fake_hass.states.set("sensor.mode", "idle")
    assert controller.get_operation_mode() == "off"


@pytest.mark.asyncio
async def test_async_set_flow_temperature_updates_number_entity(fake_hass):
    controller = HeatPumpController(fake_hass, _config(flow_temp_sensor=None))
    number = DummyNumber()
    controller.register_flow_temperature_number(number)

    fake_hass.states.set("sensor.outside", "10")
    controller.update_zone_status("living", target=21, current=19, active=True)

    mode = await controller._async_set_flow_temperature()

    assert mode == HVACMode.HEAT
    assert number.values


@pytest.mark.asyncio
async def test_async_update_heat_pump_state_updates_status_sensor(fake_hass):
    controller = HeatPumpController(fake_hass, _config())
    sensor = DummySensor()
    controller.register_pump_sensor(sensor)

    fake_hass.states.set("switch.zone_1", "on")
    fake_hass.states.set("sensor.outside", "10")
    controller.update_zone_status("living", target=21, current=19, active=True)

    await controller.async_update_heat_pump_state()

    assert sensor.states[-1] in {"heat", "cool"}


@pytest.mark.asyncio
async def test_set_mode_value_normalizes_invalid_option_and_notifies_thermostats(fake_hass):
    controller = HeatPumpController(fake_hass, _config())
    select = DummySelect()
    thermostat = DummyThermostat()

    controller.register_thermostat(thermostat)
    controller.register_mode_select(select)
    controller.set_mode_value("INVALID")

    assert controller.get_operation_mode() == "auto"
    assert select.options[-1] == "auto"
    assert thermostat.calls == 0


@pytest.mark.asyncio
async def test_thermostat_controls_circuits_and_updates_hvac_action(fake_hass):
    controller = HeatPumpController(fake_hass, _config())
    thermostat = ThermozonaThermostat(
        fake_hass,
        "entry-1",
        "living-room",
        ["switch.zone_1"],
        "sensor.living",
        controller,
        hysteresis=0.2,
        control_mode=None,
        pwm_cycle_time=None,
        pwm_min_on_time=None,
        pwm_min_off_time=None,
        pwm_kp=None,
        pwm_ki=None,
    )

    fake_hass.states.set("sensor.outside", "9")
    fake_hass.states.set("sensor.living", "19")
    fake_hass.states.set("switch.zone_1", "off")

    await thermostat.async_set_temperature(**{ATTR_TEMPERATURE: 21})

    assert thermostat.hvac_mode == HVACMode.AUTO
    assert thermostat._attr_hvac_action == HVACAction.HEATING
    assert fake_hass.states.get("switch.zone_1").state == "on"


@pytest.mark.asyncio
async def test_thermostat_turn_off_closes_circuits(fake_hass):
    controller = HeatPumpController(fake_hass, _config())
    thermostat = ThermozonaThermostat(
        fake_hass,
        "entry-1",
        "bedroom",
        ["switch.zone_2"],
        "sensor.bed",
        controller,
        hysteresis=None,
        control_mode=None,
        pwm_cycle_time=None,
        pwm_min_on_time=None,
        pwm_min_off_time=None,
        pwm_kp=None,
        pwm_ki=None,
    )

    fake_hass.states.set("switch.zone_2", "on")
    fake_hass.states.set("sensor.bed", "20")

    await thermostat.async_turn_off()

    assert thermostat.hvac_mode == HVACMode.OFF
    assert fake_hass.states.get("switch.zone_2").state == "off"


def test_name_helpers_cover_slugify_and_prettify():
    assert ThermozonaThermostat._prettify("living_room-main") == "Living room main"
    assert ThermozonaThermostat._slugify("Living Room Main!") == "living_room_main"


def _create_pwm_thermostat(fake_hass, controller):
    return ThermozonaThermostat(
        fake_hass,
        "entry-1",
        "pwm-zone",
        ["switch.zone_pwm"],
        "sensor.zone_pwm",
        controller,
        hysteresis=0.2,
        control_mode="pwm",
        pwm_cycle_time=15,
        pwm_min_on_time=3,
        pwm_min_off_time=3,
        pwm_kp=30.0,
        pwm_ki=2.0,
    )


def test_pwm_pi_output_is_clamped(fake_hass):
    controller = HeatPumpController(fake_hass, _config())
    thermostat = _create_pwm_thermostat(fake_hass, controller)

    thermostat._attr_target_temperature = 21
    duty = thermostat._calculate_pwm_duty(current_temp=10, effective_mode=HVACMode.HEAT, now=datetime.utcnow())

    assert duty == 100


def test_pwm_cycle_applies_minimum_times(fake_hass):
    controller = HeatPumpController(fake_hass, _config())
    thermostat = _create_pwm_thermostat(fake_hass, controller)

    thermostat._pwm_duty_cycle = 10
    thermostat._attr_target_temperature = 20

    now = datetime.utcnow()
    thermostat._start_new_pwm_cycle(current_temp=19.7, effective_mode=HVACMode.HEAT, now=now)

    assert thermostat._pwm_on_time.total_seconds() / 60 >= 3
    assert thermostat._pwm_cycle_start == now


@pytest.mark.asyncio
async def test_pwm_mode_switches_circuit_within_cycle(fake_hass):
    controller = HeatPumpController(fake_hass, _config())
    thermostat = _create_pwm_thermostat(fake_hass, controller)

    fake_hass.states.set("sensor.outside", "9")
    fake_hass.states.set("sensor.zone_pwm", "19")
    fake_hass.states.set("switch.zone_pwm", "off")

    await thermostat.async_set_temperature(**{ATTR_TEMPERATURE: 21})

    assert thermostat._attr_hvac_action in {HVACAction.HEATING, HVACAction.IDLE}
    assert thermostat.extra_state_attributes["control_mode"] == "pwm"
