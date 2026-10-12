"""Local Deeper Connect integration."""
from datetime import timedelta
import logging

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import entity_registry as er

from .api import DeeperApi
from .const import PLATFORMS
from .cleanup import is_obsolete_entity
from .services_config import configured_entity_keys
from .coordinator import DeeperCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    api = DeeperApi(entry.data["base_url"], entry.data["username"], entry.data["password"])
    coordinator = DeeperCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await api.close()
        raise
    entry.runtime_data = coordinator
    registry = er.async_get(hass)
    retained_keys = configured_entity_keys(entry.options)
    for entity in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if is_obsolete_entity(entity, entry.entry_id, retained_keys):
            registry.async_remove(entity.entity_id)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await api.close()
        raise
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    if entry.options.get("auto_refresh", False) and entry.options.get("auto_refresh_confirmed", False):
        async def automatic_refresh(now):
            try:
                await coordinator.refresh_all()
            except HomeAssistantError as err:
                _LOGGER.warning("Automatic Deeper refresh failed: %s", err)
        interval = timedelta(minutes=entry.options.get("refresh_interval_minutes", 60))
        entry.async_on_unload(async_track_time_interval(hass, automatic_refresh, interval))

    return True


async def async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.shutdown()
        entry.runtime_data = None
        return True
    return False
