"""Pure routing policy; independent of Home Assistant."""
from .const import APP_COUNTRIES, DEFAULT_COUNTRIES, DIRECT, IGNORED_APPS, UNASSIGNED


def active_tunnels(tunnels):
    """Rank by country; use actual tunnelCode rather than countryCode for writes."""
    def priority(tunnel):
        country = tunnel.get("countryCode")
        return DEFAULT_COUNTRIES.index(country) if country in DEFAULT_COUNTRIES else len(DEFAULT_COUNTRIES)
    return sorted((t for t in tunnels if float(t.get("activeNum", 0)) >= 1), key=priority)


def choose_tunnel(tunnels, app=None):
    ranked = active_tunnels(tunnels)
    if not ranked:
        raise ValueError("No active DPN tunnels")
    for country in APP_COUNTRIES.get(app, []):
        match = next((t for t in ranked if t.get("countryCode") == country), None)
        if match:
            return match["tunnelCode"]
    return ranked[0]["tunnelCode"]


def repair_plan(snapshot):
    """Repair only rules pointing to unavailable DPN tunnels, preserving special modes."""
    tunnels = snapshot["tunnels"]
    active = {t["tunnelCode"] for t in active_tunnels(tunnels)}
    if not active:
        return [], []
    apps = [(a["app"], choose_tunnel(tunnels, a["app"])) for a in snapshot["apps"]
            if a["app"] not in IGNORED_APPS and a["tunnel"] not in {UNASSIGNED, DIRECT}
            and a["tunnel"] not in active]
    domains = [(d["domainName"], d["tunnelCode"], choose_tunnel(tunnels)) for d in snapshot["domains"]
               if d["tunnelCode"] not in active and d["tunnelCode"] not in {UNASSIGNED, DIRECT}]
    return apps, domains
