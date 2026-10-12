"""Dropdown labels must map to correct API codes and reflect offline routes."""
import importlib
import unittest
from test_core import PACKAGE, tunnel

routes = importlib.import_module(f"{PACKAGE}.app_routes")


def snapshot(current, tunnels):
    return {"apps": [{"app": "instagram", "tunnel": current}], "tunnels": tunnels}


class AppRouteOptionsTests(unittest.TestCase):
    def test_direct_and_general_routing_are_distinct(self):
        choices = routes.app_route_options(snapshot("LL", []), "instagram")
        self.assertEqual(choices, {"Direct connection": "LL", "General routing": "ZZ"})

    def test_country_label_maps_to_actual_tunnel_code(self):
        choices = routes.app_route_options(snapshot("Sweden-node", [tunnel("Sweden-node", "SE")]), "instagram")
        self.assertEqual(choices["Sweden (Sweden-node)"], "Sweden-node")

    def test_inactive_routes_not_offered_except_current(self):
        choices = routes.app_route_options(snapshot("SE", [tunnel("SE", "SE", 0), tunnel("DE", "DE"), tunnel("TR", "TR", 0)]), "instagram")
        self.assertEqual(choices["Sweden (SE) — unavailable"], "SE")
        self.assertEqual(choices["Germany (DE)"], "DE")
        self.assertNotIn("TR", choices.values())

    def test_disappeared_current_tunnel_remains_visible(self):
        choices = routes.app_route_options(snapshot("old-node", []), "instagram")
        self.assertEqual(choices["old-node — unavailable"], "old-node")

    def test_duplicate_country_does_not_hide_different_tunnel_codes(self):
        choices = routes.app_route_options(snapshot("SE-one", [tunnel("SE-one", "SE"), tunnel("SE-two", "SE")]), "instagram")
        self.assertEqual(choices["Sweden (SE-one)"], "SE-one")
        self.assertEqual(choices["Sweden (SE-two)"], "SE-two")

    def test_missing_app_still_has_valid_choices_without_fake_current_route(self):
        choices = routes.app_route_options({"apps": [], "tunnels": []}, "instagram")
        self.assertEqual(set(choices.values()), {"LL", "ZZ"})
