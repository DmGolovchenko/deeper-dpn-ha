"""Explicit, read-only API mappings. No guessed AtomOS endpoints."""
from urllib.parse import urlsplit

FIELDS = {"temperature", "cpu_usage", "memory_usage", "installed_version", "latest_version"}


def validate_profile(profile):
    if not isinstance(profile, dict) or set(profile) - FIELDS:
        raise ValueError("Unknown telemetry fields")
    for field, spec in profile.items():
        if not isinstance(spec, dict) or set(spec) - {"endpoint", "path", "scale"}:
            raise ValueError("Invalid telemetry specification")
        endpoint = spec.get("endpoint", "")
        if not isinstance(endpoint, str):
            raise ValueError("Endpoint must be a relative path")
        parsed = urlsplit(endpoint)
        if not endpoint.startswith("/") or endpoint.startswith("//") or parsed.netloc or parsed.scheme or parsed.fragment:
            raise ValueError("Endpoint must be on the configured device")
        if ".." in parsed.path.split("/") or "%" in parsed.path or "\\" in endpoint:
            raise ValueError("Invalid endpoint path")
        if not isinstance(spec.get("path"), list) or any(type(x) not in (str, int) for x in spec["path"]):
            raise ValueError("path must be a list of JSON keys or indexes")
        if not isinstance(spec.get("scale", 1), (int, float)):
            raise ValueError("scale must be numeric")
        if field.endswith("version") and "scale" in spec:
            raise ValueError("Version fields cannot be scaled")
    return profile


def extract_value(payload, spec, field):
    value = payload
    try:
        for key in spec["path"]:
            value = value[key]
    except (KeyError, IndexError, TypeError):
        return None
    if value is None:
        return None
    if field.endswith("version"):
        return str(value) if isinstance(value, (str, int, float)) else None
    try:
        import math
        result = float(value) * spec.get("scale", 1)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None
