"""Refresh commands."""
from homeassistant.components.button import ButtonEntity

from .entity import DeeperEntity, discover


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([DeeperRefreshAll(coordinator), DeeperPoll(coordinator)])
    discover(coordinator, async_add_entities, "tunnels", DeeperTunnelRefresh)


class DeeperRefreshAll(DeeperEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator):
        super().__init__(coordinator, "refresh_all", "Refresh tunnels and repair routes")

    async def async_press(self):
        await self.coordinator.refresh_all()


class DeeperPoll(DeeperEntity, ButtonEntity):
    _attr_icon = "mdi:sync"

    def __init__(self, coordinator):
        super().__init__(coordinator, "poll", "Read device status / check updates")

    async def async_press(self):
        self.coordinator.api.invalidate_version_check()
        await self.coordinator.async_refresh()


class DeeperTunnelRefresh(DeeperEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator, code):
        super().__init__(coordinator, f"tunnel_{code}_refresh", f"Refresh tunnel {code}")
        self.code = code

    @property
    def available(self):
        return super().available and any(t["tunnelCode"] == self.code for t in self.coordinator.data["tunnels"])

    async def async_press(self):
        await self.coordinator.refresh_one(self.code)
