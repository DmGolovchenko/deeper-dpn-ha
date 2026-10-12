"""Readable labels for the four application routing selectors."""
from .const import DIRECT, UNASSIGNED
from .policy import active_tunnels

from .localization import text


def app_route_options(snapshot, app, language="en"):
    """Map display labels to actual API codes, retaining an offline current route."""
    choices = {text("direct", language): DIRECT, text("general", language): UNASSIGNED}
    tunnels = {t["tunnelCode"]: t for t in snapshot["tunnels"]}
    active = {t["tunnelCode"] for t in active_tunnels(snapshot["tunnels"])}

    def label(code):
        country = tunnels.get(code, {}).get("countryCode")
        name = text(country, language, country) if country else None
        display = f"{name} ({code})" if name else code
        return display if code in active else f"{display} — {text("unavailable", language)}"

    for tunnel in active_tunnels(snapshot["tunnels"]):
        code = tunnel["tunnelCode"]
        if code not in {DIRECT, UNASSIGNED}:
            choices[label(code)] = code
    current = next((a["tunnel"] for a in snapshot["apps"] if a["app"] == app), None)
    if current is not None and current not in choices.values():
        choices[label(current)] = current
    return choices
