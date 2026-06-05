"""Number platform for GaggiMate integration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, UNIQUE_ID_TARGET_TEMP_SETPOINT, CONF_TEMPERATURE_UNIT
from .coordinator import GaggiMateCoordinator
from .sensor import GaggiMateEntity

_LOGGER = logging.getLogger(__name__)

MIN_TEMP_C = 0
MAX_TEMP_C = 160
MIN_TEMP_F = 32
MAX_TEMP_F = 320


@dataclass(frozen=True, kw_only=True)
class GaggiMateNumberEntityDescription(NumberEntityDescription):
    """Describe a GaggiMate number."""

    value_fn: Callable[[dict[str, Any], GaggiMateCoordinator], float | None]
    set_value_fn: Callable[[GaggiMateCoordinator, float], Awaitable[None]]


SENSORS: tuple[GaggiMateNumberEntityDescription, ...] = (
    GaggiMateNumberEntityDescription(
        key=UNIQUE_ID_TARGET_TEMP_SETPOINT,
        name="Target Temperature Setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=MIN_TEMP_C,
        native_max_value=MAX_TEMP_C,
        native_step=1,
        mode=NumberMode.BOX,
        icon="mdi:thermometer",
        value_fn=lambda data, _: None if data.get("tt") is None else float(data.get("tt")),
        set_value_fn=lambda coordinator, value: coordinator.set_temperature(value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GaggiMate number entities."""
    coordinator: GaggiMateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        GaggiMateNumber(coordinator, entry, description) for description in SENSORS
    )


class GaggiMateNumber(GaggiMateEntity, NumberEntity):
    """Generic GaggiMate number driven by descriptions."""

    entity_description: GaggiMateNumberEntityDescription

    def __init__(
        self,
        coordinator: GaggiMateCoordinator,
        entry: ConfigEntry,
        description: GaggiMateNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.host}_{description.key}"
        self._attr_name = description.name

    @property
    def native_unit_of_measurement(self) -> str:
        unit = self._entry.options.get(CONF_TEMPERATURE_UNIT, "C")
        return UnitOfTemperature.FAHRENHEIT if unit == "F" else UnitOfTemperature.CELSIUS

    @property
    def native_min_value(self) -> float:
        unit = self._entry.options.get(CONF_TEMPERATURE_UNIT, "C")
        return float(MIN_TEMP_F) if unit == "F" else float(MIN_TEMP_C)

    @property
    def native_max_value(self) -> float:
        unit = self._entry.options.get(CONF_TEMPERATURE_UNIT, "C")
        return float(MAX_TEMP_F) if unit == "F" else float(MAX_TEMP_C)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        value_c = self.entity_description.value_fn(data, self.coordinator)
        if value_c is None:
            return None
        unit = self._entry.options.get(CONF_TEMPERATURE_UNIT, "C")
        if unit == "F":
            return round(value_c * 9 / 5 + 32, 1)
        return value_c

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        unit = self._entry.options.get(CONF_TEMPERATURE_UNIT, "C")
        value_c = (value - 32) * 5 / 9 if unit == "F" else value
        try:
            await self.entity_description.set_value_fn(self.coordinator, value_c)
            _LOGGER.debug("Set %s to %s", self.entity_description.key, value)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set %s: %s", self.entity_description.key, err)
            raise
