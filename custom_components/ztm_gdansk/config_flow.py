"""Config Flow — GUI konfiguracji ZTM Gdańsk w Home Assistant."""
import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

DOMAIN = "ztm_gdansk"

STOPS_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json"
)

# Predefiniowane lokalizacje / dzielnice Gdańska
LOCATIONS = {
    "Wrzeszcz": ["Wrzeszcz", "Politechnika", "Brama Wyżynna"],
    "Śródmieście": ["Śródmieście", "Główny", "Targ Węglowy"],
    "Oliwa": ["Oliwa", "Żabianka", "Przymorze"],
    "Morena": ["Morena", "Chętnika", "Łostowice"],
    "Nowy Port": ["Nowy Port", "Brzeźno", "Stogi"],
    "Wszystkie": []  # brak filtra — pokaż wszystkie
}

def fetch_stops(location_keywords: list) -> dict:
    """Pobiera przystanki i filtruje po słowach kluczowych lokalizacji."""
    try:
        resp = requests.get(STOPS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        stops_raw = data.get("stops", [])

        result = {}
        for stop in stops_raw:
            name = stop.get("stopName", "")
            stop_id = str(stop.get("stopId", ""))

            if not location_keywords:
                result[stop_id] = name
            else:
                if any(kw.lower() in name.lower() for kw in location_keywords):
                    result[stop_id] = name

        # Posortuj alfabetycznie po nazwie
        return dict(sorted(result.items(), key=lambda x: x[1]))

    except Exception:
        return {}


class ZTMGdanskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Obsługuje konfigurację przez GUI Home Assistant."""

    VERSION = 1
    _location: str = "Wszystkie"
    _stops: dict = {}

    async def async_step_user(self, user_input=None):
        """Krok 1 — wybór lokalizacji / dzielnicy."""
        errors = {}

        if user_input is not None:
            self._location = user_input["location"]
            return await self.async_step_stop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("location", default="Wrzeszcz"): vol.In(
                    list(LOCATIONS.keys())
                )
            }),
            description_placeholders={
                "info": "Wybierz dzielnicę, aby zobaczyć dostępne przystanki."
            },
            errors=errors,
        )

    async def async_step_stop(self, user_input=None):
        """Krok 2 — wybór konkretnego przystanku."""
        errors = {}

        # Pobierz przystanki dla wybranej lokalizacji
        keywords = LOCATIONS.get(self._location, [])
        self._stops = await self.hass.async_add_executor_job(
            fetch_stops, keywords
        )

        if not self._stops:
            errors["base"] = "no_stops"
            return self.async_show_form(
                step_id="stop",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if user_input is not None:
            stop_id = user_input["stop_id"]
            stop_name = self._stops.get(stop_id, stop_id)
            max_dep = user_input.get("max_departures", 6)

            # Sprawdź czy taki sensor już istnieje
            await self.async_set_unique_id(f"ztm_gdansk_{stop_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"ZTM — {stop_name}",
                data={
                    "stop_id": stop_id,
                    "stop_name": stop_name,
                    "location": self._location,
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
            description_placeholders={
                "location": self._location,
                "count": str(len(self._stops)),
            },
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
