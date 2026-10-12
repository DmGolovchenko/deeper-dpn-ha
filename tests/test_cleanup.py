"""Obsolete entity cleanup must never affect retained or foreign entities."""
import importlib
from types import SimpleNamespace
import unittest

from test_core import PACKAGE

cleanup = importlib.import_module(f"{PACKAGE}.cleanup")
const = importlib.import_module(f"{PACKAGE}.const")


def entity(key, entry_id="entry", platform="deeper_connect", unique_id=None):
    return SimpleNamespace(config_entry_id=entry_id, platform=platform,
                           unique_id=unique_id if unique_id is not None else f"{entry_id}_{key}")


class CleanupTests(unittest.TestCase):
    def test_retained_entities_are_preserved(self):
        for key in const.ENTITY_KEYS:
            with self.subTest(key=key):
                self.assertFalse(cleanup.is_obsolete_entity(entity(key), "entry"))

    def test_removed_app_tunnel_and_network_entities_are_obsolete(self):
        for key in ["app_netflix_route", "app_youtube_direct", "app_youtube_change", "app_telegram_dpn", "tunnel_SE_ips",
                    "tunnel_SE_refresh", "network_pubIp", "software_appSigVersion",
                    "cpu_usage", "memory_usage", "poll"]:
            with self.subTest(key=key):
                self.assertTrue(cleanup.is_obsolete_entity(entity(key), "entry"))

    def test_other_config_entry_is_preserved(self):
        self.assertFalse(cleanup.is_obsolete_entity(entity("poll", entry_id="other"), "entry"))

    def test_foreign_platform_is_preserved(self):
        self.assertFalse(cleanup.is_obsolete_entity(entity("poll", platform="other"), "entry"))

    def test_foreign_unique_id_is_preserved(self):
        self.assertFalse(cleanup.is_obsolete_entity(entity("poll", unique_id="other_poll"), "entry"))
