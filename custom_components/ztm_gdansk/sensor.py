"""Sensor ZTM Gdańsk — estymowane czasy odjazdów."""
import requests
import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"
DEPARTURES_URL = "https://ckan2.multimediagdansk.pl/departures"
SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    stop_id = entry.data["stop_id"]
    stop_name = entry.data["stop_name"]
    max_dep = entry.data.get("max_departures", 6)

    coordinator = ZTMCoordinator(hass, stop_id)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([ZTMSensor(coordinator, entry, stop_name, max_dep)])


class ZTMCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, stop_id):
        super().__init__(
            hass, _LOGGER,
            name=f"ZTM {stop_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.stop_id = stop_id

    async def _async_update_data(self):
        return await self.hass.async_add_executor_job(self._fetch)

    def _fetch(self):
        try:
            resp = requests.get(
                DEPARTURES_URL,
                params={"stopId": self.stop_id},
                timeout=10
            )
            resp.raise_for_status()
            deps = resp.json().get("departures", [])
            now = datetime.now()
            result = []

            for dep in deps[:15]:
                estimated = dep.get("estimatedTime", "")
                delay = int(dep.get("delay", 0))
                try:
                    t = datetime.strptime(estimated, "%H:%M").replace(
                        year=now.year, month=now.month, day=now.day
                    )
                    minutes = max(0, int((t - now).total_seconds() / 60))
                except Exception:
                    minutes = 0

                result.append({
                    "line":      dep.get("routeId", "?"),
                    "direction": dep.get("headsign", "—"),
                    "time":      estimated,
                    "scheduled": dep.get("scheduledTime", ""),
                    "minutes":   minutes,
                    "delay":     delay,
                    "status":    "Na czas" if delay == 0
                                 else ("Opóźniony" if delay > 0
                                       else "Przed czasem"),
                })
            return result
        except Exception as e:
            _LOGGER.error("Błąd API ZTM Gdańsk: %s", e)
            return []


class ZTMSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, stop_name, max_dep):
        super().__init__(coordinator)
        self._stop_name = stop_name
        self._max_dep = max_dep
        self._attr_name = f"ZTM — {stop_name}"
        self._attr_unique_id = f"ztm_gdansk_{entry.data['stop_id']}"
        self._attr_icon = "mdi:bus-clock"

    @property
    def native_value(self):
        deps = self.coordinator.data
        if deps:
            d = deps[0]
            return f"Linia {d['line']} za {d['minutes']} min"
        return "Brak odjazdów"

    @property
    def extra_state_attributes(self):
        deps = self.coordinator.data or []
        return {
            "stop_name":   self._stop_name,
            "last_update": datetime.now().strftime("%H:%M:%S"),
            "departures":  deps[:self._max_dep],
        }
