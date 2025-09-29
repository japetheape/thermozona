"""Helper utilities for the Thermozona integration."""
from __future__ import annotations

from typing import Any

from . import CONF_CIRCUITS


def resolve_circuits(zone_config: dict[str, Any]) -> list[str]:
    """Return the configured circuits, falling back to legacy groups."""
    circuits = zone_config.get(CONF_CIRCUITS)
    if circuits is None:
        circuits = zone_config.get("groups")
    return circuits or []
