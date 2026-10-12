"""Shared device and dynamically discovered entity support."""
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class DeeperEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title, manufacturer="Deeper Network",
            model="Deeper Connect Mini", sw_version=coordinator.data.get("telemetry", {}).get("installed_version"), serial_number=coordinator.data.get("hardware", {}).get("SN"), configuration_url=coordinator.api.base_url.removesuffix("/api"),
        )


@callback
def discover(coordinator, async_add_entities, collection, factory):
    known = set()

    @callback
    def update():
        entities = []
        for item in coordinator.data[collection]:
            key = item["app"] if collection == "apps" else item["tunnelCode"]
            if key not in known:
                known.add(key)
                entities.append(factory(coordinator, key))
        if entities:
            async_add_entities(entities)

    update()
    coordinator.entry.async_on_unload(coordinator.async_add_listener(update))
