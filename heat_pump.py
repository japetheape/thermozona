"""Heat pump controller for the Underfloor Heating integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from . import (
    CONF_FLOW_TEMP_SENSOR,
    CONF_HEAT_PUMP_SWITCH,
    CONF_OUTSIDE_TEMP_SENSOR,
    CONF_ZONES,
    DOMAIN,
)
from .helpers import resolve_circuits

_LOGGER = logging.getLogger(__name__)


class HeatPumpController:
    """Coordinate state updates for the shared heat pump."""

    def __init__(self, hass: HomeAssistant, entry_config: dict[str, Any]) -> None:
        self._hass = hass
        self._entry_config = entry_config

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
            return

        flow_temp = 45 - ((outside_temp + 10) * (45 - 25) / 30)
        flow_temp = min(45, max(25, flow_temp))

        _LOGGER.debug(
            "%s: Setting flow temperature to %.1f°C based on outside %.1f°C",
            DOMAIN,
            flow_temp,
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
