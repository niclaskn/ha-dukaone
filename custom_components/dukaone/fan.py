"""
Platform for Duka One fan.

see http://www.dingus.dk for more information
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from dukaonesdk.device import Mode, Speed
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.config_validation import make_entity_service_schema
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DukaConfigEntry, DukaData
from .const import (
    ATTR_MANUAL_SPEED,
    ATTR_MODE,
    DOMAIN,
    MODE_IN,
    MODE_INOUT,
    MODE_OUT,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MANUAL,
    SPEED_MEDIUM,
    SPEED_OFF,
)
from .dukaentity import DukaEntity

_LOGGER = logging.getLogger(__name__)

VALID_MODE = vol.Any(
    vol.All(vol.Coerce(int), vol.Range(min=0, max=2)),
    vol.In([MODE_IN, MODE_OUT, MODE_INOUT]),
)
SET_MODE_SCHEMA = make_entity_service_schema({vol.Required(ATTR_MODE): VALID_MODE})
RESET_FILTER_TIMER_SCHEMA = make_entity_service_schema({})
SET_MANUAL_SPEED_SCHEMA = make_entity_service_schema(
    {
        vol.Required(ATTR_MANUAL_SPEED): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        )
    }
)

PRESET_TO_SPEED = {
    SPEED_OFF: Speed.OFF,
    SPEED_LOW: Speed.LOW,
    SPEED_MEDIUM: Speed.MEDIUM,
    SPEED_HIGH: Speed.HIGH,
    SPEED_MANUAL: Speed.MANUAL,
}
SPEED_TO_PRESET = {speed: preset for preset, speed in PRESET_TO_SPEED.items()}
SPEED_TO_PERCENTAGE = {Speed.LOW: 10, Speed.MEDIUM: 35, Speed.HIGH: 70}

MODE_TO_NAME = {Mode.ONEWAY: MODE_OUT, Mode.TWOWAY: MODE_INOUT, Mode.IN: MODE_IN}
NAME_TO_MODE = {MODE_OUT: Mode.ONEWAY, MODE_INOUT: Mode.TWOWAY, MODE_IN: Mode.IN}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DukaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Duka One based on a config entry."""
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("set_mode", SET_MODE_SCHEMA, "async_set_mode")
    platform.async_register_entity_service(
        "reset_filter_timer", RESET_FILTER_TIMER_SCHEMA, "async_reset_filter_timer"
    )
    platform.async_register_entity_service(
        "set_manual_speed", SET_MANUAL_SPEED_SCHEMA, "async_set_manual_speed"
    )
    async_add_entities([DukaOneFan(hass, entry)])


class DukaOneFan(DukaEntity, FanEntity):
    """A Duka One fan."""

    _attr_name = None
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = list(PRESET_TO_SPEED)
    _attr_percentage_step = 1

    def __init__(self, hass: HomeAssistant, entry: DukaConfigEntry) -> None:
        """Initialize the Duka One fan."""
        super().__init__(entry)
        self._data: DukaData = hass.data[DOMAIN]
        self._attr_unique_id = self._device_id

    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        return self.preset_mode != SPEED_OFF

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode."""
        return SPEED_TO_PRESET.get(self.device.speed, SPEED_OFF)

    @property
    def percentage(self) -> int:
        """Return the current speed percentage."""
        speed = self.device.speed
        if speed in SPEED_TO_PERCENTAGE:
            return SPEED_TO_PERCENTAGE[speed]
        if speed == Speed.MANUAL and self.device.manualspeed is not None:
            return int(round(self.device.manualspeed * 100 / 255))
        return 0

    @property
    def mode(self) -> str:
        """Return the current mode."""
        return MODE_TO_NAME.get(self.device.mode, MODE_INOUT)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.device.is_initialized():
            return {
                "mode": None,
                "filter_alarm": None,
                "filter_timer": None,
                "filter_timer_nice": None,
                "humidity": None,
            }
        nicetime = ""
        if self.device.filter_timer is not None:
            timeinmin: int = self.device.filter_timer
            days = timeinmin // (60 * 24)
            timeinmin -= days * 60 * 24
            hours = timeinmin // 60
            timeinmin -= hours * 60
            nicetime = f"{days}d {str(hours).zfill(2)}:{str(timeinmin).zfill(2)}"
        return {
            "mode": self.mode,
            "filter_alarm": self.device.filter_alarm,
            "filter_timer": self.device.filter_timer,
            "filter_timer_nice": nicetime,
            "humidity": self.device.humidity,
        }

    async def _send(self, command: Callable[..., None], *args: Any) -> None:
        try:
            await self.hass.async_add_executor_job(command, self.device, *args)
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                f"Could not send command to Duka One: {err}"
            ) from err

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        await self._send(
            self._data.client.set_manual_speed, int(percentage * 255 / 100)
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        await self._send(self._data.client.set_speed, PRESET_TO_SPEED[preset_mode])

    async def async_set_mode(self, mode: str | int) -> None:
        """Set the fan mode (in, out, inout or 0, 1, 2)."""
        if isinstance(mode, str) and mode in NAME_TO_MODE:
            new_mode = NAME_TO_MODE[mode]
        else:
            new_mode = Mode(int(mode))
        await self._send(self._data.client.set_mode, new_mode)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the entity."""
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._send(self._data.client.turn_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the entity."""
        await self._send(self._data.client.turn_off)

    async def async_reset_filter_timer(self) -> None:
        """Reset the filter timer to 90 days."""
        await self._send(self._data.client.reset_filter_alarm)

    async def async_set_manual_speed(self, manual_speed: int) -> None:
        """Set the manual fan speed."""
        await self._send(self._data.client.set_manual_speed, manual_speed)
