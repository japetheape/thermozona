"""Heat pump controller for the Thermozona integration."""
from __future__ import annotations

import logging
import weakref
from typing import Any, TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.components.climate import HVACMode

from . import (
    CONF_FLOW_TEMP_SENSOR,
    CONF_HEAT_PUMP_MODE,
    CONF_OUTSIDE_TEMP_SENSOR,
    CONF_ZONES,
    DOMAIN,
)
from .helpers import resolve_circuits

if TYPE_CHECKING:
    from .thermostat import ThermozonaThermostat
    from .number import ThermozonaFlowTemperatureNumber
    from .select import ThermozonaHeatPumpModeSelect
    from .sensor import ThermozonaHeatPumpStatusSensor

_LOGGER = logging.getLogger(__name__)


class HeatPumpController:
    """Coordinate state updates for the shared heat pump."""

    def __init__(self, hass: HomeAssistant, entry_config: dict[str, Any]) -> None:
        self._hass = hass
        self._entry_config = entry_config
        self._zone_status: dict[str, dict[str, float]] = {}
        self._last_auto_mode: HVACMode = HVACMode.HEAT
        self._thermostats: weakref.WeakSet[ThermozonaThermostat] = weakref.WeakSet()
        self._flow_number: weakref.ReferenceType[
            ThermozonaFlowTemperatureNumber
        ] | None = None
        self._pump_sensor: weakref.ReferenceType[
            ThermozonaHeatPumpStatusSensor
        ] | None = None
        self._last_flow_temp: float | None = None
        self._mode_select: weakref.ReferenceType[
            ThermozonaHeatPumpModeSelect
        ] | None = None
        self._mode_value: str = "auto"
        self._mode_entity_id: str | None = None
        self._pump_state: str = "idle"


    def _outside_temp_sensor(self) -> str | None:
        return self._entry_config.get(CONF_OUTSIDE_TEMP_SENSOR)

    def _flow_temp_entity(self) -> str | None:
        return self._entry_config.get(CONF_FLOW_TEMP_SENSOR)

    def _flow_temp_number(self) -> "ThermozonaFlowTemperatureNumber" | None:
        if self._flow_number is None:
            return None
        entity = self._flow_number()
        if entity is None:
            self._flow_number = None
        return entity

    def _mode_select_entity(self) -> "ThermozonaHeatPumpModeSelect" | None:
        if self._mode_select is None:
            return None
        entity = self._mode_select()
        if entity is None:
            self._mode_select = None
        return entity

    def _pump_sensor_entity(self) -> "ThermozonaHeatPumpStatusSensor" | None:
        if self._pump_sensor is None:
            return None
        entity = self._pump_sensor()
        if entity is None:
            self._pump_sensor = None
        return entity

    def register_flow_temperature_number(
        self, entity: "ThermozonaFlowTemperatureNumber"
    ) -> None:
        """Register internal number entity to publish flow temperature."""
        self._flow_number = weakref.ref(entity)
        if self._last_flow_temp is not None:
            entity.set_calculated_value(self._last_flow_temp)

    def unregister_flow_temperature_number(
        self, entity: "ThermozonaFlowTemperatureNumber"
    ) -> None:
        """Unregister the internal number entity when it is removed."""
        if self._flow_number is not None and self._flow_number() is entity:
            self._flow_number = None

    def register_pump_sensor(
        self, entity: "ThermozonaHeatPumpStatusSensor"
    ) -> None:
        """Register internal sensor for heat pump status."""
        self._pump_sensor = weakref.ref(entity)
        entity.update_state(self._pump_state)

    def unregister_pump_sensor(
        self, entity: "ThermozonaHeatPumpStatusSensor"
    ) -> None:
        """Unregister the internal sensor when removed."""
        if self._pump_sensor is not None and self._pump_sensor() is entity:
            self._pump_sensor = None

    def _update_pump_status(
        self, demand: bool, mode: HVACMode | None
    ) -> None:
        """Update cached pump status and expose it via helper entities."""
        if not demand or mode is None:
            state = "idle"
        elif mode == HVACMode.COOL:
            state = "cool"
        else:
            state = "heat"

        self._pump_state = state
        if (sensor := self._pump_sensor_entity()) is not None:
            sensor.update_state(state)

    def register_mode_select(
        self, entity: "ThermozonaHeatPumpModeSelect"
    ) -> None:
        """Register internal select entity to control heat pump mode."""
        self._mode_select = weakref.ref(entity)
        self._mode_entity_id = entity.entity_id
        entity.update_current_option(self._mode_value)
        for thermostat in list(self._thermostats):
            self._hass.async_create_task(thermostat.async_update_mode_listener())

    def unregister_mode_select(
        self, entity: "ThermozonaHeatPumpModeSelect"
    ) -> None:
        """Unregister the internal select entity when removed."""
        if self._mode_select is not None and self._mode_select() is entity:
            self._mode_select = None
            self._mode_entity_id = None
            for thermostat in list(self._thermostats):
                self._hass.async_create_task(thermostat.async_update_mode_listener())

    def set_mode_value(self, value: str) -> None:
        """Store a new mode value coming from the select entity."""
        normalized = value.lower()
        if normalized not in {"auto", "heat", "cool", "off"}:
            _LOGGER.warning("%s: Invalid mode '%s', defaulting to auto", DOMAIN, value)
            normalized = "auto"

        previous = self._mode_value

        if normalized == "heat":
            self._last_auto_mode = HVACMode.HEAT
        elif normalized == "cool":
            self._last_auto_mode = HVACMode.COOL

        if normalized == previous:
            if (select := self._mode_select_entity()) is not None:
                select.update_current_option(normalized)
            return

        self._mode_value = normalized

        if (select := self._mode_select_entity()) is not None:
            select.update_current_option(normalized)

        _LOGGER.debug("%s: Heat pump mode set to %s", DOMAIN, normalized)
        self._notify_thermostats()

    def get_all_circuit_entities(self) -> list[str]:
        """Return all circuit entities across the configured zones."""
        circuits: list[str] = []
        for zone_config in self._entry_config.get(CONF_ZONES, {}).values():
            circuits.extend(resolve_circuits(zone_config))
        return circuits

    def get_operation_mode(self) -> str:
        """Return the current heat pump operation mode (heat/cool/auto)."""
        if self._mode_select_entity() is not None:
            return self._mode_value

        mode_entity = self._entry_config.get(CONF_HEAT_PUMP_MODE)
        if not mode_entity:
            return "auto"

        state = self._hass.states.get(mode_entity)
        if not state:
            _LOGGER.warning("%s: Heat pump mode entity %s not found", DOMAIN, mode_entity)
            return "auto"

        value = state.state.lower()
        if value in {"off", "idle"}:
            return "off"
        if value in {"heat", "heating"}:
            return "heat"
        if value in {"cool", "cooling"}:
            return "cool"
        if value in {"auto", "automatic"}:
            return "auto"

        _LOGGER.debug(
            "%s: Heat pump mode %s unknown (state=%s), defaulting to auto",
            DOMAIN,
            mode_entity,
            state.state,
        )
        return "auto"

    @property
    def mode_entity(self) -> str | None:
        """Return the configured heat pump mode entity, if any."""
        if self._mode_entity_id is not None:
            return self._mode_entity_id
        return self._entry_config.get(CONF_HEAT_PUMP_MODE)

    def update_zone_status(
        self,
        zone_name: str,
        *,
        target: float | None,
        current: float | None,
        active: bool | None = None,
        source: ThermozonaThermostat | None = None,
    ) -> None:
        """Store latest temperature/target info for the zone."""
        if target is None or current is None:
            self._zone_status.pop(zone_name, None)
        else:
            entry = self._zone_status.setdefault(zone_name, {})
            entry["target"] = float(target)
            entry["current"] = float(current)
            if active is not None:
                entry["active"] = bool(active)

        if active is not None and zone_name in self._zone_status:
            self._zone_status[zone_name]["active"] = bool(active)

        if self.get_operation_mode() == "auto":
            previous_mode = self._last_auto_mode
            new_mode = self.determine_auto_mode()
            if new_mode != previous_mode:
                _LOGGER.debug(
                    "%s: Auto mode changed from %s to %s after %s update",
                    DOMAIN,
                    previous_mode,
                    new_mode,
                    zone_name,
                )
                self._notify_thermostats(skip=source)

    def determine_auto_mode(self) -> HVACMode:
        """Decide between heating or cooling when pump is in auto mode."""
        if not self._zone_status:
            self._last_auto_mode = HVACMode.HEAT
            return self._last_auto_mode

        deltas: list[float] = []
        for status in self._zone_status.values():
            deltas.append(status["current"] - status["target"])

        if not deltas:
            self._last_auto_mode = HVACMode.HEAT
            return self._last_auto_mode

        avg_delta = sum(deltas) / len(deltas)
        # Small deadband to avoid rapid toggling around the setpoint
        if avg_delta > 0.2:
            self._last_auto_mode = HVACMode.COOL
        elif avg_delta < -0.2:
            self._last_auto_mode = HVACMode.HEAT

        return self._last_auto_mode

    def determine_flow_temperature(
        self, effective_mode: HVACMode, outside_temp: float | None
    ) -> float:
        """Return desired flow temperature based on zone targets and weather."""

        def _relevant_statuses() -> list[dict[str, float]]:
            active_statuses = [
                status for status in self._zone_status.values() if status.get("active")
            ]
            return active_statuses or list(self._zone_status.values())

        statuses = _relevant_statuses()
        if not statuses:
            # fallback naar een veilige laagtemperatuur
            return 30.0 if effective_mode != HVACMode.COOL else 20.0

        max_target = max(status["target"] for status in statuses)
        min_target = min(status["target"] for status in statuses)

        if effective_mode == HVACMode.COOL:
            min_temp = 15.0
            max_temp = 25.0
            base_offset = 2.5
            if outside_temp is not None:
                base_offset += max(0.0, outside_temp - 24.0) * 0.2
            flow = min_target - base_offset
            return max(min_temp, min(max_temp, flow))

        # Heating branch (default)
        min_temp = 15.0
        max_temp = 35.0
        base_offset = 2.0
        if outside_temp is not None:
            base_offset += max(0.0, 15.0 - outside_temp) * 0.25
        flow = max_target + base_offset
        return max(min_temp, min(max_temp, flow))

    def register_thermostat(self, thermostat: ThermozonaThermostat) -> None:
        """Register a thermostat for notifications."""
        self._thermostats.add(thermostat)
        self._hass.async_create_task(thermostat.async_update_mode_listener())

    def unregister_thermostat(self, thermostat: ThermozonaThermostat) -> None:
        """Unregister a thermostat."""
        self._thermostats.discard(thermostat)

    def _notify_thermostats(
        self, *, skip: ThermozonaThermostat | None = None
    ) -> None:
        """Ask all thermostats (except the source) to re-evaluate control."""
        for thermostat in list(self._thermostats):
            if thermostat is skip:
                continue
            thermostat.async_schedule_control()

    async def async_update_heat_pump_state(self) -> None:
        """Update the heat pump switch and flow temperature based on circuit state."""
        try:
            circuits = self.get_all_circuit_entities()
            _LOGGER.debug("%s: Checking circuits for heat pump control: %s", DOMAIN, circuits)

            any_circuit_on = False
            for entity_id in circuits:
                state = self._hass.states.get(entity_id)
                if state and state.state == "on":
                    any_circuit_on = True
                    _LOGGER.debug("%s: Circuit %s is active", DOMAIN, entity_id)
                    break

            effective_mode: HVACMode | None = None
            if any_circuit_on:
                effective_mode = await self._async_set_flow_temperature()

            self._update_pump_status(any_circuit_on, effective_mode)
        except Exception as exc:  # pragma: no cover - defensive logging
            _LOGGER.error("%s: Error updating heat pump state: %s", DOMAIN, exc)

    async def _async_set_flow_temperature(self) -> HVACMode | None:
        """Calculate and set the flow temperature using the weather-compensation curve."""
        outside_sensor = self._outside_temp_sensor()
        has_target_entity = self._flow_temp_entity() or self._flow_temp_number()

        if not outside_sensor or not has_target_entity:
            _LOGGER.debug(
                "%s: Flow temperature update skipped, missing config", DOMAIN
            )
            return None

        outside_temp_state = self._hass.states.get(outside_sensor)
        if not outside_temp_state:
            _LOGGER.error("Outside temperature sensor not found: %s", outside_sensor)
            return None

        try:
            outside_temp = float(outside_temp_state.state)
        except (TypeError, ValueError):
            _LOGGER.error(
                "Invalid outside temperature value from %s: %s",
                outside_sensor,
                outside_temp_state.state,
            )
            outside_temp = None

        operation = self.get_operation_mode()
        if operation == "off":
            _LOGGER.debug("%s: Heat pump mode off, skipping flow update", DOMAIN)
            return None

        if operation == "cool":
            effective_mode = HVACMode.COOL
        elif operation == "heat":
            effective_mode = HVACMode.HEAT
        else:
            effective_mode = self.determine_auto_mode()

        flow_temp = self.determine_flow_temperature(effective_mode, outside_temp)

        _LOGGER.debug(
            "%s: Setting flow temperature to %.1f°C (mode=%s, outside=%s)",
            DOMAIN,
            flow_temp,
            effective_mode,
            outside_temp,
        )

        self._last_flow_temp = flow_temp

        if (number_entity := self._flow_temp_number()) is not None:
            number_entity.set_calculated_value(flow_temp)
            return effective_mode

        if flow_temp_entity := self._flow_temp_entity():
            await self._hass.services.async_call(
                "input_number",
                "set_value",
                {"entity_id": flow_temp_entity, "value": flow_temp},
                blocking=True,
            )
        return effective_mode

    def refresh_entry_config(self, entry_config: dict[str, Any]) -> None:
        """Update internal reference to the config entry (for reload scenarios)."""
        self._entry_config = entry_config
