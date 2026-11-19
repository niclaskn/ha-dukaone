"""Tests for the humidity sensor."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE

SENSOR = "sensor.bathroom_humidity"


async def test_humidity_attributes(hass, setup_entry):
    state = hass.states.get(SENSOR)
    assert state.state == "45"
    assert state.attributes["unit_of_measurement"] == PERCENTAGE
    assert state.attributes["device_class"] == SensorDeviceClass.HUMIDITY
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT


async def test_humidity_update_on_push(hass, device, setup_entry, onchange):
    device.humidity = 60
    onchange()
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "60"
