"""User-managed service configuration and domain rules."""
import importlib
from types import SimpleNamespace
import unittest

from test_core import PACKAGE
import test_workflow as workflow

services = importlib.import_module(f"{PACKAGE}.services_config")
cleanup = importlib.import_module(f"{PACKAGE}.cleanup")


class ServiceConfigTests(unittest.TestCase):
    def test_domains_normalized_deduplicated_and_idna_encoded(self):
        self.assertEqual(services.parse_domains("Example.ORG, cdn.example.org\nexample.org; пример.рф"),
                         ["example.org", "cdn.example.org", "xn--e1afmkfd.xn--p1ai"])

    def test_invalid_domains_are_rejected_before_any_writes(self):
        for value in ("", "https://example.org", "example.org/path", "*.example.org", "127.0.0.1", "example.org:80", "-bad.example", "localhost"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                services.parse_domains(value)

    def test_only_changed_and_missing_domains_are_written(self):
        snapshot = {"domains": [{"domainName": "a.example", "tunnelCode": "SE"}, {"domainName": "b.example", "tunnelCode": "US"}]}
        self.assertEqual(services.domain_plan(snapshot, ["a.example", "b.example", "c.example"], "SE"),
                         [("b.example", "US", "SE"), ("c.example", None, "SE")])

    def test_custom_service_route_handles_partial_and_mixed_rules(self):
        service = {"domains": ["a.example", "b.example"]}
        self.assertIsNone(services.custom_current_route({"domains": []}, service))
        snapshot = {"domains": [{"domainName": "a.example", "tunnelCode": "SE"}]}
        self.assertEqual(services.custom_current_route(snapshot, service), "__mixed__")
        snapshot["domains"].append({"domainName": "b.example", "tunnelCode": "SE"})
        self.assertEqual(services.custom_current_route(snapshot, service), "SE")

    def test_selected_apps_and_custom_services_survive_cleanup(self):
        options = {"selected_apps": ["youtube", "spotify", "spotify"],
                   "custom_services": [{"id": "custom-id", "name": "My service", "domains": ["a.example"]}]}
        self.assertEqual(services.selected_apps(options), ["youtube", "spotify"])
        keys = services.configured_entity_keys(options)
        self.assertNotIn("app_instagram_route", keys)
        for key in ("app_youtube_route", "app_spotify_route", "custom_custom-id_route", "refresh_all"):
            self.assertIn(key, keys)
            entity = SimpleNamespace(platform="deeper_connect", config_entry_id="entry", unique_id=f"entry_{key}")
            self.assertFalse(cleanup.is_obsolete_entity(entity, "entry", keys))


class CustomDomainActionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = workflow.WorkflowTests.asyncSetUp

    async def test_create_and_update_domains_with_one_service(self):
        self.api.state["domains"] = [{"domainName": "existing.example", "tunnelCode": "old"}]
        await self.coordinator.configure_domains(["existing.example", "new.example"], "LL")
        self.assertEqual(self.api.writes, [("domain", "existing.example", "old", "LL"), ("add_domain", "new.example", "LL")])
        self.assertEqual({d["tunnelCode"] for d in self.api.state["domains"]}, {"LL"})

    async def test_retry_is_idempotent(self):
        await self.coordinator.configure_domains(["new.example"], "old")
        await self.coordinator.configure_domains(["new.example"], "old")
        self.assertEqual(self.api.writes, [("add_domain", "new.example", "old")])

    async def test_unavailable_route_causes_no_domain_writes(self):
        with self.assertRaises(workflow.HomeAssistantError):
            await self.coordinator.configure_domains(["new.example"], "unavailable")
        self.assertEqual(self.api.writes, [])

    async def test_general_routing_not_supported_for_domain_rule_creation(self):
        with self.assertRaises(workflow.HomeAssistantError):
            await self.coordinator.configure_domains(["new.example"], "ZZ")
        self.assertEqual(self.api.writes, [])
