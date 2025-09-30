"""Sensor platform for Thermozona helper entities."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .heat_pump import HeatPumpController

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Thermozona sensor entities."""
    domain_data = hass.data[DOMAIN]
    entry_config = domain_data[config_entry.entry_id]

    controllers = domain_data.setdefault("controllers", {})
    controller = controllers.get(config_entry.entry_id)
    if controller is None:
        controller = HeatPumpController(hass, entry_config)
    else:
        controller.refresh_entry_config(entry_config)
    controllers[config_entry.entry_id] = controller

    async_add_entities(
        [ThermozonaHeatPumpStatusSensor(config_entry.entry_id, controller)]
    )


class ThermozonaHeatPumpStatusSensor(SensorEntity):
    """Expose the current heat-pump direction (heat/cool/idle)."""

    _attr_has_entity_name = True
    _attr_name = "Heat Pump Status"
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:hvac"

    def __init__(
        self,
        entry_id: str,
        controller: HeatPumpController,
    ) -> None:
        self._controller = controller
        self._attr_unique_id = f"{entry_id}_heat_pump_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "Thermozona",
        }
        self._attr_native_value: str = "idle"

    async def async_added_to_hass(self) -> None:
        """Register the sensor with the heat pump controller."""
        await super().async_added_to_hass()
        self.async_write_ha_state()
        self._controller.register_pump_sensor(self)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the sensor when removed."""
        self._controller.unregister_pump_sensor(self)
        await super().async_will_remove_from_hass()

    def update_state(self, state: str) -> None:
        """Push the latest pump state into Home Assistant."""
        if state not in {"heat", "cool", "idle"}:
            state = "idle"
        self._attr_native_value = state
        self.async_write_ha_state()
