"""
Get air quality from Kweather air stations
#https://github.com/GrecHouse/anniversary
"""

from datetime import timedelta, date, datetime
import logging

import aiohttp
import time
import math

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.components.sensor import ENTITY_ID_FORMAT, PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_SENSORS, CONF_NAME, CONF_TYPE,
    DEVICE_CLASS_TEMPERATURE, DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_PM10, DEVICE_CLASS_PM25, DEVICE_CLASS_TIMESTAMP,
)
from homeassistant.helpers.entity import Entity, async_generate_entity_id
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.util.json import load_json
from homeassistant.helpers.event import async_track_point_in_utc_time

import xml.etree.ElementTree as ET

_LOGGER = logging.getLogger(__name__)

CONF_SENSOR_LOCATION = 'sensor_location'
CONF_SENSOR_TYPES ='sensor_types'
CONF_INTERVAL = 'interval'
CONF_STATION_NO = 'station_no'
CONF_UNIQUE_ID = 'unique_id'

KWEATHER_API_URL = 'https://datacenter.kweather.co.kr/api/app/iotData'

SENSOR_TYPES = {
    'pm25': [DEVICE_CLASS_PM25, 'PM2.5', 'μg/m³'],
    'pm10': [DEVICE_CLASS_PM10, 'PM10', 'μg/m³'],
    'temp': [DEVICE_CLASS_TEMPERATURE, 'Temperature', '℃'],
    'humi': [DEVICE_CLASS_HUMIDITY, 'Humidity', '%'],
    'time' : [DEVICE_CLASS_TIMESTAMP, 'Last Updated Time', ''],
}

DEFAULT_SENSOR_TYPES = list(SENSOR_TYPES.keys())

SENSOR_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default=''): cv.string,
    vol.Required(CONF_STATION_NO, default=''): cv.string,
    vol.Required(CONF_INTERVAL, default=3600): cv.positive_int,
    vol.Optional(CONF_SENSOR_TYPES, default=DEFAULT_SENSOR_TYPES): cv.ensure_list,
    vol.Optional(CONF_SENSOR_LOCATION, default=''): cv.string,
    vol.Optional(CONF_UNIQUE_ID): cv.string
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SENSORS): cv.schema_with_slug_keys(SENSOR_SCHEMA),
})


async def get_kweather_air365_result_impl_http_aio(station_no):
    params = { 'station_no' : 'OT2CL1900053' }
    async with aiohttp.ClientSession() as session:
        async with session.post(KWEATHER_API_URL, data=params) as resp:
            xml = await resp.text()
            result = {}
            try:
                root = ET.fromstring(xml)
                for child in root:
                    result[child.tag] = child.text
            except:
                pass
            result['time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            return result

aq_history = {}
async def get_weather_air365_sensor_value(station_no, sensor):
    newKeyStr = time.strftime('%y%m%d%H%M', time.localtime())
    newKey = math.floor(int(newKeyStr) / 10)
    keys_to_remove = []

    if newKey not in aq_history.keys():
        for eachKey in aq_history.keys():
            if eachKey != newKey:
                keys_to_remove.append(eachKey)

        for eachKey in keys_to_remove:
            aq_history.pop(eachKey)

        aq_history[newKey] = await get_kweather_air365_result_impl_http_aio(station_no)

    return aq_history[newKey][sensor]


sensor_icons = {
    'temp' : 'mdi:thermometer',
    'humi' : 'mdi:water-percent',
    'pm25' : 'mdi:alien-outline',
    'pm10' : 'mdi:alien-outline',
    'time' : 'mdi:clock-check-outline',
}

class DataStore:
    def __init__(self, hass, sensors, interval):
        self._hass = hass
        self._sensors = sensors
        self._interval = interval

    def get_next_interval(self):
        now = dt_util.utcnow()
        interval = now + timedelta(seconds=self._interval);
        return interval

    @callback
    async def point_in_time_listener(self, now):
        """Get the latest data and update state."""
        for sensor in self._sensors:
            await sensor._update_internal_state()
            sensor.async_schedule_update_ha_state(True)
        async_track_point_in_utc_time(
            self._hass, self.point_in_time_listener, self.get_next_interval())

data_stores = []
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Anniversary sensor."""
    if hass.config.time_zone is None:
        _LOGGER.error("Timezone is not set in Home Assistant configuration")
        return False

    for device, device_config in config[CONF_SENSORS].items():
        location = device_config.get(CONF_SENSOR_LOCATION)
        station_no = device_config.get(CONF_STATION_NO)
        interval = device_config.get(CONF_INTERVAL)
        sensor_types = device_config.get(CONF_SENSOR_TYPES)

        result = await get_kweather_air365_result_impl_http_aio(station_no)

        # https://stackoverflow.com/questions/29867405/python-asyncio-return-vs-set-result

        _LOGGER.info("current values : {}".format(result))

        sensors = []
        for sensor in SENSOR_TYPES:
            if sensor in sensor_types:
                initial = result[sensor]
                sensor = KWeatherAir365Sensor(hass, location, station_no, sensor, initial, interval)
                sensors.append(sensor)

        data_store = DataStore(hass, sensors, interval)
        data_stores.append(data_store)

        async_track_point_in_utc_time(
            hass, data_store.point_in_time_listener, data_store.get_next_interval())

    async_add_entities(sensors, True)


class KWeatherAir365Sensor(Entity):
    def __init__(self, hass, name, station_no, sensor_type, initial_value, interval):
        self.hass = hass
        self.entity_id = async_generate_entity_id(ENTITY_ID_FORMAT, "{}_{}".format(name, sensor_type), hass=hass)
        self._name = name
        self._station_no = station_no
        self._sensor_type = sensor_type
        self._interval = interval
        self._extra_state_attributes = { }
        self._attr_state = initial_value
        self._attr_name = "{} {}".format(name, SENSOR_TYPES[sensor_type][1])
        self._attr_unit_of_measurement = SENSOR_TYPES[sensor_type][2]

    @property
    def name(self):
        if self._sensor_type in SENSOR_TYPES:
            return "{} {}".format(self._name, SENSOR_TYPES[self._sensor_type][2])
        else:
            return "{} {}".format(self._name, self._sensor_type)

    @property
    def state(self):
        return self._attr_state

    @property
    def icon(self):
        if self._sensor_type in sensor_icons:
            return sensor_icons[self._sensor_type]
        return ""

    @property
    def extra_state_attributes(self):
        return self._extra_state_attributes

    #@property
    #def should_poll(self):
    #    _LOGGER.info("Returning false for should_poll")
    #    return False

    #How to update state
    #https://developers.home-assistant.io/docs/core/entity/
    async def _update_internal_state(self):
        try:
            self._attr_state = await get_weather_air365_sensor_value(self._station_no, self._sensor_type)
        except:
            _LOGGER.info("Exception occured!!")
        return self._attr_state

'''
def point_in_time_listener(hass, sensors, interval):
    """Get the latest data and update state."""
    for sensor in sensors:
        sensor._update_internal_state()
        sensor.async_schedule_update_ha_state()

    async_track_point_in_utc_time(
        hass, point_in_time_listener(hass, sensors, interval), get_next_interval(interval))
'''
