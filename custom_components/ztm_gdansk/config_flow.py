"""Config Flow — ZTM Gdańsk."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"

DEPARTURES_URL = "https://ckan2.multimediagdansk.pl/departures?stopId={stop_id}"
STOPS_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json"
)


class ZTMGdanskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _async_verify_stop(self, stop_id: str) -> tuple[bool, str]:
        """
        Weryfikuje przystanek odpytując endpoint odjazdów.
        Zwraca (sukces, nazwa_przystanku).
        """
        try:
            session = async_get_clientsession(self.hass)
            url = DEPARTURES_URL.format(stop_id=stop_id)
            async with session.get(url) as resp:
                if resp.status != 200:
                    _LOGGER.error("ZTM departures HTTP %s dla stopId=%s", resp.status, stop_id)
                    return False, ""
                data = await resp.json(content_type=None)

            # Jeśli API odpowiedziało (nawet pustą listą) — przystanek istnieje
            if "lastUpdate" in data or "departures" in data:
                # Spróbuj pobrać nazwę z stops.json (opcjonalnie, krótki timeout)
                name = await self._async_get_stop_name(stop_id)
                return True, name

            return False, ""

        except Exception as e:
            _LOGGER.error("ZTM: błąd weryfikacji przystanku %s: %s", stop_id, e)
            return False, ""

    async def _async_get_stop_name(self, stop_id: str) -> str:
        """Próbuje pobrać nazwę przystanku. Jeśli się nie uda — zwraca samo ID."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(STOPS_URL) as resp:
                if resp.status != 200:
                    return stop_id
                raw = await resp.json(content_type=None)

            if isinstance(raw, dict):
                date_key = next(iter(raw))
                stops_list = raw[date_key].get("stops", [])
            elif isinstance(raw, list):
                stops_list = raw
            else:
                return stop_id

            for stop in stops_list:
                if str(stop.get("stopId", "")) == stop_id:
                    name = stop.get("stopName", "").strip()
                    sub  = stop.get("subName", "").strip()
                    return f"{name} {sub}".strip() if sub else name

            return stop_id

        except Exception as e:
            _LOGGER.warning("ZTM: nie udało się pobrać nazwy dla %s: %s", stop_id, e)
            return stop_id

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            stop_id = str(user_input["stop_id"]).strip()
            max_dep = int(user_input["max_departures"])

            ok, stop_name = await self._async_verify_stop(stop_id)

            if not ok:
                errors["stop_id"] = "stop_not_found"
            else:
                await self.async_set_unique_id(f"ztm_gdansk_{stop_id}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"ZTM {stop_name} [{stop_id}]",
                    data={
                        "stop_id":        stop_id,
                        "stop_name":      stop_name if stop_name != stop_id else f"Przystanek {stop_id}",
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
