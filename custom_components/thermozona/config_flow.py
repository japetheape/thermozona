"""Config flow for the Thermozona integration."""
import logging
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

class ThermozonaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thermozona."""

    VERSION = 1

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        """Import a config entry from configuration.yaml."""
        _LOGGER.debug("Starting async_step_import with config: %s", import_config)

        # Voorkom dubbele entries
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="Thermozona",
            data=import_config
        )

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        # We gebruiken alleen configuration.yaml voor setup
        return self.async_abort(
            reason="configuration_yaml_only",
            description_placeholders={
                "readme_url": "https://github.com/thermozona/thermozona/blob/main/README.md#configuration",
            },
        )
