"""Tests for the fan entity."""

import pytest
import voluptuous as vol
from dukaonesdk.device import Mode, Speed
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.dukaone.const import DOMAIN

FAN = "fan.bathroom"


async def _call(hass, domain, service, **data):
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: FAN, **data}, blocking=True
    )


@pytest.mark.parametrize(
    ("preset", "speed"),
    [
        ("off", Speed.OFF),
        ("low", Speed.LOW),
        ("medium", Speed.MEDIUM),
        ("high", Speed.HIGH),
        ("manual", Speed.MANUAL),
    ],
)
async def test_presets(hass, client, device, setup_entry, preset, speed):
    await _call(hass, FAN_DOMAIN, "set_preset_mode", preset_mode=preset)
    client.set_speed.assert_called_once_with(device, speed)


async def test_set_percentage(hass, client, device, setup_entry):
    await _call(hass, FAN_DOMAIN, "set_percentage", percentage=50)
    client.set_manual_speed.assert_called_once_with(device, 127)


async def test_turn_on_off(hass, client, device, setup_entry):
    await _call(hass, FAN_DOMAIN, "turn_on")
    client.turn_on.assert_called_once_with(device)
    await _call(hass, FAN_DOMAIN, "turn_on", preset_mode="high")
    client.set_speed.assert_called_once_with(device, Speed.HIGH)
    await _call(hass, FAN_DOMAIN, "turn_on", percentage=100)
    client.set_manual_speed.assert_called_once_with(device, 255)
    await _call(hass, FAN_DOMAIN, "turn_off")
    client.turn_off.assert_called_once_with(device)


async def test_reset_filter_timer(hass, client, device, setup_entry):
    await _call(hass, DOMAIN, "reset_filter_timer")
    client.reset_filter_alarm.assert_called_once_with(device)


@pytest.mark.parametrize(
    ("speed", "manual", "preset", "percentage", "state"),
    [
        (Speed.OFF, None, "off", 0, STATE_OFF),
        (Speed.LOW, None, "low", 10, STATE_ON),
        (Speed.MEDIUM, None, "medium", 35, STATE_ON),
        (Speed.HIGH, None, "high", 70, STATE_ON),
        (Speed.MANUAL, 255, "manual", 100, STATE_ON),
        (Speed.MANUAL, 128, "manual", 50, STATE_ON),
        (Speed.MANUAL, None, "manual", 0, STATE_ON),
    ],
)
async def test_state_follows_device_on_push(
    hass, device, setup_entry, onchange, speed, manual, preset, percentage, state
):
    device.speed, device.manualspeed = speed, manual
    onchange()
    await hass.async_block_till_done()
    fan = hass.states.get(FAN)
    assert fan.state == state
    assert fan.attributes["preset_mode"] == preset
    assert fan.attributes["percentage"] == percentage


@pytest.mark.parametrize(
    ("mode", "name"),
    [(Mode.ONEWAY, "out"), (Mode.TWOWAY, "inout"), (Mode.IN, "in"), (None, "inout")],
)
async def test_extra_attributes(hass, device, setup_entry, onchange, mode, name):
    device.mode = mode
    device.filter_timer = 2 * 24 * 60 + 5 * 60 + 7
    onchange()
    await hass.async_block_till_done()
    attrs = hass.states.get(FAN).attributes
    assert attrs["mode"] == name
    assert attrs["filter_alarm"] is False
    assert attrs["filter_timer"] == 3187
    assert attrs["filter_timer_nice"] == "2d 05:07"
    assert attrs["humidity"] == 45


async def test_extra_attributes_not_initialized(hass, device, setup_entry, onchange):
    device.is_initialized = lambda: False
    device.filter_timer = None
    onchange()
    await hass.async_block_till_done()
    attrs = hass.states.get(FAN).attributes
    assert attrs["mode"] is None
    assert attrs["humidity"] is None


async def test_extra_attributes_no_filter_timer(hass, device, setup_entry, onchange):
    device.filter_timer = None
    onchange()
    await hass.async_block_till_done()
    assert hass.states.get(FAN).attributes["filter_timer_nice"] == ""


@pytest.mark.parametrize("value", [0, 100, 255, "42"])
async def test_set_manual_speed_accepts(hass, client, device, setup_entry, value):
    await _call(hass, DOMAIN, "set_manual_speed", manual_speed=value)
    client.set_manual_speed.assert_called_once_with(device, int(value))


@pytest.mark.parametrize("value", [256, -1, "abc"])
async def test_set_manual_speed_rejects(hass, client, setup_entry, value):
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(hass, DOMAIN, "set_manual_speed", manual_speed=value)
    client.set_manual_speed.assert_not_called()


@pytest.mark.parametrize(
    ("value", "mode"),
    [
        ("in", Mode.IN),
        ("out", Mode.ONEWAY),
        ("inout", Mode.TWOWAY),
        (0, Mode.ONEWAY),
        (1, Mode.TWOWAY),
        (2, Mode.IN),
    ],
)
async def test_set_mode_accepts(hass, client, device, setup_entry, value, mode):
    await _call(hass, DOMAIN, "set_mode", mode=value)
    client.set_mode.assert_called_once_with(device, mode)


@pytest.mark.parametrize("value", ["sideways", 3, -1])
async def test_set_mode_rejects(hass, client, setup_entry, value):
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(hass, DOMAIN, "set_mode", mode=value)
    client.set_mode.assert_not_called()


@pytest.mark.parametrize(
    ("method", "domain", "service", "data"),
    [
        ("turn_on", FAN_DOMAIN, "turn_on", {}),
        ("turn_off", FAN_DOMAIN, "turn_off", {}),
        ("set_speed", FAN_DOMAIN, "set_preset_mode", {"preset_mode": "low"}),
        ("set_mode", DOMAIN, "set_mode", {"mode": "in"}),
        ("reset_filter_alarm", DOMAIN, "reset_filter_timer", {}),
    ],
)
@pytest.mark.parametrize("error", [OSError("net down"), TimeoutError("slow")])
async def test_sdk_errors_become_ha_errors(
    hass, client, setup_entry, method, domain, service, data, error
):
    getattr(client, method).side_effect = error
    with pytest.raises(HomeAssistantError):
        await _call(hass, domain, service, **data)
