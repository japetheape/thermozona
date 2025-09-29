"""Binary sensor platform for Thermozona helper entities."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up Thermozona binary sensor entities."""
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
        [ThermozonaHeatPumpDemandSensor(config_entry.entry_id, controller)]
    )


class ThermozonaHeatPumpDemandSensor(BinarySensorEntity):
    """Expose whether the heat pump currently has demand."""

    _attr_has_entity_name = True
    _attr_name = "Thermozona Heat Pump Demand"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry_id: str,
        controller: HeatPumpController,
    ) -> None:
        self._controller = controller
        self._attr_unique_id = f"{entry_id}_heat_pump_demand"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "Thermozona",
        }
        self._attr_is_on: bool = False

    async def async_added_to_hass(self) -> None:
        """Register the sensor with the heat pump controller."""
        await super().async_added_to_hass()
        self.async_write_ha_state()
        self._controller.register_pump_sensor(self)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the sensor when removed."""
        self._controller.unregister_pump_sensor(self)
        await super().async_will_remove_from_hass()

    def update_state(self, active: bool) -> None:
        """Push the latest demand state into Home Assistant."""
        self._attr_is_on = active
        self.async_write_ha_state()
