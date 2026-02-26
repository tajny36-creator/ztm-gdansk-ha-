"""Config Flow — GUI konfiguracji ZTM Gdańsk w Home Assistant."""
import logging
import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"

STOPS_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json"
)

LOCATIONS = {
    "Wrzeszcz":     ["Wrzeszcz", "Politechnika"],
    "Śródmieście":  ["Śródmieście", "Główny", "Targ Węglowy"],
    "Oliwa":        ["Oliwa", "Żabianka", "Przymorze"],
    "Morena":       ["Morena", "Chętnika", "Łostowice"],
    "Nowy Port":    ["Nowy Port", "Brzeźno", "Stogi"],
    "Wszystkie":    [],
}


def fetch_stops(keywords: list) -> dict:
    """Pobiera i filtruje przystanki z API ZTM Gdańsk."""
    try:
        resp = requests.get(STOPS_URL, timeout=15)
        resp.raise_for_status()
        raw = resp.json()

        # ✅ API zwraca {"2026-02-26": {"stops": [...], "lastUpdate": "..."}}
        # Pobieramy wartość pierwszego (jedynego) klucza — daty
        if isinstance(raw, dict):
            date_key = next(iter(raw))          # np. "2026-02-26"
            inner = raw[date_key]               # {"lastUpdate": ..., "stops": [...]}
            stops_list = inner.get("stops", [])
        elif isinstance(raw, list):
            stops_list = raw
        else:
            stops_list = []

        _LOGGER.debug("Pobrano %d przystanków z API", len(stops_list))

        result = {}
        for stop in stops_list:
            name    = stop.get("stopName", "")
            stop_id = str(stop.get("stopId", ""))

            if not name or not stop_id:
                continue

            if not keywords:
                result[stop_id] = name
            else:
                if any(kw.lower() in name.lower() for kw in keywords):
                    result[stop_id] = name

        sorted_result = dict(sorted(result.items(), key=lambda x: x[1]))
        _LOGGER.debug("Po filtrowaniu: %d przystanków", len(sorted_result))
        return sorted_result

    except requests.exceptions.Timeout:
        _LOGGER.error("Timeout podczas pobierania przystanków ZTM")
        return {}
    except requests.exceptions.ConnectionError:
        _LOGGER.error("Brak połączenia z API ZTM Gdańsk")
        return {}
    except Exception as e:
        _LOGGER.error("Nieoczekiwany błąd pobierania przystanków: %s", e)
        return {}



class ZTMGdanskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Obsługuje konfigurację przez GUI Home Assistant."""

    VERSION = 1

    def __init__(self):
        self._location: str = "Wszystkie"
        self._stops: dict = {}

    async def async_step_user(self, user_input=None):
        """Krok 1 — wybór lokalizacji / dzielnicy."""
        if user_input is not None:
            self._location = user_input["location"]

            # Pobierz przystanki TUTAJ — po wyborze lokalizacji
            keywords = LOCATIONS.get(self._location, [])
            self._stops = await self.hass.async_add_executor_job(
                fetch_stops, keywords
            )

            if not self._stops:
                # Pokaż błąd nadal na kroku 1, nie przeskakuj dalej
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({
                        vol.Required("location", default=self._location): vol.In(
                            list(LOCATIONS.keys())
                        )
                    }),
                    errors={"base": "cannot_connect"},
                )

            # Przystanki pobrane — idź do kroku 2
            return await self.async_step_stop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("location", default="Wrzeszcz"): vol.In(
                    list(LOCATIONS.keys())
                )
            }),
        )

    async def async_step_stop(self, user_input=None):
        """Krok 2 — wybór konkretnego przystanku."""
        errors = {}

        if user_input is not None:
            stop_id = user_input["stop_id"]
            stop_name = self._stops.get(stop_id, stop_id)
            max_dep = user_input.get("max_departures", 6)

            await self.async_set_unique_id(f"ztm_gdansk_{stop_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"ZTM — {stop_name}",
                data={
                    "stop_id":        stop_id,
                    "stop_name":      stop_name,
                    "location":       self._location,
                    "max_departures": max_dep,
                },
            )

        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema({
                vol.Required("stop_id"): vol.In(self._stops),
                vol.Optional("max_departures", default=6): vol.All(
                    int, vol.Range(min=1, max=15)
                ),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZTMOptionsFlow(config_entry)


class ZTMOptionsFlow(config_entries.OptionsFlow):
    """Pozwala edytować ustawienia po instalacji."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    "max_departures",
                    default=self.config_entry.data.get("max_departures", 6)
                ): vol.All(int, vol.Range(min=1, max=15)),
            }),
        )

