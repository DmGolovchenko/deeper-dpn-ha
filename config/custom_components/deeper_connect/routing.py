"""Global routing controls, preserving device-configured tunnels."""
MODE_OPTIONS = {"disabled": "Direct", "smart": "Smart", "full": "Full"}


def route_parameters(state, mode, tunnels):
    if mode not in MODE_OPTIONS:
        raise ValueError("Unsupported routing mode")
    field = {"smart": "smartTunnel", "full": "fullTunnel", "disabled": "tunnelCode"}[mode]
    code = state.get(field)
    if not isinstance(code, str) or not code:
        raise ValueError("Configure the routing tunnel in AtomOS first")
    if mode == "full" and code not in {t["tunnelCode"] for t in tunnels if t.get("activeNum", 0) >= 1}:
        raise ValueError("The configured Full routing tunnel has no active IPs")
    return {"dpnMode": mode, "tunnelCode": code}
