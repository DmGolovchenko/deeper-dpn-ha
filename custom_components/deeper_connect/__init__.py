"""Local Deeper Connect integration."""
from datetime import timedelta
import logging

try:
    import probatio as vol  # Home Assistant 2026.10
except ImportError:
    import voluptuous as vol  # Earlier Home Assistant releases
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval

from .api import DeeperApi
from .const import DOMAIN, PLATFORMS
from .coordinator import DeeperCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    api = DeeperApi(entry.data["base_url"], entry.data["username"], entry.data["password"], entry.options.get("telemetry_profile"))
    coordinator = DeeperCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await api.close()
        raise
    entry.runtime_data = coordinator
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await api.close()
        raise
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    if entry.options.get("auto_refresh", False):
        async def automatic_refresh(now):
            try:
                await coordinator.refresh_all()
            except HomeAssistantError as err:
                _LOGGER.warning("Automatic Deeper refresh failed: %s", err)
        entry.async_on_unload(async_track_time_interval(hass, automatic_refresh, timedelta(hours=4)))

    if not hass.services.has_service(DOMAIN, "refresh_tunnels"):
        async def refresh(call):
            await get_coordinator(hass, call).refresh_all(call.data.get("repair", True))
        async def set_domain(call):
            await get_coordinator(hass, call).set_domain(call.data["domain_name"], call.data["tunnel_code"])
        hass.services.async_register(DOMAIN, "refresh_tunnels", refresh, schema=vol.Schema({
            vol.Required("entry_id"): str, vol.Optional("repair", default=True): bool,
        }))
        hass.services.async_register(DOMAIN, "set_domain_tunnel", set_domain, schema=vol.Schema({
            vol.Required("entry_id"): str, vol.Required("domain_name"): str, vol.Required("tunnel_code"): str,
        }))
    return True


def get_coordinator(hass, call):
    entry = hass.config_entries.async_get_entry(call.data["entry_id"])
    if entry is None or entry.domain != DOMAIN or not isinstance(getattr(entry, "runtime_data", None), DeeperCoordinator):
        raise HomeAssistantError("Deeper integration is not loaded")
    return entry.runtime_data


async def async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.shutdown()
        entry.runtime_data = None
        if not any(isinstance(getattr(e, "runtime_data", None), DeeperCoordinator) for e in hass.config_entries.async_entries(DOMAIN)):
            hass.services.async_remove(DOMAIN, "refresh_tunnels")
            hass.services.async_remove(DOMAIN, "set_domain_tunnel")
        return True
    return False
