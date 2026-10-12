"""Firmware version comparison; installing firmware is intentionally unsupported."""
from homeassistant.components.update import UpdateDeviceClass, UpdateEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import DeeperEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    if {"installed_version", "latest_version"} <= set(coordinator.api.profile):
        async_add_entities([DeeperFirmware(coordinator)])


class DeeperFirmware(DeeperEntity, UpdateEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_title = "AtomOS"
    _attr_icon = "mdi:chip"
    _attr_device_class = UpdateDeviceClass.FIRMWARE

    def __init__(self, coordinator):
        super().__init__(coordinator, "firmware", "AtomOS firmware")

    @property
    def entity_picture(self):
        # Let the entity show its firmware chip icon instead of a generic brand image.
        return None

    @property
    def installed_version(self):
        return self.coordinator.data["telemetry"].get("installed_version")

    @property
    def latest_version(self):
        return self.coordinator.data["telemetry"].get("latest_version")

    @property
    def available(self):
        return super().available and self.installed_version is not None and self.latest_version is not None
