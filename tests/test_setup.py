"""Verify timer registration using HA stand-ins; no actual HA runtime."""
from datetime import timedelta
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_core import PACKAGE
import test_workflow  # Provides the coordinator's minimal Home Assistant interfaces.

registry_module = ModuleType("homeassistant.helpers.entity_registry")
registry_module.async_get = Mock()
registry_module.async_entries_for_config_entry = Mock(return_value=[])
sys.modules[registry_module.__name__] = registry_module
sys.modules["homeassistant.helpers"].entity_registry = registry_module
event_module = ModuleType("homeassistant.helpers.event")
event_module.async_track_time_interval = Mock(return_value=lambda: None)
sys.modules[event_module.__name__] = event_module
path = Path(__file__).resolve().parents[1] / "custom_components/deeper_connect/__init__.py"
setup = ModuleType(f"{PACKAGE}.integration_setup")
setup.__package__ = PACKAGE
exec(compile(path.read_text(), str(path), "exec"), setup.__dict__)


class SetupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = SimpleNamespace(config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()))
        self.entry = SimpleNamespace(entry_id="entry", options={},
            data={"base_url": "http://127.0.0.1/api", "username": "test", "password": "synthetic-ciphertext"},
            async_on_unload=Mock(), add_update_listener=Mock())
        self.coordinator = SimpleNamespace(async_config_entry_first_refresh=AsyncMock(), refresh_all=AsyncMock())
        event_module.async_track_time_interval.reset_mock()
        registry_module.async_entries_for_config_entry.return_value = []

    async def run_setup(self):
        with patch.object(setup, "DeeperCoordinator", return_value=self.coordinator), patch.object(setup, "DeeperApi", return_value=SimpleNamespace(close=AsyncMock())):
            self.assertTrue(await setup.async_setup_entry(self.hass, self.entry))

    async def test_default_does_not_start_automatic_repairs(self):
        await self.run_setup()
        event_module.async_track_time_interval.assert_not_called()
        self.coordinator.refresh_all.assert_not_awaited()
        self.hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(self.entry, ["button", "select", "sensor", "update"])

    async def test_confirmed_enabled_schedule_uses_minutes(self):
        self.entry.options = {"auto_refresh": True, "auto_refresh_confirmed": True, "refresh_interval_minutes": 240}
        await self.run_setup()
        args = event_module.async_track_time_interval.call_args.args
        self.assertEqual(args[2], timedelta(hours=4))
        self.coordinator.refresh_all.assert_not_awaited()
        await args[1](None)
        self.coordinator.refresh_all.assert_awaited_once_with()

    async def test_one_hour_option_registers_hourly_timer(self):
        self.entry.options = {"auto_refresh": True, "auto_refresh_confirmed": True, "refresh_interval_minutes": 60}
        await self.run_setup()
        args = event_module.async_track_time_interval.call_args.args
        self.assertEqual(args[2], timedelta(hours=1))
        await args[1](None)
        self.coordinator.refresh_all.assert_awaited_once_with()

    async def test_cleanup_keeps_requested_entities_and_removes_own_obsolete_entry(self):
        records = [SimpleNamespace(entity_id="sensor.retained", config_entry_id="entry", platform="deeper_connect", unique_id="entry_temperature"),
                   SimpleNamespace(entity_id="select.retained", config_entry_id="entry", platform="deeper_connect", unique_id="entry_app_youtube_route"),
                   SimpleNamespace(entity_id="button.obsolete", config_entry_id="entry", platform="deeper_connect", unique_id="entry_app_youtube_direct"),
                   SimpleNamespace(entity_id="select.foreign", config_entry_id="foreign", platform="deeper_connect", unique_id="foreign_app_youtube_route")]
        registry = SimpleNamespace(async_remove=Mock())
        registry_module.async_get.return_value = registry
        registry_module.async_entries_for_config_entry.return_value = records
        await self.run_setup()
        registry.async_remove.assert_called_once_with("button.obsolete")


    async def test_upgrade_disables_legacy_automatic_schedule(self):
        self.entry.options = {"auto_refresh": True, "refresh_interval_hours": 1}
        await self.run_setup()
        event_module.async_track_time_interval.assert_not_called()

    async def test_short_user_selected_interval(self):
        self.entry.options = {"auto_refresh": True, "auto_refresh_confirmed": True, "refresh_interval_minutes": 15}
        await self.run_setup()
        self.assertEqual(event_module.async_track_time_interval.call_args.args[2], timedelta(minutes=15))
