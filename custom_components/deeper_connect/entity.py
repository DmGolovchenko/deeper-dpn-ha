"""Shared device information for the requested entities."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class DeeperEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = {
            "hardware_cpuCount": "cpu_cores",
            "hardware_cpuModel": "cpu_model",
            "hardware_totalMem": "total_memory",
        }.get(key, key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title, manufacturer="Deeper Network",
            model="Deeper Connect Mini", sw_version=coordinator.data.get("telemetry", {}).get("installed_version"), serial_number=coordinator.data.get("hardware", {}).get("SN"), configuration_url=coordinator.api.base_url.removesuffix("/api"),
        )

