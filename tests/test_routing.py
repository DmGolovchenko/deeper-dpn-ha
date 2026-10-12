"""Global modes preserve the user's configured Smart/Full tunnels."""
import importlib
import unittest

from test_core import PACKAGE, tunnel
routing = importlib.import_module(f"{PACKAGE}.routing")


class RoutingTests(unittest.TestCase):
    state = {"dpnMode": "smart", "tunnelCode": "US", "smartTunnel": "US", "fullTunnel": "SE"}

    def test_full_uses_configured_tunnel_not_current_smart_tunnel(self):
        result = routing.route_parameters(self.state, "full", [tunnel("US", "US"), tunnel("SE", "SE")])
        self.assertEqual(result, {"dpnMode": "full", "tunnelCode": "SE"})

    def test_smart_preserves_configured_tunnel(self):
        self.assertEqual(routing.route_parameters(self.state, "smart", []), {"dpnMode": "smart", "tunnelCode": "US"})

    def test_direct_does_not_require_active_tunnel(self):
        self.assertEqual(routing.route_parameters(self.state, "disabled", []), {"dpnMode": "disabled", "tunnelCode": "US"})

    def test_full_unavailable_is_not_silently_changed_to_another_country(self):
        with self.assertRaises(ValueError):
            routing.route_parameters(self.state, "full", [tunnel("US", "US")])

    def test_invalid_or_unconfigured_mode_is_rejected(self):
        for mode, state in [("made-up", self.state), ("full", {"dpnMode": "smart"})]:
            with self.assertRaises(ValueError):
                routing.route_parameters(state, mode, [])
