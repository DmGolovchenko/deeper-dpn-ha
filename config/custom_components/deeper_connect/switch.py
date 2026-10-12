"""Enable/disable an application-specific DPN route."""
from homeassistant.components.switch import SwitchEntity

from .const import DIRECT, UNASSIGNED
from .entity import DeeperEntity, discover


async def async_setup_entry(hass, entry, async_add_entities):
    discover(entry.runtime_data, async_add_entities, "apps", DeeperAppSwitch)


class DeeperAppSwitch(DeeperEntity, SwitchEntity):
    _attr_icon = "mdi:vpn"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, app):
        super().__init__(coordinator, f"app_{app}_dpn", f"{app} DPN")
        self.app = app

    @property
    def route(self):
        return next((a["tunnel"] for a in self.coordinator.data["apps"] if a["app"] == self.app), None)

    @property
    def available(self):
        return super().available and self.route is not None

    @property
    def is_on(self):
        return self.route is not None and self.route not in {DIRECT, UNASSIGNED}

    async def async_turn_on(self, **kwargs):
        await self.coordinator.set_app(self.app, enabled=True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.set_app(self.app, enabled=False)
