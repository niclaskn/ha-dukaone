"""
Sensor platform for Duka One.

see http://www.dingus.dk for more information
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DukaConfigEntry
from .dukaentity import DukaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DukaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Duka One humidity sensor."""
    async_add_entities([DukaOneHumidity(entry)])


class DukaOneHumidity(DukaEntity, SensorEntity):
    """A Duka One humidity sensor (pushed)."""

    _attr_translation_key = "humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, entry: DukaConfigEntry) -> None:
        super().__init__(entry)
        # Same id as the fan (different platform): keeps the existing history.
        self._attr_unique_id = self._device_id

    @property
    def native_value(self) -> int | None:
        """Return the humidity."""
        return self.device.humidity
