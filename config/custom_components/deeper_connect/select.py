"""Device routing mode and four application route selectors."""
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .app_routes import app_route_options
from .const import DIRECT, UNASSIGNED
from .entity import DeeperEntity
from .localization import ha_language, mode_options, text
from .services_config import app_details, custom_current_route, selected_apps
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([DeeperRoutingMode(coordinator)]
                       + [DeeperAppRoute(coordinator, app) for app in selected_apps(entry.options)]
                       + [DeeperCustomRoute(coordinator, service) for service in entry.options.get("custom_services", [])])


class DeeperRoutingMode(DeeperEntity, SelectEntity):
    _attr_icon = "mdi:routes"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "routing_mode", "Routing mode")

    @property
    def mode_choices(self):
        return mode_options(ha_language(self.coordinator.hass))

    @property
    def options(self):
        return list(self.mode_choices.values())

    @property
    def current_option(self):
        return self.mode_choices.get(self.coordinator.data.get("routing", {}).get("dpnMode"))

    @property
    def icon(self):
        mode = self.coordinator.data.get("routing", {}).get("dpnMode")
        return {"disabled": "mdi:lan-connect", "smart": "mdi:routes", "full": "mdi:vpn"}.get(mode, "mdi:routes")

    @property
    def available(self):
        return super().available and self.current_option is not None

    @property
    def extra_state_attributes(self):
        state = self.coordinator.data.get("routing", {})
        return {key: state.get(key) for key in ("tunnelCode", "smartTunnel", "fullTunnel")}

    async def async_select_option(self, option):
        mode = next((key for key, label in self.mode_choices.items() if label == option), None)
        if mode is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="routing_option_unavailable")
        await self.coordinator.set_routing_mode(mode)


class DeeperAppRoute(DeeperEntity, SelectEntity):
    def __init__(self, coordinator, app):
        details = app_details(app)
        super().__init__(coordinator, f"app_{app}_route", f"{details['name']} route")
        self.app = app
        if app not in {"instagram", "youtube", "whatsapp", "telegram"}:
            self._attr_translation_key = "app_route"
            self._attr_translation_placeholders = {"app": details["name"]}
        self._attr_icon = details["icon"]

    @property
    def route_choices(self):
        return app_route_options(self.coordinator.data, self.app, ha_language(self.coordinator.hass))

    @property
    def options(self):
        return list(self.route_choices)

    @property
    def current_option(self):
        current = next((a["tunnel"] for a in self.coordinator.data["apps"] if a["app"] == self.app), None)
        return next((label for label, code in self.route_choices.items() if code == current), None)

    @property
    def available(self):
        return super().available and self.current_option is not None

    @property
    def extra_state_attributes(self):
        current = next((a["tunnel"] for a in self.coordinator.data["apps"] if a["app"] == self.app), None)
        return {"current_tunnel": current}

    async def async_select_option(self, option):
        target = self.route_choices.get(option)
        if target is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="routing_option_unavailable")
        # The coordinator rechecks active tunnels immediately before writing.
        await self.coordinator.set_app(self.app, code=target)


class DeeperCustomRoute(DeeperEntity, SelectEntity):
    _attr_icon = "mdi:web"

    def __init__(self, coordinator, service):
        super().__init__(coordinator, f"custom_{service['id']}_route", service["name"])
        self.service = service
        self._attr_translation_key = "custom_service_route"
        self._attr_translation_placeholders = {"service": service["name"]}

    @property
    def route_choices(self):
        language = ha_language(self.coordinator.hass)
        current = custom_current_route(self.coordinator.data, self.service)
        fake = {**self.coordinator.data, "apps": [{"app": "custom", "tunnel": current if current != "__mixed__" else None}]}
        choices = {label: code for label, code in app_route_options(fake, "custom", language).items() if code != UNASSIGNED}
        if current == "__mixed__":
            choices[text("mixed", language)] = "__mixed__"
        return choices

    @property
    def options(self):
        return list(self.route_choices)

    @property
    def current_option(self):
        current = custom_current_route(self.coordinator.data, self.service)
        return next((label for label, code in self.route_choices.items() if code == current), None)

    @property
    def extra_state_attributes(self):
        return {"domains": self.service["domains"], "current_tunnel": custom_current_route(self.coordinator.data, self.service)}

    async def async_select_option(self, option):
        target = self.route_choices.get(option)
        if target is None or target == "__mixed__":
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="routing_option_unavailable")
        await self.coordinator.configure_domains(self.service["domains"], target)
