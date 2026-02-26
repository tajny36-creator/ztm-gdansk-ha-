"""ZTM Gdańsk — integracja odjazdów autobusów i tramwajów."""
import os
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Generuj kartę Lovelace w tle
    hass.async_create_task(
        _async_create_lovelace_card(hass, entry)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_create_lovelace_card(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Zapisuje gotową kartę Lovelace do pliku YAML."""
    stop_id   = entry.data["stop_id"]
    stop_name = entry.data.get("stop_name", stop_id)
    max_dep   = entry.data.get("max_departures", 6)
    entity_id = f"sensor.ztm_{stop_id}"

    card_yaml = _build_card_yaml(entity_id, stop_name, max_dep)

    www_dir = hass.config.path("www/ztm_gdansk")
    await hass.async_add_executor_job(os.makedirs, www_dir, 0o777, True)

    card_path = os.path.join(www_dir, f"card_{stop_id}.yaml")

    def _write():
        with open(card_path, "w", encoding="utf-8") as f:
            f.write(card_yaml)

    try:
        await hass.async_add_executor_job(_write)
        _LOGGER.info("ZTM Gdańsk: karta Lovelace zapisana → %s", card_path)
    except Exception as e:
        _LOGGER.error("ZTM Gdańsk: błąd zapisu karty: %s", e)

    hass.components.persistent_notification.async_create(
        message=(
            f"✅ **ZTM Gdańsk** — przystanek **{stop_name}** gotowy!\n\n"
            f"Karta Lovelace zapisana w:\n"
            f"`config/www/ztm_gdansk/card_{stop_id}.yaml`"
        ),
        title="ZTM Gdańsk 🚌",
        notification_id=f"ztm_card_{stop_id}",
    )


def _build_card_yaml(entity_id: str, stop_name: str, max_dep: int) -> str:
    rows = "\n".join([
        f"""      - type: conditional
        conditions:
          - condition: template
            value_template: >
              {{{{ state_attr('{entity_id}', 'odjazdy') | length > {i} }}}}
        row:
          type: section
          label: >
            {{{{ state_attr('{entity_id}', 'odjazdy')[{i}].linia }}}}
            → {{{{ state_attr('{entity_id}', 'odjazdy')[{i}].kierunek }}}}
            za {{{{ state_attr('{entity_id}', 'odjazdy')[{i}].za_minuty }}}} min"""
        for i in range(max_dep)
    ])

    return f"""type: vertical-stack
cards:
  - type: entity
    entity: {entity_id}
    name: "{stop_name}"
    icon: mdi:bus-stop

  - type: entities
    title: Najbliższe odjazdy
    entities:
{rows}
"""
