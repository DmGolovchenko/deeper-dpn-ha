"""Constants for Deeper Connect."""
DOMAIN = "deeper_connect"
PLATFORMS = ["button", "select", "sensor", "switch", "update"]
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
