"""Thermozona integration entrypoint."""
from homeassistant.config import async_hass_config_yaml
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

DOMAIN = "thermozona"
PLATFORMS = [Platform.CLIMATE, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]

SERVICE_RELOAD = "reload"

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
CONF_HYSTERESIS = "hysteresis"

ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CIRCUITS): [cv.entity_id],
        vol.Required(CONF_TEMP_SENSOR): cv.entity_id,
        vol.Optional(CONF_HYSTERESIS): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, max=5),
        ),
    }
)

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


async def _async_load_yaml_config(hass: HomeAssistant) -> dict:
    """Return the current Thermozona YAML configuration."""
    yaml_config = await async_hass_config_yaml(hass)
    domain_config = yaml_config.get(DOMAIN)
    if domain_config is None:
        raise HomeAssistantError(
            "Thermozona is not configured in configuration.yaml"
        )

    return domain_config


def _validate_domain_config(domain_config: dict) -> dict:
    """Validate Thermozona YAML config against CONFIG_SCHEMA."""
    try:
        validated_config = CONFIG_SCHEMA({DOMAIN: domain_config})[DOMAIN]
    except vol.Invalid as err:
        raise HomeAssistantError(
            f"Invalid Thermozona configuration: {err}"
        ) from err

    return validated_config


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Thermozona component."""
    if DOMAIN not in config:
        return True

    hass.data[DOMAIN] = {}

    async def _async_handle_reload(_: ServiceCall) -> None:
        """Handle the reload service to re-import YAML configuration."""
        domain_config = await _async_load_yaml_config(hass)
        validated_config = _validate_domain_config(domain_config)

        entries = hass.config_entries.async_entries(DOMAIN)
        if entries:
            entry = entries[0]
            hass.config_entries.async_update_entry(entry, data=validated_config)
            await hass.config_entries.async_reload(entry.entry_id)
            return

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=validated_config,
            )
        )

    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=_validate_domain_config(config[DOMAIN]),
        )
    )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thermozona from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    domain_config = await _async_load_yaml_config(hass)
    validated_config = _validate_domain_config(domain_config)
    hass.config_entries.async_update_entry(entry, data=validated_config)

    hass.data[DOMAIN][entry.entry_id] = validated_config

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
