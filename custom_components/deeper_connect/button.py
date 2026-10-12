"""Manual refresh and device restart controls."""
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import DeeperEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([DeeperRefreshAll(coordinator), DeeperReboot(coordinator)])


class DeeperRefreshAll(DeeperEntity, ButtonEntity):
    _attr_icon = "mdi:sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "refresh_all", "Refresh and repair tunnels")

    async def async_press(self):
        await self.coordinator.refresh_all()



class DeeperReboot(DeeperEntity, ButtonEntity):
    _attr_icon = "mdi:restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "reboot", "Restart device")

    async def async_press(self):
        await self.coordinator.reboot()

