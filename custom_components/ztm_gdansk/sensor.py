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
WARSAW_TZ = timezone(timedelta(hours=1))  # CET; HA obsłuży DST przez lokalny czas


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    stop_id   = entry.data["stop_id"]
    stop_name = entry.data.get("stop_name", stop_id)
    max_dep   = entry.data.get("max_departures", 6)

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
                return await resp.json(content_type=None)
        except Exception as e:
            raise UpdateFailed(f"Błąd pobierania odjazdów: {e}") from e


class ZTMDepartureSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, stop_name, max_dep):
        super().__init__(coordinator)
        self._entry      = entry
        self._stop_name  = stop_name
        self._max_dep    = max_dep
        self._attr_name  = f"ZTM {stop_name}"
        self._attr_unique_id = f"ztm_gdansk_{entry.data['stop_id']}"
        self._attr_icon  = "mdi:bus-clock"

    @property
    def native_value(self):
        """Pierwsza odjeżdżająca linia — główna wartość sensora."""
        deps = self._get_departures()
        if not deps:
            return "Brak odjazdów"
        first = deps[0]
        return f"{first['line']} → {first['headsign']} za {first['in_min']} min"

    @property
    def extra_state_attributes(self):
        """Pełna tablica odjazdów + metadane."""
        deps = self._get_departures()
        now  = datetime.now(timezone.utc)

        # Buduj tablicę jak na stronie ZTM
        table_rows = []
        for d in deps:
            table_rows.append({
                "linia":       d["line"],
                "kierunek":    d["headsign"],
                "odjazd":      d["scheduled"],
                "rzeczywisty": d["estimated"],
                "opoznienie":  d["delay_str"],
                "status":      d["status"],
                "za_minuty":   d["in_min"],
            })

        raw = self.coordinator.data or {}
        last_update = raw.get("lastUpdate", "")

        return {
            "przystanek":      self._stop_name,
            "stop_id":         self._entry.data["stop_id"],
            "ostatnia_aktualizacja": last_update,
            "liczba_odjazdow": len(deps),
            "odjazdy":         table_rows,
            # Skrócona tablica tekstowa — czytelna w Lovelace
            "tablica": self._build_text_table(deps),
        }

    def _get_departures(self) -> list:
        raw = self.coordinator.data or {}
        departures = raw.get("departures", [])
        now = datetime.now(timezone.utc)
        result = []

        for dep in departures[: self._max_dep * 2]:  # weź z zapasem, odfiltruj przeszłe
            try:
                estimated_str  = dep.get("estimatedTime") or dep.get("theoreticalTime", "")
                scheduled_str  = dep.get("theoreticalTime", "")
                delay_sec      = dep.get("delayInSeconds", 0)
                line           = dep.get("routeShortName", "?")
                headsign       = dep.get("headsign", "?")
                status         = dep.get("status", "SCHEDULED")

                if not estimated_str:
                    continue

                est_dt  = datetime.fromisoformat(estimated_str.replace("Z", "+00:00"))
                sched_dt = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00")) if scheduled_str else est_dt

                # Pomijaj odjazdy które już minęły
                if est_dt < now - timedelta(seconds=30):
                    continue

                in_min = max(0, int((est_dt - now).total_seconds() / 60))

                # Formatuj czas lokalnie (Polska)
                local_est   = est_dt.astimezone(timezone(timedelta(hours=1)))
                local_sched = sched_dt.astimezone(timezone(timedelta(hours=1)))

                delay_min = delay_sec // 60
                if delay_sec > 60:
                    delay_str = f"+{delay_min} min"
                elif delay_sec < -60:
                    delay_str = f"{delay_min} min"
                else:
                    delay_str = "na czas"

                result.append({
                    "line":      line,
                    "headsign":  headsign,
                    "scheduled": local_sched.strftime("%H:%M"),
                    "estimated": local_est.strftime("%H:%M"),
                    "delay_str": delay_str,
                    "delay_sec": delay_sec,
                    "status":    status,
                    "in_min":    in_min,
                    "est_dt":    est_dt,
                })

            except Exception as e:
                _LOGGER.debug("Błąd parsowania odjazdu: %s", e)
                continue

        # Sortuj po czasie rzeczywistym
        result.sort(key=lambda x: x["est_dt"])
        return result[: self._max_dep]

    def _build_text_table(self, deps: list) -> str:
        """Buduje czytelną tablicę tekstową — jak wyświetlacz na przystanku."""
        if not deps:
            return "Brak odjazdów"

        lines = [f"{'LINIA':<6} {'KIERUNEK':<25} {'GODZ':>5} {'ZA':>5}  STATUS"]
        lines.append("─" * 55)

        for d in deps:
            headsign = d["headsign"][:24]
            status   = d["delay_str"]
            lines.append(
                f"{d['line']:<6} {headsign:<25} {d['estimated']:>5} {d['in_min']:>3}min  {status}"
            )

        return "\n".join(lines)
