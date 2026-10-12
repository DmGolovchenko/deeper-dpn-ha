"""Constants for Deeper Connect."""
DOMAIN = "deeper_connect"
PLATFORMS = ["button", "select", "sensor", "update"]
ENTITY_KEYS = {
    "count_tunnels", "count_domains", "installed_version", "latest_version",
    "temperature", "hardware_cpuCount", "hardware_cpuModel", "hardware_totalMem",
    "firmware", "refresh_all", "reboot", "routing_mode",
}
DEFAULT_COUNTRIES = ["SE", "DE", "TR", "FR", "US", "CA", "CH", "IT", "SG", "CN", "AE"]
APP_COUNTRIES = {
    "instagram": ["SE", "DE", "TR", "FR", "CA", "US", "CH", "IT"],
    "telegram": ["TR", "SE", "DE", "FR", "CA", "US", "CH", "IT"],
}
IGNORED_APPS = {"youtube", "netflix", "plex"}
UNASSIGNED = "ZZ"
DIRECT = "LL"

DEFAULT_TELEMETRY = {
    "installed_version": {"endpoint": "/system-info/software-info", "path": ["softwareVersion"]},
    "latest_version": {"endpoint": "/system-info/get-latestversion", "path": ["latestVersion"]},
}

APP_CONTROLS = {
    "instagram": {"name": "Instagram", "icon": "mdi:instagram"},
    "youtube": {"name": "YouTube", "icon": "mdi:youtube"},
    "whatsapp": {"name": "WhatsApp", "icon": "mdi:whatsapp"},
    "telegram": {"name": "Telegram", "icon": "mdi:send"},
}
ENTITY_KEYS.update(f"app_{app}_route" for app in APP_CONTROLS)
