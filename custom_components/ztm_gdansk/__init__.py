"""ZTM Gdańsk — integracja odjazdów autobusów i tramwajów."""
import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.persistent_notification import async_create

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.async_create_task(_async_create_lovelace_card(hass, entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_create_lovelace_card(hass: HomeAssistant, entry: ConfigEntry) -> None:
    stop_id   = entry.data["stop_id"]
    stop_name = entry.data.get("stop_name", stop_id)
    max_dep   = int(entry.data.get("max_departures", 6))
    entity_id = f"sensor.ztm_{stop_id}"

    card_yaml = _build_card_yaml(entity_id, stop_name, max_dep)

    www_dir = hass.config.path("www/ztm_gdansk")

    def _write():
        os.makedirs(www_dir, exist_ok=True)
        path = os.path.join(www_dir, f"card_{stop_id}.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(card_yaml)
        return path

    try:
        path = await hass.async_add_executor_job(_write)
        _LOGGER.info("ZTM Gdańsk: karta zapisana → %s", path)
    except Exception as e:
        _LOGGER.error("ZTM Gdańsk: błąd zapisu karty: %s", e)
        return

    async_create(
        hass,
        message=(
            f"✅ Przystanek **{stop_name}** (`{stop_id}`) dodany!\n\n"
            f"Karta Lovelace zapisana w:\n"
            f"`config/www/ztm_gdansk/card_{stop_id}.yaml`\n\n"
            f"Aby dodać kartę do dashboardu:\n"
            f"1. Edytuj dashboard → **Dodaj kartę** → **Ręczna konfiguracja YAML**\n"
            f"2. Wklej zawartość pliku `card_{stop_id}.yaml`"
        ),
        title="ZTM Gdańsk 🚌",
        notification_id=f"ztm_card_{stop_id}",
    )


def _build_card_yaml(entity_id: str, stop_name: str, max_dep: int) -> str:
    rows = ""
    for i in range(max_dep):
        rows += f"""      - type: conditional
        conditions:
          - condition: template
            value_template: >-
              {{{{ (state_attr('{entity_id}', 'odjazdy') or []) | length > {i} }}}}
        row:
          type: attribute
          entity: {entity_id}
          attribute: tablica
          name: >-
            {{{{ (state_attr('{entity_id}', 'odjazdy') or [])[{i}]['linia'] | default('') }}}}
            → {{{{ (state_attr('{entity_id}', 'odjazdy') or [])[{i}]['kierunek'] | default('') }}}}
          suffix: >-
            za {{{{ (state_attr('{entity_id}', 'odjazdy') or [])[{i}]['za_minuty'] | default('?') }}}} min
\n"""

    return f"""type: vertical-stack
cards:
  - type: entity
    entity: {entity_id}
    name: "{stop_name}"
    icon: mdi:bus-stop

  - type: markdown
    content: >
      ## 🚌 Najbliższe odjazdy — {stop_name}

      {{{{ state_attr('{entity_id}', 'tablica') }}}}
"""
