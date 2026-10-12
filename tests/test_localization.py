"""Localized route labels must preserve API codes and retain translation coverage."""
import importlib
import json
from pathlib import Path
import unittest

from test_core import PACKAGE, tunnel

localization = importlib.import_module(f"{PACKAGE}.localization")
routes = importlib.import_module(f"{PACKAGE}.app_routes")


class LocalizationTests(unittest.TestCase):
    def test_russian_modes_preserve_api_values(self):
        self.assertEqual(localization.mode_options("ru"), {"disabled": "Прямая", "smart": "Умная", "full": "Полная"})
        self.assertEqual(localization.mode_options("en"), {"disabled": "Direct", "smart": "Smart", "full": "Full"})

    def test_russian_application_routes_preserve_api_codes(self):
        snapshot = {"apps": [{"app": "instagram", "tunnel": "SE"}],
                    "tunnels": [tunnel("SE", "SE"), tunnel("DE-node", "DE", 0)]}
        choices = routes.app_route_options(snapshot, "instagram", "ru")
        self.assertEqual(choices["Прямое подключение"], "LL")
        self.assertEqual(choices["Общая маршрутизация"], "ZZ")
        self.assertEqual(choices["Швеция (SE)"], "SE")
        self.assertNotIn("DE-node", choices.values())

    def test_russian_offline_route_remains_visible(self):
        snapshot = {"apps": [{"app": "telegram", "tunnel": "TR"}], "tunnels": [tunnel("TR", "TR", 0)]}
        self.assertEqual(routes.app_route_options(snapshot, "telegram", "ru")["Турция (TR) — недоступен"], "TR")

    def test_language_variant_and_fallback(self):
        self.assertEqual(localization.text("direct", "ru-RU"), "Прямое подключение")
        self.assertEqual(localization.text("direct", "de"), "Direct connection")
        self.assertEqual(localization.text("XY", "ru", "XY"), "XY")

    def test_entity_names_have_matching_translation_coverage(self):
        component = Path(__file__).resolve().parents[1] / "custom_components/deeper_connect"
        en = json.loads((component / "translations/en.json").read_text())
        ru = json.loads((component / "translations/ru.json").read_text())
        for domain, entries in en["entity"].items():
            self.assertEqual(set(entries), set(ru["entity"][domain]))
        self.assertEqual(sum(len(entries) for entries in en["entity"].values()), 18)
        self.assertEqual(en["entity"]["button"]["refresh_all"]["name"], "Refresh and repair tunnels")
        self.assertEqual(ru["entity"]["button"]["refresh_all"]["name"], "Обновить и восстановить туннели")
