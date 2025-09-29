"""Climate platform for the Thermozona integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_TEMP_SENSOR, DOMAIN
from .heat_pump import HeatPumpController
from .helpers import resolve_circuits
from .thermostat import ThermozonaThermostat

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Thermozona climate devices."""
    _LOGGER.debug("Setting up climate platform")
    domain_data = hass.data[DOMAIN]
    entry_config = domain_data[config_entry.entry_id]
    zones = entry_config.get("zones", {})
    _LOGGER.debug("Found zones: %s", zones)

    controllers = domain_data.setdefault("controllers", {})
    controller = controllers.get(config_entry.entry_id)
    if controller is None:
        controller = HeatPumpController(hass, entry_config)
    else:
        controller.refresh_entry_config(entry_config)
    controllers[config_entry.entry_id] = controller

    entities: list[ThermozonaThermostat] = []
    for zone_name, config in zones.items():
        _LOGGER.debug("Creating thermostat for zone: %s with config: %s", zone_name, config)
        circuits = resolve_circuits(config)
        if not circuits:
            _LOGGER.error("%s: No circuits defined for zone %s", DOMAIN, zone_name)
            continue
        entities.append(
            ThermozonaThermostat(
                hass,
                zone_name,
                circuits,
                config.get(CONF_TEMP_SENSOR),
                controller,
            )
        )

    async_add_entities(entities)
