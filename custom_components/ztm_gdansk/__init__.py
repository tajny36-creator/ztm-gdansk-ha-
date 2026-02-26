"""ZTM Gdańsk — integracja odjazdów autobusów i tramwajów."""
import os
import json
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.lovelace import _get_lovelace_data

_LOGGER = logging.getLogger(__name__)
DOMAIN = "ztm_gdansk"
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Automatycznie generuj kartę Lovelace po dodaniu integracji
    hass.async_create_task(
        _async_create_lovelace_card(hass, entry)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_create_lovelace_card(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Tworzy gotową kartę Lovelace i zapisuje ją jako plik YAML."""
    stop_id   = entry.data["stop_id"]
    stop_name = entry.data.get("stop_name", stop_id)
    max_dep   = entry.data.get("max_departures", 6)
    entity_id = f"sensor.ztm_{stop_id}"

    card_yaml = _build_card_yaml(entity_id, stop_name, max_dep)

    # Zapisz do www/ żeby użytkownik mógł łatwo skopiować
    www_dir = hass.config.path("www/ztm_gdansk")
    os.makedirs(www_dir, exist_ok=True)

    card_path = os.path.join(www_dir, f"card_{stop_id}.yaml")
    try:
        with open(card_path, "w", encoding="utf-8") as f:
            f.write(card_yaml)
        _LOGGER.info(
            "ZTM Gdańsk: karta Lovelace zapisana → %s", card_path
        )
    except Exception as e:
        _LOGGER.error("ZTM Gdańsk: błąd zapisu karty: %s", e)

    # Powiadomienie w HA UI
    hass.components.persistent_notification.async_create(
        message=(
            f"✅ **ZTM Gdańsk** — przystanek **{stop_name}** dodany!\n\n"
            f"Gotowa karta Lovelace została zapisana w:\n"
            f"`config/www/ztm_gdansk/card_{stop_id}.yaml`\n\n"
            f"Skopiuj jej zawartość do edytora kart w Lovelace "
            f"(tryb YAML) lub użyj przycisku poniżej."
        ),
        title="ZTM Gdańsk — karta gotowa 🚌",
        notification_id=f"ztm_card_{stop_id}",
    )


def _build_card_yaml(entity_id: str, stop_name: str, max_dep: int) -> str:
    """Generuje YAML karty Lovelace dla danego przystanku."""
    rows = "\n".join([
        f"""          - type: conditional
            conditions:
              - condition: template
                value_template: >
                  {{{{ state_attr('{entity_id}', 'odjazdy') | length > {i} }}}}
            row:
              type: custom:template-entity-row
              entity: {entity_id}
              name: >
                {{{{ state_attr('{entity_id}', 'odjazdy')[{i}].linia }}}}
              secondary: >
                {{{{ state_attr('{entity_id}', 'odjazdy')[{i}].kierunek }}}}
              state: >
                {{{{ state_attr('{entity_id}', 'odjazdy')[{i}].za_minuty }}}} min
              icon: mdi:bus"""
        for i in range(max_dep)
    ])

    return f"""type: vertical-stack
cards:
  - type: custom:mushroom-template-card
    primary: "{stop_name}"
    secondary: >
      🕐 Aktualizacja: {{{{ state_attr('{entity_id}', 'ostatnia_aktualizacja') }}}}
    icon: mdi:bus-stop
    icon_color: blue
    tap_action:
      action: more-info
    entity: {entity_id}

  - type: entities
    title: Najbliższe odjazdy
    show_header_toggle: false
    entities:
{rows}

  - type: custom:mushroom-template-card
    primary: >
      {{{{ state_attr('{entity_id}', 'liczba_odjazdow') }}}} odjazdów w kolejce
    secondary: "Przystanek ID: {{{{ state_attr('{entity_id}', 'stop_id') }}}}"
    icon: mdi:information-outline
    icon_color: grey
    entity: {entity_id}
"""
