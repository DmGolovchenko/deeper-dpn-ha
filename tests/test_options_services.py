"""Options form workflows using HA stand-ins; actual frontend rendering is not tested."""
import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from test_core import PACKAGE, tunnel
import test_workflow


class FlowBase:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_show_menu(self, **kwargs):
        return {"type": "menu", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}


class FakeSelector:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        return value


config_entries = ModuleType("homeassistant.config_entries")
config_entries.ConfigFlow = FlowBase
config_entries.OptionsFlow = FlowBase
sys.modules[config_entries.__name__] = config_entries
sys.modules["homeassistant"].config_entries = config_entries
core = ModuleType("homeassistant.core")
core.callback = lambda fn: fn
sys.modules[core.__name__] = core
selectors = ModuleType("homeassistant.helpers.selector")
selectors.SelectSelector = selectors.TextSelector = FakeSelector
selectors.SelectSelectorConfig = selectors.TextSelectorConfig = dict
selectors.SelectSelectorMode = SimpleNamespace(DROPDOWN="dropdown")
selectors.TextSelectorType = SimpleNamespace(PASSWORD="password")
sys.modules[selectors.__name__] = selectors
sys.modules["homeassistant.helpers"].selector = selectors
flow_module = importlib.import_module(f"{PACKAGE}.config_flow")


class ServiceOptionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.snapshot = {"apps": [{"app": "spotify", "tunnel": "ZZ"}],
                         "tunnels": [tunnel("SE", "SE")], "domains": []}
        self.coordinator = SimpleNamespace(operation_lock=asyncio.Lock(),
            api=SimpleNamespace(snapshot=AsyncMock(return_value=self.snapshot)),
            set_app=AsyncMock(), configure_domains=AsyncMock())
        self.options = {"auto_refresh": False, "scan_interval": 90, "custom_services": []}
        self.flow = flow_module.DeeperOptionsFlow()
        self.flow.config_entry = SimpleNamespace(options=self.options, runtime_data=self.coordinator)
        self.flow.hass = SimpleNamespace(config=SimpleNamespace(language="ru"))

    async def test_menu_contains_forms_and_settings(self):
        result = await self.flow.async_step_init()
        self.assertEqual(result["menu_options"], ["settings", "application", "custom_service"])

    async def test_application_form_applies_route_and_preserves_other_options(self):
        result = await self.flow.async_step_application({"application": "spotify", "tunnel": "SE"})
        self.coordinator.set_app.assert_awaited_once_with("spotify", code="SE")
        self.assertEqual(result["type"], "create_entry")
        self.assertIn("spotify", result["data"]["selected_apps"])
        self.assertEqual(result["data"]["scan_interval"], 90)
        self.assertFalse(result["data"]["auto_refresh"])
        self.assertNotIn("auto_refresh_confirmed", result["data"])

    async def test_missing_catalog_application_is_not_added(self):
        result = await self.flow.async_step_application({"application": "invented", "tunnel": "SE"})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "application_missing"})
        self.coordinator.set_app.assert_not_awaited()

    async def test_custom_service_form_creates_profile_and_applies_domains(self):
        result = await self.flow.async_step_custom_service({"name": " My service ", "domains": "A.example\ncdn.example", "tunnel": "SE"})
        self.coordinator.configure_domains.assert_awaited_once_with(["a.example", "cdn.example"], "SE")
        profile = result["data"]["custom_services"][0]
        self.assertEqual(profile["name"], "My service")
        self.assertEqual(profile["domains"], ["a.example", "cdn.example"])
        self.assertEqual(len(profile["id"]), 32)
        self.assertEqual(result["data"]["scan_interval"], 90)

    async def test_invalid_domains_cause_no_write(self):
        result = await self.flow.async_step_custom_service({"name": "My service", "domains": "https://a.example", "tunnel": "SE"})
        self.assertEqual(result["errors"], {"domains": "invalid_domains"})
        self.coordinator.configure_domains.assert_not_awaited()

    async def test_duplicate_service_and_overlapping_domains_cause_no_write(self):
        self.options["custom_services"] = [{"id": "existing", "name": "My service", "domains": ["a.example"]}]
        result = await self.flow.async_step_custom_service({"name": "MY SERVICE", "domains": "a.example", "tunnel": "SE"})
        self.assertEqual(result["errors"], {"name": "name_exists", "domains": "domain_in_use"})
        self.coordinator.configure_domains.assert_not_awaited()
