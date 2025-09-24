"""Heat pump controller for the Underfloor Heating integration."""
from __future__ import annotations

import logging
import weakref
from typing import Any, TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.components.climate import HVACMode

from . import (
    CONF_FLOW_TEMP_SENSOR,
    CONF_HEAT_PUMP_MODE,
    CONF_HEAT_PUMP_SWITCH,
    CONF_OUTSIDE_TEMP_SENSOR,
    CONF_ZONES,
    DOMAIN,
)
from .helpers import resolve_circuits

if TYPE_CHECKING:
    from .thermostat import FloorHeatingThermostat

_LOGGER = logging.getLogger(__name__)


class HeatPumpController:
    """Coordinate state updates for the shared heat pump."""

    def __init__(self, hass: HomeAssistant, entry_config: dict[str, Any]) -> None:
        self._hass = hass
        self._entry_config = entry_config
        self._zone_status: dict[str, dict[str, float]] = {}
        self._last_auto_mode: HVACMode = HVACMode.HEAT
        self._thermostats: weakref.WeakSet[FloorHeatingThermostat] = weakref.WeakSet()


    def _heat_pump_switch(self) -> str | None:
        return self._entry_config.get(CONF_HEAT_PUMP_SWITCH)

    def _outside_temp_sensor(self) -> str | None:
        return self._entry_config.get(CONF_OUTSIDE_TEMP_SENSOR)

    def _flow_temp_entity(self) -> str | None:
        return self._entry_config.get(CONF_FLOW_TEMP_SENSOR)

    def get_all_circuit_entities(self) -> list[str]:
        """Return all circuit entities across the configured zones."""
        circuits: list[str] = []
        for zone_config in self._entry_config.get(CONF_ZONES, {}).values():
            circuits.extend(resolve_circuits(zone_config))
        return circuits

    def get_operation_mode(self) -> str:
        """Return the current heat pump operation mode (heat/cool/auto)."""
        mode_entity = self._entry_config.get(CONF_HEAT_PUMP_MODE)
        if not mode_entity:
            return "auto"

        state = self._hass.states.get(mode_entity)
        if not state:
            _LOGGER.warning("%s: Heat pump mode entity %s not found", DOMAIN, mode_entity)
            return "auto"

        value = state.state.lower()
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
        return self._entry_config.get(CONF_HEAT_PUMP_MODE)

    def update_zone_status(
        self,
        zone_name: str,
        *,
        target: float | None,
        current: float | None,
        active: bool | None = None,
        source: FloorHeatingThermostat | None = None,
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

    def register_thermostat(self, thermostat: FloorHeatingThermostat) -> None:
        """Register a thermostat for notifications."""
        self._thermostats.add(thermostat)

    def unregister_thermostat(self, thermostat: FloorHeatingThermostat) -> None:
        """Unregister a thermostat."""
        self._thermostats.discard(thermostat)

    def _notify_thermostats(
        self, *, skip: FloorHeatingThermostat | None = None
    ) -> None:
        """Ask all thermostats (except the source) to re-evaluate control."""
        for thermostat in list(self._thermostats):
            if thermostat is skip:
                continue
            thermostat.async_schedule_control()

    async def async_update_heat_pump_state(self) -> None:
        """Update the heat pump switch and flow temperature based on circuit state."""
        try:
            heat_pump_switch = self._heat_pump_switch()
            if not heat_pump_switch:
                _LOGGER.debug("%s: No heat pump switch configured", DOMAIN)
                return

            circuits = self.get_all_circuit_entities()
            _LOGGER.debug("%s: Checking circuits for heat pump control: %s", DOMAIN, circuits)

            any_circuit_on = False
            for entity_id in circuits:
                state = self._hass.states.get(entity_id)
                if state and state.state == "on":
                    any_circuit_on = True
                    _LOGGER.debug("%s: Circuit %s is active", DOMAIN, entity_id)
                    break

            await self._hass.services.async_call(
                "input_boolean",
                "turn_on" if any_circuit_on else "turn_off",
                {"entity_id": heat_pump_switch},
                blocking=True,
            )

            if any_circuit_on:
                await self._async_set_flow_temperature()
        except Exception as exc:  # pragma: no cover - defensive logging
            _LOGGER.error("%s: Error updating heat pump state: %s", DOMAIN, exc)

    async def _async_set_flow_temperature(self) -> None:
        """Calculate and set the flow temperature using the weather-compensation curve."""
        outside_sensor = self._outside_temp_sensor()
        flow_temp_entity = self._flow_temp_entity()

        if not outside_sensor or not flow_temp_entity:
            _LOGGER.debug("%s: Flow temperature update skipped, missing config", DOMAIN)
            return

        outside_temp_state = self._hass.states.get(outside_sensor)
        if not outside_temp_state:
            _LOGGER.error("Outside temperature sensor not found: %s", outside_sensor)
            return

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

        await self._hass.services.async_call(
            "input_number",
            "set_value",
            {"entity_id": flow_temp_entity, "value": flow_temp},
            blocking=True,
        )

    def refresh_entry_config(self, entry_config: dict[str, Any]) -> None:
        """Update internal reference to the config entry (for reload scenarios)."""
        self._entry_config = entry_config
