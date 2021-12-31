"""
Get air quality from Kweather air stations
#https://github.com/GrecHouse/anniversary
"""

from datetime import timedelta, date, datetime
import logging

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.components.sensor import ENTITY_ID_FORMAT, PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_SENSORS, CONF_NAME, CONF_TYPE,
    DEVICE_CLASS_TEMPERATURE, DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_PM10, DEVICE_CLASS_PM25,
)
from homeassistant.helpers.entity import Entity, async_generate_entity_id
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.util.json import load_json
from homeassistant.helpers.event import async_track_point_in_utc_time

import requests
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
    'temperature': [DEVICE_CLASS_TEMPERATURE, 'Temperature', '℃'],
    'humidity': [DEVICE_CLASS_HUMIDITY, 'Humidity', '%'],
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

async def get_kweather_air365_result(station_no):
    params = { 'station_no' : station_no }
    #self._attributes = {"pm25": 10}
    x = requests.post(KWEATHER_API_URL, data = params)
    result = {}
    if (x.status_code == 200):
        try:
            root = ET.fromstring(x.text)
            for child in root:
                result[child.tag] = child.text
        except:
            pass
    return result


aq_history = {}
async def get_weather_air365_sensor_value(hass, station_no, sensor):
    k = time.strftime('%y%m%d%H', time.localtime())
    if k not in aq_history.keys():
        aq_history.clear()
        aq_history[k] = await hass.async_add_executor_job(get_kweather_air365_result(station_no))
    return aq_history[k][sensor]

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Anniversary sensor."""
    if hass.config.time_zone is None:
        _LOGGER.error("Timezone is not set in Home Assistant configuration")
        return False

    sensors = []

    for device, device_config in config[CONF_SENSORS].items():
        location = device_config.get(CONF_SENSOR_LOCATION)
        station_no = device_config.get(CONF_STATION_NO)
        interval = device_config.get(CONF_INTERVAL)
        sensor_types = device_config.get(CONF_SENSOR_TYPES)

        await hass.async_add_executor_job(get_kweather_air365_result(station_no))

        for sensor in SENSOR_TYPES:
            if sensor in sensor_types:
                sensor = KWeatherAir365Sensor(hass, location, station_no, sensor, interval)
                sensors.append(sensor)

        async_track_point_in_utc_time(
            hass, point_in_time_listener, get_next_interval(interval))

    async_add_entities(sensors, True)


class KWeatherAir365Sensor(Entity):
    def __init__(self, hass, name, station_no, sensor_type, interval):
        self.hass = hass
        self.entity_id = async_generate_entity_id(ENTITY_ID_FORMAT, "{}_{}".format(name, sensor_type), hass=hass)
        self._name = name
        self._station_no = station_no
        self._sensor_type = sensor_type
        self._interval = interval
        self._extra_state_attributes = { }
        self._attr_state = get_weather_air365_sensor_value(hass, station_no, sensor_type)
        self._attr_name = "{} {}".format(name, SENSOR_TYPES[sensor_type][1])
        self._attr_unit_of_measurement = SENSOR_TYPES[sensor_type][2]

        _LOGGER.info('interval passed to ctor : {0}'.format(self._interval))

        #self._update_internal_state()

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._attr_state

    @property
    def icon(self):
        return "ph:graph-thin"

    @property
    def extra_state_attributes(self):
        return self._extra_state_attributes

    async def _update_internal_state(self):
        self._state = get_weather_air365_sensor_value(self._hass, self._station_no, self._sensor_type)

        params = { 'station_no' : self._station_no }
        #self._attributes = {"pm25": 10}
        '''
        x = requests.post(KWEATHER_API_URL, data = params)
        if (x.status_code == 200):
            try:
                root = ET.fromstring(x.text)
                for child in root:
                    self._attribute[child.tag] = child.text
            except:
                pass
        '''
        #self._attributes = await hass.async_add_executor_job(get_kweather_air365_result(self._station_no))

    '''
    @callback
    def point_in_time_listener(self, time_date):
        """Get the latest data and update state."""
        self._update_internal_state()
        self.async_schedule_update_ha_state()
        async_track_point_in_utc_time(
            self.hass, self.point_in_time_listener, self.get_next_interval())
    '''

def get_next_interval(interval):
    now = dt_util.utcnow()
    return now + timedelta(seconds=interval)

def point_in_time_listener(hass, sensors, interval):
    """Get the latest data and update state."""
    for sensor in sensors:
        sensor._update_internal_state()
        sensor.async_schedule_update_ha_state()

    async_track_point_in_utc_time(
        hass, point_in_time_listener, get_next_interval(interval))
