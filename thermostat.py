"""Thermostat entity for the Underfloor Heating integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .heat_pump import HeatPumpController

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)


class FloorHeatingThermostat(ClimateEntity):
    """Representation of a Floor Heating Thermostat."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5
    _attr_max_temp = 30
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        hass: HomeAssistant,
        zone_name: str,
        circuits: list[str],
        temp_sensor: str | None,
        controller: HeatPumpController,
    ) -> None:
        """Initialize the thermostat."""
        self.hass = hass
        self._attr_name = f"Vloerverwarming {zone_name}"
        self._attr_unique_id = f"underfloorheating_{zone_name}"
        self._circuits = circuits
        self._temp_sensor = temp_sensor
        self._attr_target_temperature = 20
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._remove_update_handler = None
        self._controller = controller
        self._is_heating = False

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Start periodieke temperatuurcontrole
        self._remove_update_handler = async_track_time_interval(
            self.hass,
            self._async_update_temp,
            SCAN_INTERVAL,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed."""
        if self._remove_update_handler is not None:
            self._remove_update_handler()

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if not self._temp_sensor:
            _LOGGER.warning("%s: No temperature sensor configured", self._attr_name)
            return None
        temp_state = self.hass.states.get(self._temp_sensor)
        _LOGGER.debug(
            "%s: Getting temperature from %s: State=%s",
            self._attr_name,
            self._temp_sensor,
            temp_state.state if temp_state else "None",
        )

        if temp_state is None:
            _LOGGER.warning(
                "%s: Temperature sensor %s not found",
                self._attr_name,
                self._temp_sensor,
            )
            return None

        try:
            return float(temp_state.state)
        except (ValueError, TypeError) as exc:
            _LOGGER.error(
                "%s: Could not convert temperature '%s' to float: %s",
                self._attr_name,
                temp_state.state,
                exc,
            )
            return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            _LOGGER.warning("No temperature provided in set_temperature call")
            return

        _LOGGER.debug(
            "%s: Setting temperature to %s (current: %s)",
            self._attr_name,
            temperature,
            self.current_temperature,
        )

        self._attr_target_temperature = temperature
        await self._control_heating()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        _LOGGER.debug("%s: Setting HVAC mode to %s", self._attr_name, hvac_mode)
        self._attr_hvac_mode = hvac_mode
        await self._control_heating()

    async def _async_update_temp(self, *_) -> None:
        """Update temperature and control heating periodically."""
        _LOGGER.debug(
            "%s: Periodic temperature check - Current: %s, Target: %s",
            self._attr_name,
            self.current_temperature,
            self._attr_target_temperature,
        )
        await self._control_heating()

    async def _control_heating(self) -> None:
        """Control the heating based on temperature difference."""
        _LOGGER.debug(
            "%s: Controlling heating - Mode: %s, Target: %s, Current: %s",
            self._attr_name,
            self._attr_hvac_mode,
            self._attr_target_temperature,
            self.current_temperature,
        )

        if self._attr_hvac_mode == HVACMode.OFF:
            _LOGGER.debug("%s: HVAC mode is OFF, turning off all circuits", self._attr_name)
            await self._set_circuits_state(False)
            self._attr_hvac_action = HVACAction.OFF
            self.async_write_ha_state()
            return

        current_temp = self.current_temperature
        if current_temp is None:
            _LOGGER.warning("%s: No current temperature available", self._attr_name)
            return

        # Voeg hysterese toe om te voorkomen dat het systeem te vaak schakelt
        hysteresis = 0.3  # 0.3°C hysterese
        should_heat = current_temp < (self._attr_target_temperature - hysteresis)
        should_stop = current_temp > (self._attr_target_temperature + hysteresis)

        if should_heat:
            _LOGGER.debug(
                "%s: Current temp (%s) < target-hysteresis (%s), turning heating on",
                self._attr_name,
                current_temp,
                self._attr_target_temperature - hysteresis,
            )
            await self._set_circuits_state(True)
            self._attr_hvac_action = HVACAction.HEATING
        elif should_stop:
            _LOGGER.debug(
                "%s: Current temp (%s) > target+hysteresis (%s), turning heating off",
                self._attr_name,
                current_temp,
                self._attr_target_temperature + hysteresis,
            )
            await self._set_circuits_state(False)
            self._attr_hvac_action = HVACAction.IDLE
        else:
            _LOGGER.debug(
                "%s: Temperature (%s) within hysteresis range, maintaining current state",
                self._attr_name,
                current_temp,
            )
            self._attr_hvac_action = (
                HVACAction.HEATING if self._is_heating else HVACAction.IDLE
            )
            self.async_write_ha_state()
            return

        self.async_write_ha_state()

    async def _set_circuits_state(self, state: bool) -> None:
        """Set all circuits to the specified state."""
        if self._is_heating == state:
            return

        for circuit_entity_id in self._circuits:
            _LOGGER.debug(
                "%s: %s circuit %s",
                self._attr_name,
                "Turning on" if state else "Turning off",
                circuit_entity_id,
            )
            try:
                # Controleer of het een geldige entity_id is
                if not circuit_entity_id.startswith("input_boolean."):
                    _LOGGER.error(
                        "%s: Invalid entity_id format: %s",
                        self._attr_name,
                        circuit_entity_id,
                    )
                    continue

                await self.hass.services.async_call(
                    "input_boolean",
                    "turn_on" if state else "turn_off",
                    {"entity_id": circuit_entity_id},
                    blocking=True,
                )
            except Exception as exc:  # pragma: no cover - safeguard against service errors
                _LOGGER.error(
                    "%s: Error setting state for circuit %s: %s",
                    self._attr_name,
                    circuit_entity_id,
                    exc,
                )

        self._is_heating = state
        if not state and self._attr_hvac_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF

        await self._controller.async_update_heat_pump_state()
