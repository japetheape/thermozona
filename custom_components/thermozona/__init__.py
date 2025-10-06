"""Thermozona integration entrypoint."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

DOMAIN = "thermozona"
PLATFORMS = [Platform.CLIMATE, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]

CONF_ZONES = "zones"
CONF_CIRCUITS = "circuits"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_OUTSIDE_TEMP_SENSOR = "outside_temp_sensor"
CONF_FLOW_TEMP_SENSOR = "flow_temp_sensor"
CONF_HEAT_PUMP_MODE = "heat_pump_mode"
CONF_HEATING_BASE_OFFSET = "heating_base_offset"
CONF_COOLING_BASE_OFFSET = "cooling_base_offset"

DEFAULT_HEATING_BASE_OFFSET = 3.0
DEFAULT_COOLING_BASE_OFFSET = 2.5

ZONE_SCHEMA = vol.Schema({
    vol.Required(CONF_CIRCUITS): [cv.entity_id],
    vol.Required(CONF_TEMP_SENSOR): cv.entity_id,
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_OUTSIDE_TEMP_SENSOR): cv.entity_id,
        vol.Optional(CONF_FLOW_TEMP_SENSOR): cv.entity_id,
        vol.Optional(CONF_HEAT_PUMP_MODE): cv.entity_id,
        vol.Optional(
            CONF_HEATING_BASE_OFFSET,
            default=DEFAULT_HEATING_BASE_OFFSET,
        ): vol.Coerce(float),
        vol.Optional(
            CONF_COOLING_BASE_OFFSET,
            default=DEFAULT_COOLING_BASE_OFFSET,
        ): vol.Coerce(float),
        vol.Required(CONF_ZONES): {
            cv.string: ZONE_SCHEMA
        }
    })
}, extra=vol.ALLOW_EXTRA)



async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Thermozona component."""
    if DOMAIN not in config:
        return True

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["config"] = config[DOMAIN]  # Store complete config

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "import"}, data=config[DOMAIN]
        )
    )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermozona from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    hass.data[DOMAIN][entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        controllers = hass.data[DOMAIN].get("controllers")
        if controllers:
            controllers.pop(entry.entry_id, None)
            if not controllers:
                hass.data[DOMAIN].pop("controllers")
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
