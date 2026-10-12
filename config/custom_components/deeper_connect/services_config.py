"""Validate custom services and determine only the user-selected entity set."""
import re

from .const import APP_CONTROLS, ENTITY_KEYS


def selected_apps(options):
    return list(dict.fromkeys(options.get("selected_apps", list(APP_CONTROLS))))


def app_details(app):
    return APP_CONTROLS.get(app, {"name": app.replace("_", " ").title(), "icon": "mdi:application"})


def configured_entity_keys(options):
    keys = ENTITY_KEYS - {f"app_{app}_route" for app in APP_CONTROLS}
    keys |= {f"app_{app}_route" for app in selected_apps(options)}
    keys |= {f"custom_{service['id']}_route" for service in options.get("custom_services", [])}
    return keys


def parse_domains(value):
    if not isinstance(value, str):
        raise ValueError("Enter domain names")
    domains = []
    for raw in re.split(r"[\s,;]+", value.strip()):
        if not raw:
            continue
        try:
            domain = raw.rstrip(".").lower().encode("idna").decode("ascii")
        except UnicodeError as err:
            raise ValueError("Invalid domain") from err
        labels = domain.split(".")
        if len(domain) > 253 or len(labels) < 2 or all(label.isdigit() for label in labels):
            raise ValueError("Enter a domain rather than an IP address")
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
            raise ValueError("Invalid domain; URLs and wildcards are not supported")
        if domain not in domains:
            domains.append(domain)
    if not domains or len(domains) > 50:
        raise ValueError("Enter between 1 and 50 domains")
    return domains


def domain_plan(snapshot, domains, target):
    existing = {entry["domainName"]: entry["tunnelCode"] for entry in snapshot["domains"]}
    return [(domain, existing.get(domain), target) for domain in domains if existing.get(domain) != target]


def custom_current_route(snapshot, service):
    existing = {entry["domainName"]: entry["tunnelCode"] for entry in snapshot["domains"]}
    values = {existing.get(domain) for domain in service["domains"]}
    if values == {None}:
        return None
    if len(values) == 1:
        return next(iter(values))
    return "__mixed__"
