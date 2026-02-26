"""Config Flow — ZTM Gdańsk."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"

STOPS_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json"
)


class ZTMGdanskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._all_stops: dict = {}

    async def _async_fetch_stops(self) -> dict:
        """Pobiera wszystkie przystanki z API ZTM."""
        try:
            session = async_get_clientsession(self.hass)
            resp = await session.get(STOPS_URL, timeout=30)
            if resp.status != 200:
                _LOGGER.error("ZTM API zwróciło HTTP %s", resp.status)
                return {}

            raw = await resp.json(content_type=None)

            # Struktura: {"2026-02-26": {"stops": [...]}}
            if isinstance(raw, dict):
                date_key = next(iter(raw))
                stops_list = raw[date_key].get("stops", [])
            elif isinstance(raw, list):
                stops_list = raw
            else:
                _LOGGER.error("ZTM API — nieznany format danych: %s", type(raw))
                return {}

            result = {}
            for stop in stops_list:
                stop_id = str(stop.get("stopId", "")).strip()
                name    = stop.get("stopName", "").strip()
                sub     = stop.get("subName", "").strip()
                desc    = stop.get("stopDesc", "").strip()
                if stop_id and name:
                    result[stop_id] = {
                        "name": name,
                        "sub":  sub,
                        "desc": desc,
                    }

            _LOGGER.debug("ZTM: załadowano %d przystanków", len(result))
            return result

        except Exception as e:
            _LOGGER.error("ZTM: wyjątek przy pobieraniu przystanków: %s", e)
            return {}

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            stop_id = str(user_input["stop_id"]).strip()
            max_dep = int(user_input["max_departures"])

            if not self._all_stops:
                self._all_stops = await self._async_fetch_stops()

            if not self._all_stops:
                errors["base"] = "cannot_connect"
            else:
                stop_data = self._all_stops.get(stop_id)
                if not stop_data:
                    errors["stop_id"] = "stop_not_found"
                else:
                    await self.async_set_unique_id(f"ztm_gdansk_{stop_id}")
                    self._abort_if_unique_id_configured()

                    stop_name = stop_data["name"]
                    if stop_data["sub"]:
                        stop_name += f" {stop_data['sub']}"

                    return self.async_create_entry(
                        title=f"ZTM {stop_name} [{stop_id}]",
                        data={
                            "stop_id":        stop_id,
                            "stop_name":      stop_name,
                            "max_departures": max_dep,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("stop_id"): str,
                vol.Required("max_departures", default=6): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=15)
                ),
            }),
            errors=errors,
        )
