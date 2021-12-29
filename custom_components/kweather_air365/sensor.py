"""
Get air quality from Kweather air stations
#https://github.com/GrecHouse/anniversary
"""

from datetime import timedelta, date, datetime
import logging

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.components.sensor import ENTITY_ID_FORMAT, PLATFORM_SCHEMA
from homeassistant.const import CONF_SENSORS, CONF_NAME, CONF_TYPE, CONF_SCAN_INTERVAL, CONF_API_KEY
from homeassistant.helpers.entity import Entity, async_generate_entity_id
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.util.json import load_json
from homeassistant.helpers.event import async_track_point_in_utc_time

import requests
import xml.etree.ElementTree as ET


_LOGGER = logging.getLogger(__name__)

DEFAULT_SENSOR_NAME = 'KWeather Air 365'

CONF_NAME = 'sensor_name'
CONF_SCAN_INTERVAL = 'interval'
CONF_API_KEY = 'station_no'

KWEATHER_API_URL = 'https://datacenter.kweather.co.kr/api/app/iotData'


SENSOR_SCHEMA = vol.Schema({
    vol.Required(CONF_API_KEY, default=''): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_SENSOR_NAME): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=360): cv.positive_int,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SENSORS): cv.schema_with_slug_keys(SENSOR_SCHEMA),
})


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Anniversary sensor."""
    if hass.config.time_zone is None:
        _LOGGER.error("Timezone is not set in Home Assistant configuration")
        return False

    sensors = []
    sensor = KWeatherAir365Sensor(hass, config.get(CONF_NAME), config.get(CONF_API_KEY), config.get(CONF_SCAN_INTERVAL))

    async_track_point_in_utc_time(
            hass, sensor.point_in_time_listener, sensor.get_next_interval())
    sensors.append(sensor)

    async_add_entities(sensors, True)

class KWeatherAir365Sensor(Entity):
    def __init__(self, hass, name, station_no, interval):
        self.hass = hass
        self._name = name
        self._station_no = station_no
        self._interval = interval
        self._update_internal_state(dt_util.utcnow())

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def icon(self):
        return "ph:graph-thin"

    @property
    def device_state_attributes(self):
        return self._attributes

    def _update_internal_state(self):
        self._attribute = {
            'type': self._type,
        }

        params = { 'station_no' : self._station_no }
        x = requests.post(KWEATHER_API_URL, data = params)
        if (x.status_code == 200):
            try:
                root = ET.fromstring(x.text)
                for child in root:
                    self._attribute[child.tag] = child.text
            except:
                pass

    def get_next_interval(self, now=None):
        """Compute next time an update should occur."""
        interval = self._interval

        if now is None:
            now = dt_util.utcnow()
        elif interval == 86460 or interval is None:
            now = dt_util.start_of_local_day(dt_util.as_local(now))
        return now + timedelta(seconds=interval)

    @callback
    def point_in_time_listener(self, time_date):
        """Get the latest data and update state."""
        self._update_internal_state(time_date)
        self.async_schedule_update_ha_state()
        async_track_point_in_utc_time(
            self.hass, self.point_in_time_listener, self.get_next_interval())


