"""Climate platform for Floor Heating integration."""
import logging
from typing import Any
from datetime import timedelta
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval

from . import (
    DOMAIN,
    CONF_HEAT_PUMP_SWITCH,
    CONF_OUTSIDE_TEMP_SENSOR,
    CONF_FLOW_TEMP_SENSOR,
    CONF_ZONES,
    CONF_CIRCUITS,
    CONF_TEMP_SENSOR,
)

_LOGGER = logging.getLogger(__name__)


def _resolve_circuits(zone_config: dict[str, Any]) -> list[str]:
    """Return the configured circuits, falling back to legacy groups."""
    circuits = zone_config.get(CONF_CIRCUITS)
    if circuits is None:
        circuits = zone_config.get("groups")
    return circuits or []

SCAN_INTERVAL = timedelta(minutes=1)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Floor Heating climate devices."""
    _LOGGER.debug("Setting up climate platform")
    zones = hass.data[DOMAIN][config_entry.entry_id]["zones"]
    _LOGGER.debug("Found zones: %s", zones)
    
    entities = []
    for zone_name, config in zones.items():
        _LOGGER.debug("Creating thermostat for zone: %s with config: %s", zone_name, config)
        circuits = _resolve_circuits(config)
        if not circuits:
            _LOGGER.error("%s: No circuits defined for zone %s", DOMAIN, zone_name)
            continue
        entities.append(
            FloorHeatingThermostat(
                hass,
                zone_name,
                circuits,
                config.get(CONF_TEMP_SENSOR),
            )
        )
    
    async_add_entities(entities)

class FloorHeatingThermostat(ClimateEntity):
    """Representation of a Floor Heating Thermostat."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
    )
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
    ) -> None:
        """Initialize the thermostat."""
        self.hass = hass
        self._attr_name = f"Vloerverwarming {zone_name}"
        self._attr_unique_id = f"underfloorheating_{zone_name}"
        self._circuits = circuits
        self._temp_sensor = temp_sensor
        self._attr_target_temperature = 20
        self._attr_hvac_mode = HVACMode.OFF
        self._remove_update_handler = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()
        
        # Start periodieke temperatuurcontrole
        self._remove_update_handler = async_track_time_interval(
            self.hass,
            self._async_update_temp,
            SCAN_INTERVAL
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
            temp_state.state if temp_state else "None"
        )
        
        if temp_state is None:
            _LOGGER.warning(
                "%s: Temperature sensor %s not found",
                self._attr_name,
                self._temp_sensor
            )
            return None
            
        try:
            return float(temp_state.state)
        except (ValueError, TypeError) as e:
            _LOGGER.error(
                "%s: Could not convert temperature '%s' to float: %s",
                self._attr_name,
                temp_state.state,
                str(e)
            )
            return None

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            _LOGGER.warning("No temperature provided in set_temperature call")
            return
        
        _LOGGER.debug(
            "%s: Setting temperature to %s (current: %s)", 
            self._attr_name, 
            temperature, 
            self.current_temperature
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
            self._attr_target_temperature
        )
        await self._control_heating()

    async def _control_heating(self) -> None:
        """Control the heating based on temperature difference."""
        _LOGGER.debug(
            "%s: Controlling heating - Mode: %s, Target: %s, Current: %s",
            self._attr_name,
            self._attr_hvac_mode,
            self._attr_target_temperature,
            self.current_temperature
        )

        if self._attr_hvac_mode == HVACMode.OFF:
            _LOGGER.debug("%s: HVAC mode is OFF, turning off all circuits", self._attr_name)
            await self._set_circuits_state(False)
            return

        current_temp = self.current_temperature
        if current_temp is None:
            _LOGGER.warning("%s: No current temperature available", self._attr_name)
            return

        # Voeg hysterese toe om te voorkomen dat het systeem te vaak schakelt
        HYSTERESIS = 0.3  # 0.3°C hysterese
        should_heat = current_temp < (self._attr_target_temperature - HYSTERESIS)
        should_stop = current_temp > (self._attr_target_temperature + HYSTERESIS)

        if should_heat:
            _LOGGER.debug(
                "%s: Current temp (%s) < target-hysteresis (%s), turning heating on",
                self._attr_name,
                current_temp,
                self._attr_target_temperature - HYSTERESIS
            )
            await self._set_circuits_state(True)
        elif should_stop:
            _LOGGER.debug(
                "%s: Current temp (%s) > target+hysteresis (%s), turning heating off",
                self._attr_name,
                current_temp,
                self._attr_target_temperature + HYSTERESIS
            )
            await self._set_circuits_state(False)
        else:
            _LOGGER.debug(
                "%s: Temperature (%s) within hysteresis range, maintaining current state",
                self._attr_name,
                current_temp
            )

    async def _set_circuits_state(self, state: bool) -> None:
        """Set all circuits to the specified state."""
        for circuit_entity_id in self._circuits:
            _LOGGER.debug(
                "%s: %s circuit %s", 
                self._attr_name,
                "Turning on" if state else "Turning off",
                circuit_entity_id
            )
            try:
                # Controleer of het een geldige entity_id is
                if not circuit_entity_id.startswith("input_boolean."):
                    _LOGGER.error(
                        "%s: Invalid entity_id format: %s", 
                        self._attr_name, 
                        circuit_entity_id
                    )
                    continue
                    
                await self.hass.services.async_call(
                    "input_boolean",
                    "turn_on" if state else "turn_off",
                    {"entity_id": circuit_entity_id},
                    blocking=True
                )
            except Exception as e:
                _LOGGER.error(
                    "%s: Error setting state for circuit %s: %s",
                    self._attr_name,
                    circuit_entity_id,
                    str(e)
                )
        
        await self._update_heat_pump_state()

    async def _update_heat_pump_state(self) -> None:
        """Update heat pump status and flow temperature."""
        try:
            _LOGGER.debug("%s: Starting heat pump state update", self._attr_name)
            
            # Get config data
            domain_data = self.hass.data[DOMAIN]
            if isinstance(domain_data, dict):
                if "zones" in domain_data:  # Direct setup structure
                    config = domain_data
                else:  # Config entry structure
                    config = domain_data[next(iter(domain_data))]
            
            _LOGGER.debug("%s: Current config: %s", self._attr_name, config)
            
            heat_pump_switch = config.get(CONF_HEAT_PUMP_SWITCH)
            if not heat_pump_switch:
                _LOGGER.debug("%s: No heat pump switch in config, available keys: %s", 
                            self._attr_name, list(config.keys()))
                return

            circuits = await self._get_all_circuit_entities()
            any_circuit_on = False
            for entity_id in circuits:
                state = self.hass.states.get(entity_id)
                if state and state.state == "on":
                    any_circuit_on = True
                    _LOGGER.debug("%s: Found active circuit: %s", self._attr_name, entity_id)
                    break

            _LOGGER.debug("%s: Any circuits active: %s, %s", self._attr_name, any_circuit_on, circuits)

            # Update heat pump status
            await self.hass.services.async_call(
                "input_boolean",
                "turn_on" if any_circuit_on else "turn_off",
                {"entity_id": heat_pump_switch},
                blocking=True
            )

            if any_circuit_on:
                await self._set_flow_temperature()

        except Exception as e:
            _LOGGER.error("%s: Error updating heat pump state: %s", self._attr_name, str(e))

    async def _set_flow_temperature(self) -> None:
        """Bereken en zet aanvoertemperatuur op basis van stooklijn."""
        try:
            config = self.hass.data[DOMAIN][next(iter(self.hass.data[DOMAIN]))]
            outside_temp_entity = config[CONF_OUTSIDE_TEMP_SENSOR]
            flow_temp_entity = config[CONF_FLOW_TEMP_SENSOR]
            
            outside_temp_state = self.hass.states.get(outside_temp_entity)
            
            if not outside_temp_state:
                _LOGGER.error("Outside temperature sensor not found: %s", outside_temp_entity)
                return
                
            try:
                outside_temp = float(outside_temp_state.state)
            except (ValueError, TypeError):
                _LOGGER.error("Invalid outside temperature value: %s", outside_temp_state.state)
                return
            
            # Simpele lineaire stooklijn
            flow_temp = 45 - ((outside_temp + 10) * (45 - 25) / 30)
            flow_temp = min(45, max(25, flow_temp))  # Begrens tussen 25 en 45°C
            
            _LOGGER.debug(
                "Calculating flow temperature - Outside: %s°C, Flow: %s°C",
                outside_temp,
                flow_temp
            )
            
            # Gebruik de geconfigureerde entity voor de aanvoertemperatuur
            await self.hass.services.async_call(
                "input_number",
                "set_value",
                {
                    "entity_id": flow_temp_entity,
                    "value": flow_temp
                },
                blocking=True
            )
        except Exception as e:
            _LOGGER.error("Error setting flow temperature: %s", str(e))

    async def _get_all_circuit_entities(self) -> list[str]:
        """Get all circuit entities from all zones."""
        config = self.hass.data[DOMAIN][next(iter(self.hass.data[DOMAIN]))]
        all_circuits: list[str] = []

        # Loop through all zones to collect all circuits
        for zone_config in config.get(CONF_ZONES, {}).values():
            all_circuits.extend(_resolve_circuits(zone_config))

        _LOGGER.debug("%s: Found all circuits across zones: %s", self._attr_name, all_circuits)
        return all_circuits
