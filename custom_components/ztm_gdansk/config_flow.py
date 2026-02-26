"""Config Flow — ZTM Gdańsk."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"

STOPS_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json"
)

LOCATIONS = {
    "Wrzeszcz":    ["Wrzeszcz", "Politechnika"],
    "Śródmieście": ["Śródmieście", "Główny", "Targ Węglowy"],
    "Oliwa":       ["Oliwa", "Żabianka", "Przymorze"],
    "Morena":      ["Morena", "Chętnika", "Łostowice"],
    "Nowy Port":   ["Nowy Port", "Brzeźno", "Stogi"],
    "Wszystkie":   [],
}


class ZTMGdanskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._location: str = "Wszystkie"
        self._stops: dict = {}
        self._all_stops: dict = {}  # id -> pełny obiekt przystanku

    async def _async_fetch_stops(self, keywords: list) -> dict:
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(STOPS_URL, timeout=15) as resp:
                if resp.status != 200:
                    return {}
                raw = await resp.json(content_type=None)

            if isinstance(raw, dict):
                date_key = next(iter(raw))
                stops_list = raw[date_key].get("stops", [])
            elif isinstance(raw, list):
                stops_list = raw
            else:
                return {}

            # Zapisz wszystkie przystanki do wyszukiwania po numerze
            self._all_stops = {
                str(s.get("stopId", "")): s for s in stops_list if s.get("stopId")
            }

            result = {}
            for stop in stops_list:
                name    = stop.get("stopName", "")
                stop_id = str(stop.get("stopId", ""))
                sub     = stop.get("subName", "")
                desc    = stop.get("stopDesc", "")
                label   = f"{name} {sub} — {desc} [{stop_id}]"

                if not name or not stop_id:
                    continue

                if not keywords or any(kw.lower() in name.lower() for kw in keywords):
                    result[stop_id] = label

            return dict(sorted(result.items(), key=lambda x: x[1]))

        except Exception as e:
            _LOGGER.error("Błąd pobierania przystanków ZTM: %s", e)
            return {}

    async def async_step_user(self, user_input=None):
        """Krok 1 — wybór metody: dzielnica lub numer przystanku."""
        errors = {}

        if user_input is not None:
            method = user_input.get("method", "dzielnica")

            if method == "numer":
                return await self.async_step_by_number()

            self._location = user_input.get("location", "Wszystkie")
            keywords = LOCATIONS.get(self._location, [])
            self._stops = await self._async_fetch_stops(keywords)

            if not self._stops:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_stop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("method", default="dzielnica"): vol.In({
                    "dzielnica": "🗺️ Wybierz dzielnicę",
                    "numer":     "🔢 Wpisz numer przystanku",
                }),
                vol.Optional("location", default="Wrzeszcz"): vol.In(
                    list(LOCATIONS.keys())
                ),
            }),
            errors=errors,
        )

    async def async_step_by_number(self, user_input=None):
        """Krok 1b — wpisz numer przystanku ręcznie."""
        errors = {}

        if user_input is not None:
            stop_id = str(user_input["stop_id"]).strip()

            # Upewnij się że mamy załadowane przystanki
            if not self._all_stops:
                await self._async_fetch_stops([])

            stop_data = self._all_stops.get(stop_id)
            if not stop_data:
                errors["stop_id"] = "stop_not_found"
            else:
                name      = stop_data.get("stopName", stop_id)
                sub       = stop_data.get("subName", "")
                desc      = stop_data.get("stopDesc", "")
                max_dep   = user_input.get("max_departures", 6)

                await self.async_set_unique_id(f"ztm_gdansk_{stop_id}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"ZTM — {name} {sub}",
                    data={
                        "stop_id":        stop_id,
                        "stop_name":      f"{name} {sub}",
                        "stop_desc":      desc,
                        "location":       "Ręczny",
                        "max_departures": max_dep,
                    },
                )

        return self.async_show_form(
            step_id="by_number",
            data_schema=vol.Schema({
                vol.Required("stop_id"): str,
                vol.Optional("max_departures", default=6): vol.All(
                    int, vol.Range(min=1, max=15)
                ),
            }),
            errors=errors,
        )

    async def async_step_stop(self, user_input=None):
        """Krok 2 — wybór przystanku z listy."""
        if user_input is not None:
            stop_id   = user_input["stop_id"]
            stop_data = self._all_stops.get(stop_id, {})
            name      = stop_data.get("stopName", stop_id)
            sub       = stop_data.get("subName", "")
            desc      = stop_data.get("stopDesc", "")
            max_dep   = user_input.get("max_departures", 6)

            await self.async_set_unique_id(f"ztm_gdansk_{stop_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"ZTM — {name} {sub}",
                data={
                    "stop_id":        stop_id,
                    "stop_name":      f"{name} {sub}",
                    "stop_desc":      desc,
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
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZTMOptionsFlow(config_entry)


class ZTMOptionsFlow(config_entries.OptionsFlow):
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
