"""Routing counters and optional confirmed telemetry."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory

from .entity import DeeperEntity, discover
from .policy import active_tunnels

METRICS = {
    "temperature": ("Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "cpu_usage": ("CPU usage", PERCENTAGE, None),
    "memory_usage": ("Memory usage", PERCENTAGE, None),
    "installed_version": ("AtomOS version", None, None),
    "latest_version": ("Latest AtomOS version", None, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([DeeperCount(coordinator, "tunnels", "Active tunnels"),
                        DeeperCount(coordinator, "domains", "Whitelist domains")]
                       + [DeeperMetric(coordinator, key) for key in ({"temperature"} | set(coordinator.api.profile))]
                       + [DeeperHardware(coordinator, key, name) for key, name in {
                           "cpuCount": "CPU cores", "cpuModel": "CPU model", "totalMem": "Total memory"
                       }.items()]
                       + [DeeperInfo(coordinator, group, key, name) for group, key, name in [
                           ("network", "ip", "IP address"), ("network", "pubIp", "Public IP address"),
                           ("software", "appSigVersion", "Application signatures version"),
                           ("software", "builtinRuleVersion", "Built-in rules version"),
                           ("software", "urlSigVersion", "URL signatures version"),
                       ]])

    discover(coordinator, async_add_entities, "tunnels", DeeperTunnelIPs)


class DeeperCount(DeeperEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator, f"count_{key}", name)
        self.key = key

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


class DeeperInfo(DeeperEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, group, key, name):
        super().__init__(coordinator, f"{group}_{key}", name)
        self.group, self.key = group, key

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def native_value(self):
        return self.coordinator.data.get(self.group, {}).get(self.key)


class DeeperTunnelIPs(DeeperEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator, code):
        super().__init__(coordinator, f"tunnel_{code}_ips", f"Tunnel {code} active IPs")
        self.code = code

    @property
    def tunnel(self):
        return next((t for t in self.coordinator.data["tunnels"] if t["tunnelCode"] == self.code), None)

    @property
    def available(self):
        return super().available and self.tunnel is not None

    @property
    def native_value(self):
        return self.tunnel["activeNum"] if self.tunnel else None

    @property
    def extra_state_attributes(self):
        if not self.tunnel:
            return {}
        return {key: self.tunnel.get(key) for key in ("countryCode", "regionCode", "activeIp", "addedByUser")}
