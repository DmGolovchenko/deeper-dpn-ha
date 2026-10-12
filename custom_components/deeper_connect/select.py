"""Explicit per-application routing selection."""
from homeassistant.components.select import SelectEntity

from .const import DIRECT, UNASSIGNED
from .entity import DeeperEntity, discover
from .policy import active_tunnels


async def async_setup_entry(hass, entry, async_add_entities):
    discover(entry.runtime_data, async_add_entities, "apps", DeeperAppSelect)


class DeeperAppSelect(DeeperEntity, SelectEntity):
    _attr_icon = "mdi:routes"

    def __init__(self, coordinator, app):
        super().__init__(coordinator, f"app_{app}_route", f"{app} route")
        self.app = app

    @property
    def current_option(self):
        return next((a["tunnel"] for a in self.coordinator.data["apps"] if a["app"] == self.app), None)

    @property
    def available(self):
        return super().available and self.current_option is not None

    @property
    def options(self):
        choices = [UNASSIGNED, DIRECT] + [t["tunnelCode"] for t in active_tunnels(self.coordinator.data["tunnels"])]
        if self.current_option:
            choices.append(self.current_option)
        return list(dict.fromkeys(choices))

    @property
    def extra_state_attributes(self):
        return {"modes": {UNASSIGNED: "Remove application rule", DIRECT: "Direct route"},
                "tunnel_countries": {t["tunnelCode"]: t.get("countryCode") for t in self.coordinator.data["tunnels"]}}

    async def async_select_option(self, option):
        await self.coordinator.set_app(self.app, code=option)
