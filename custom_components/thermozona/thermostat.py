"""Thermostat entity for the Thermozona integration."""
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
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .heat_pump import HeatPumpController

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)


class ThermozonaThermostat(ClimateEntity):
    """Representation of a Thermozona thermostat."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
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
        self._attr_name = f"Thermozona {zone_name}"
        self._attr_unique_id = f"thermozona_{zone_name}"
        self._zone_name = zone_name
        self._circuits = circuits
        self._temp_sensor = temp_sensor
        self._attr_target_temperature = 20
        self._attr_hvac_action = HVACAction.OFF
        self._remove_update_handler = None
        self._remove_mode_listener = None
        self._controller = controller
        self._pending_control = False
        self._reschedule_control = False
        self._manual_mode: HVACMode = HVACMode.AUTO
        self._effective_mode: HVACMode = HVACMode.AUTO

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        self._controller.register_thermostat(self)

        # Start periodieke temperatuurcontrole
        self._remove_update_handler = async_track_time_interval(
            self.hass,
            self._async_update_temp,
            SCAN_INTERVAL,
        )
        if (mode_entity := self._controller.mode_entity) is not None:
            self._remove_mode_listener = async_track_state_change_event(
                self.hass,
                mode_entity,
                self._handle_pump_mode_change,
            )

        # Trigger initial evaluation with current readings
        self.async_schedule_control()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed."""
        if self._remove_update_handler is not None:
            self._remove_update_handler()
        if self._remove_mode_listener is not None:
            self._remove_mode_listener()
        self._controller.update_zone_status(
            self._zone_name, target=None, current=None, source=self
        )
        self._controller.unregister_thermostat(self)

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
        if hvac_mode not in (HVACMode.AUTO, HVACMode.OFF):
            _LOGGER.warning(
                "%s: Unsupported hvac mode %s requested; only AUTO/OFF allowed",
                self._attr_name,
                hvac_mode,
            )
            return

        _LOGGER.debug("%s: Setting manual HVAC mode to %s", self._attr_name, hvac_mode)
        self._manual_mode = hvac_mode
        await self._control_heating()

    async def async_turn_on(self) -> None:
        """Turn the thermostat on (enable circuits under pump control)."""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self) -> None:
        """Turn the thermostat off (force circuits closed)."""
        await self.async_set_hvac_mode(HVACMode.OFF)

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
            self.hvac_mode,
            self._attr_target_temperature,
            self.current_temperature,
        )

        if self._manual_mode == HVACMode.OFF:
            _LOGGER.debug("%s: HVAC mode is OFF, turning off all circuits", self._attr_name)
            self._controller.update_zone_status(
                self._zone_name, target=None, current=None, source=self
            )
            await self._set_circuits_state(False)
            self._attr_hvac_action = HVACAction.OFF
            self._effective_mode = HVACMode.OFF
            self.async_write_ha_state()
            return

        current_temp = self.current_temperature
        if current_temp is None:
            _LOGGER.warning("%s: No current temperature available", self._attr_name)
            self._controller.update_zone_status(
                self._zone_name, target=None, current=None, source=self
            )
            return

        active_before = self._circuits_are_active()
        self._controller.update_zone_status(
            self._zone_name,
            target=self._attr_target_temperature,
            current=current_temp,
            active=active_before,
            source=self,
        )

        pump_mode = self._controller.get_operation_mode()

        if pump_mode == "cool":
            effective_mode = HVACMode.COOL
        elif pump_mode == "heat":
            effective_mode = HVACMode.HEAT
        else:  # auto or unknown
            effective_mode = self._controller.determine_auto_mode()

        if pump_mode != "auto":
            _LOGGER.debug(
                "%s: Pump mode %s drives effective mode %s",
                self._attr_name,
                pump_mode,
                effective_mode,
            )

        hysteresis = 0.3  # 0.3°C hysterese
        target = self._attr_target_temperature

        if effective_mode == HVACMode.HEAT:
            should_activate = current_temp < (target - hysteresis)
            should_deactivate = current_temp > (target + hysteresis)
            active_action = HVACAction.HEATING
        else:
            should_activate = current_temp > (target + hysteresis)
            should_deactivate = current_temp < (target - hysteresis)
            active_action = HVACAction.COOLING

        if should_activate:
            _LOGGER.debug(
                "%s: Activating circuits (pump_mode=%s, effective=%s, current=%s, target=%s)",
                self._attr_name,
                pump_mode,
                effective_mode,
                current_temp,
                target,
            )
            await self._set_circuits_state(True)
            self._attr_hvac_action = active_action
        elif should_deactivate:
            _LOGGER.debug(
                "%s: Deactivating circuits (pump_mode=%s, effective=%s, current=%s, target=%s)",
                self._attr_name,
                pump_mode,
                effective_mode,
                current_temp,
                target,
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
                active_action if self._circuits_are_active() else HVACAction.IDLE
            )

        self._effective_mode = effective_mode
        active_after = self._circuits_are_active()
        self._controller.update_zone_status(
            self._zone_name,
            target=self._attr_target_temperature,
            current=current_temp,
            active=active_after,
            source=self,
        )
        self.async_write_ha_state()

    async def _handle_pump_mode_change(self, event) -> None:
        """React to global heat pump mode changes."""
        _LOGGER.debug(
            "%s: Heat pump mode changed, re-evaluating control (event=%s)",
            self._attr_name,
            event,
        )
        self.async_schedule_control()

    def async_schedule_control(self) -> None:
        """Schedule a control evaluation if one isn't already running."""
        if self._pending_control:
            self._reschedule_control = True
            return

        async def _run() -> None:
            try:
                await self._control_heating()
            finally:
                self._pending_control = False
                if self._reschedule_control:
                    self._reschedule_control = False
                    self.async_schedule_control()

        self._pending_control = True
        self._reschedule_control = False
        self.hass.async_create_task(_run())

    async def _set_circuits_state(self, state: bool) -> None:
        """Set all circuits to the specified state."""
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

        if not state and self._manual_mode == HVACMode.OFF:
            self._attr_hvac_action = HVACAction.OFF

        await self._controller.async_update_heat_pump_state()

    def _circuits_are_active(self) -> bool:
        """Return True if any circuit is currently on."""
        for circuit_entity_id in self._circuits:
            state = self.hass.states.get(circuit_entity_id)
            if state and state.state == "on":
                return True
        return False

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.OFF if self._manual_mode == HVACMode.OFF else HVACMode.AUTO

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode.AUTO, HVACMode.OFF]
