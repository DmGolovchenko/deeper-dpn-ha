"""The eight requested device information sensors."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory

from .entity import DeeperEntity
from .policy import active_tunnels

METRICS = {
    "temperature": ("Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "installed_version": ("AtomOS version", None, None),
    "latest_version": ("Latest AtomOS version", None, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([
        DeeperCount(coordinator, "tunnels", "Active tunnels"),
        DeeperCount(coordinator, "domains", "Whitelist domains count"),
        DeeperMetric(coordinator, "installed_version"),
        DeeperMetric(coordinator, "latest_version"),
        DeeperMetric(coordinator, "temperature"),
        DeeperHardware(coordinator, "cpuCount", "CPU cores"),
        DeeperHardware(coordinator, "cpuModel", "CPU model"),
        DeeperHardware(coordinator, "totalMem", "Total memory"),
    ])


class DeeperCount(DeeperEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, f"count_{key}", name)
        self.key = key
        self._attr_icon = "mdi:vpn" if key == "tunnels" else "mdi:format-list-checks"

    @property
    def native_value(self):
        values = self.coordinator.data[self.key]
        return len(active_tunnels(values)) if self.key == "tunnels" else len(values)


class DeeperMetric(DeeperEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key):
        name, unit, device_class = METRICS[key]
        super().__init__(coordinator, key, name)
        self.key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_icon = {"installed_version": "mdi:information-outline", "latest_version": "mdi:update", "temperature": "mdi:thermometer"}[key]
        if key == "temperature":
            self._attr_suggested_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_suggested_display_precision = 1
            self._attr_icon = "mdi:thermometer"
        if unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def native_value(self):
        return self.coordinator.data["telemetry"].get(self.key)


class DeeperHardware(DeeperEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, f"hardware_{key}", name)
        self.key = key
        self._attr_icon = {"cpuCount": "mdi:cpu-64-bit", "cpuModel": "mdi:chip", "totalMem": "mdi:memory"}[key]
        if key == "totalMem":
            self._attr_native_unit_of_measurement = "MiB"
            self._attr_device_class = SensorDeviceClass.DATA_SIZE

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def native_value(self):
        value = self.coordinator.data.get("hardware", {}).get(self.key)
        if self.key == "totalMem" and isinstance(value, (int, float)):
            return round(value / 1048576, 1)
        return value

