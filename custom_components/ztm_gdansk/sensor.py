"""Sensor ZTM Gdańsk — tablica odjazdów."""
import logging
from datetime import datetime, timezone, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
    UpdateFailed,
)

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"
DEPARTURES_URL = "https://ckan2.multimediagdansk.pl/departures?stopId={stop_id}"
SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    stop_id   = entry.data["stop_id"]
    stop_name = entry.data.get("stop_name", stop_id)
    max_dep   = int(entry.data.get("max_departures", 6))

    coordinator = ZTMCoordinator(hass, stop_id, max_dep)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([ZTMDepartureSensor(coordinator, entry, stop_name, max_dep)])


class ZTMCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, stop_id, max_dep):
        super().__init__(
            hass,
            _LOGGER,
            name=f"ZTM stop {stop_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.stop_id = stop_id
        self.max_dep = max_dep

    async def _async_update_data(self):
        url = DEPARTURES_URL.format(stop_id=self.stop_id)
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
                deps = data.get("departures", [])
                _LOGGER.debug("ZTM RAW: liczba=%s", len(deps))
                return data
        except Exception as e:
            raise UpdateFailed(f"Błąd pobierania odjazdów: {e}") from e


class ZTMDepartureSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, stop_name, max_dep):
        super().__init__(coordinator)
        self._entry     = entry
        self._stop_name = stop_name
        self._max_dep   = max_dep
        self._attr_name      = f"ZTM {stop_name}"
        self._attr_unique_id = f"ztm_gdansk_{entry.data['stop_id']}"
        self._attr_icon      = "mdi:bus-clock"

    @property
    def native_value(self) -> str:
        deps = self._get_departures()
        if not deps:
            return "Brak odjazdów"
        d = deps[0]
        return f"{d['linia']} → {d['kierunek']} za {d['za_minuty']} min"

    @property
    def extra_state_attributes(self) -> dict:
        deps = self._get_departures()
        raw  = self.coordinator.data or {}
        return {
            "przystanek":            self._stop_name,
            "stop_id":               self._entry.data["stop_id"],
            "ostatnia_aktualizacja": raw.get("lastUpdate", ""),
            "liczba_odjazdow":       len(deps),
            "odjazdy":               deps,
            "tablica":               self._build_text_table(deps),
        }

    def _get_departures(self) -> list:
        raw        = self.coordinator.data or {}
        departures = raw.get("departures", [])
        now        = datetime.now(timezone.utc)
        result     = []

        for dep in departures:
            try:
                estimated = dep.get("estimatedTime") or dep.get("theoreticalTime")
                scheduled = dep.get("theoreticalTime") or estimated
                line      = str(dep.get("routeShortName", dep.get("routeId", "?")))
                headsign  = dep.get("headsign", "")

                if not estimated:
                    continue

                # API zwraca ISO 8601 np. "2026-02-27T00:00:00Z"
                est_dt = datetime.fromisoformat(estimated.replace("Z", "+00:00"))
                sch_dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))

                in_sec = (est_dt - now).total_seconds()
                if in_sec < -60:
                    continue

                in_min = max(0, int(in_sec // 60))

                # Opóźnienie — najpierw z pola delayInSeconds, fallback z różnicy czasów
                delay_sec = dep.get("delayInSeconds") or int((est_dt - sch_dt).total_seconds())

                if delay_sec is not None and delay_sec > 60:
                    delay_str, status = f"+{delay_sec // 60} min", "opóźniony"
                elif delay_sec is not None and delay_sec < -60:
                    delay_str, status = f"{delay_sec // 60} min", "wcześniej"
                else:
                    delay_str, status = "na czas", "punktualny"

                result.append({
                    "linia":       line,
                    "kierunek":    headsign,
                    "odjazd":      sch_dt.strftime("%H:%M"),
                    "rzeczywisty": est_dt.strftime("%H:%M"),
                    "opoznienie":  delay_str,
                    "status":      status,
                    "za_minuty":   in_min,
                })

            except Exception as e:
                _LOGGER.debug("Błąd parsowania odjazdu: %s", e)
                continue

            if len(result) >= self._max_dep:
                break

        return result

    def _build_text_table(self, deps: list) -> str:
        if not deps:
            return "_Brak nadchodzących odjazdów_"
        lines = ["| Linia | Kierunek | Za (min) | Status |",
                 "|-------|----------|----------|--------|"]
        for d in deps:
            lines.append(
                f"| **{d['linia']}** | {d['kierunek']} | {d['za_minuty']} | {d['status']} |"
            )
        return "\n".join(lines)
