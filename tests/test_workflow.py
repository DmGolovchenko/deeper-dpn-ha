"""Coordinator logic with minimal HA stand-ins; does not validate HA platform loading."""
import asyncio
from copy import deepcopy
import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from test_core import PACKAGE, api_module, tunnel


class HomeAssistantError(Exception):
    pass


class ConfigEntryAuthFailed(HomeAssistantError):
    pass


class UpdateFailed(HomeAssistantError):
    pass


class DataUpdateCoordinator:
    def __init__(self, hass, logger, **kwargs):
        self.hass, self.data = hass, None

    def async_set_updated_data(self, data):
        self.data = data

    def async_set_update_error(self, error):
        self.last_error = error

    async def async_request_refresh(self):
        self.data = await self._async_update_data()


for name in ("homeassistant", "homeassistant.helpers", "homeassistant.exceptions", "homeassistant.helpers.update_coordinator"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed = ConfigEntryAuthFailed
sys.modules["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = DataUpdateCoordinator
sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed = UpdateFailed
coordinator_module = importlib.import_module(f"{PACKAGE}.coordinator")


class FakeApi:
    profile = {}

    def __init__(self):
        self.state = {"tunnels": [tunnel("old", "SE")], "apps": [{"app": "telegram", "tunnel": "old"}], "domains": []}
        self.writes = []
        self.closed = False

    async def snapshot(self):
        return deepcopy(self.state)

    async def tunnels(self):
        return deepcopy(self.state["tunnels"])

    async def refresh_tunnel(self, code):
        self.writes.append(("refresh", code))

    async def set_app(self, app, code):
        self.writes.append(("app", app, code))
        next(a for a in self.state["apps"] if a["app"] == app)["tunnel"] = code

    async def set_domain(self, name, old, new):
        self.writes.append(("domain", name, old, new))
        next(d for d in self.state["domains"] if d["domainName"] == name)["tunnelCode"] = new

    async def add_domain(self, name, target):
        self.writes.append(("add_domain", name, target))
        self.state["domains"].append({"domainName": name, "tunnelCode": target})

    async def info(self, endpoint):
        return {"tempInCelsius": 48.75}

    async def telemetry(self, initial=None):
        return {}, []

    async def routing(self):
        return {"dpnMode": "smart", "tunnelCode": "old", "smartTunnel": "old", "fullTunnel": "old"}

    async def set_routing(self, mode, code):
        self.writes.append(("routing", mode, code))

    async def reboot(self):
        self.writes.append(("reboot",))

    async def close(self):
        self.closed = True


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api = FakeApi()
        self.entry = types.SimpleNamespace(options={}, entry_id="entry", async_start_reauth=lambda hass: None,
                                           async_create_task=lambda hass, coroutine, name: asyncio.create_task(coroutine))
        self.coordinator = coordinator_module.DeeperCoordinator(types.SimpleNamespace(), self.entry, self.api)

    async def test_repair_reads_rules_after_wait(self):
        async def delay(seconds):
            self.assertEqual(seconds, 60)
            self.api.state["tunnels"] = [tunnel("new", "TR")]
            self.api.state["apps"] = [{"app": "telegram", "tunnel": "ZZ"}, {"app": "instagram", "tunnel": "old"}]
            self.api.state["domains"] = [{"domainName": "changed.example", "tunnelCode": "LL"}, {"domainName": "old.example", "tunnelCode": "old"}]
        with patch.object(coordinator_module.asyncio, "sleep", delay):
            await self.coordinator.refresh_all()
        self.assertEqual(self.api.writes, [("refresh", "old"), ("app", "instagram", "new"), ("domain", "old.example", "old", "new")])
        self.assertEqual(self.coordinator.jobs, set())

    async def test_refresh_without_repair(self):
        with patch.object(coordinator_module.asyncio, "sleep", AsyncMock()):
            await self.coordinator.refresh_all(repair=False)
        self.assertEqual(self.api.writes, [("refresh", "old")])

    async def test_turn_off_with_no_available_tunnels(self):
        self.api.state["tunnels"] = []
        await self.coordinator.set_app("telegram", enabled=False)
        self.assertEqual(self.api.writes, [("app", "telegram", "ZZ")])

    async def test_enable_with_no_tunnels_reports_failure(self):
        self.api.state["tunnels"] = []
        with self.assertRaises(HomeAssistantError):
            await self.coordinator.set_app("telegram", enabled=True)
        self.assertEqual(self.api.writes, [])

    async def test_overlapping_refresh_rejected(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def delay(seconds):
            started.set()
            await release.wait()
        with patch.object(coordinator_module.asyncio, "sleep", delay):
            job = asyncio.create_task(self.coordinator.refresh_all())
            await started.wait()
            with self.assertRaises(HomeAssistantError):
                await self.coordinator.refresh_all()
            release.set()
            await job
        self.assertEqual(self.api.writes, [("refresh", "old")])

    async def test_unload_cancels_pending_repair(self):
        started = asyncio.Event()
        async def delay(seconds):
            started.set()
            await asyncio.Event().wait()
        with patch.object(coordinator_module.asyncio, "sleep", delay):
            job = asyncio.create_task(self.coordinator.refresh_all())
            await started.wait()
            await self.coordinator.shutdown()
            self.assertTrue(job.cancelled())
        self.assertTrue(self.api.closed)
        self.assertEqual(self.coordinator.jobs, set())
        self.assertEqual(self.api.writes, [("refresh", "old")])

    async def test_optional_info_failure_does_not_break_routes(self):
        self.api.info = AsyncMock(side_effect=api_module.DeeperError("Unsupported"))
        data = await self.coordinator._async_update_data()
        self.assertEqual(data["apps"], self.api.state["apps"])
        self.assertIsNone(data["telemetry"]["temperature"])

    async def test_auth_failure_requests_reauth(self):
        self.api.snapshot = AsyncMock(side_effect=api_module.DeeperAuthError())
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.coordinator._async_update_data()


    async def test_full_routing_uses_configured_full_tunnel(self):
        await self.coordinator.set_routing_mode("full")
        self.assertEqual(self.api.writes, [("routing", "full", "old")])

    async def test_direct_mode_is_available_without_active_tunnels(self):
        self.api.state["tunnels"] = []
        await self.coordinator.set_routing_mode("disabled")
        self.assertEqual(self.api.writes, [("routing", "disabled", "old")])

    async def test_reboot_marks_device_temporarily_unavailable(self):
        await self.coordinator.reboot()
        self.assertEqual(self.api.writes, [("reboot",)])
        self.assertIsInstance(self.coordinator.last_error, UpdateFailed)

    async def test_reboot_cancels_pending_route_repairs(self):
        started = asyncio.Event()
        async def delay(seconds):
            started.set()
            await asyncio.Event().wait()
        with patch.object(coordinator_module.asyncio, "sleep", delay):
            job = asyncio.create_task(self.coordinator.refresh_all())
            await started.wait()
            await self.coordinator.reboot()
            self.assertTrue(job.cancelled())
        self.assertEqual(self.api.writes, [("refresh", "old"), ("reboot",)])
