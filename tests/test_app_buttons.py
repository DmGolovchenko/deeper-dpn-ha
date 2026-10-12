"""Manual app routing: cycle active countries, preserve special modes in auto repair."""
import importlib
import unittest

from test_core import PACKAGE, tunnel
import test_workflow as workflow

policy = importlib.import_module(f"{PACKAGE}.policy")


class AppCycleTests(unittest.TestCase):
    def test_cycle_wraps_instead_of_alternating_only_top_two(self):
        tunnels = [tunnel("US", "US"), tunnel("DE", "DE"), tunnel("SE", "SE")]
        self.assertEqual(policy.next_app_tunnel(tunnels, "youtube", "SE"), "DE")
        self.assertEqual(policy.next_app_tunnel(tunnels, "youtube", "DE"), "US")
        self.assertEqual(policy.next_app_tunnel(tunnels, "youtube", "US"), "SE")

    def test_enable_from_direct_or_general_routing_selects_preferred_route(self):
        tunnels = [tunnel("SE-id", "SE"), tunnel("TR-id", "TR")]
        self.assertEqual(policy.next_app_tunnel(tunnels, "telegram", "LL"), "TR-id")
        self.assertEqual(policy.next_app_tunnel(tunnels, "instagram", "ZZ"), "SE-id")

    def test_inactive_routes_are_never_selected(self):
        self.assertEqual(policy.next_app_tunnel([tunnel("SE", "SE", 0), tunnel("DE", "DE")], "whatsapp", "LL"), "DE")

    def test_single_current_route_and_empty_list_fail(self):
        for tunnels in ([], [tunnel("SE", "SE")], [tunnel("SE", "SE"), tunnel("SE", "SE")]):
            with self.assertRaises(ValueError):
                policy.next_app_tunnel(tunnels, "youtube", "SE")


class AppActionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = workflow.WorkflowTests.asyncSetUp

    async def test_disable_routes_direct_even_with_no_active_tunnels(self):
        self.api.state["tunnels"] = []
        self.api.state["apps"] = [{"app": "youtube", "tunnel": "old"}]
        await self.coordinator.set_app("youtube", code="LL")
        self.assertEqual(self.api.writes, [("app", "youtube", "LL")])

    async def test_manual_youtube_change_is_not_blocked_by_auto_ignore_list(self):
        self.api.state["apps"] = [{"app": "youtube", "tunnel": "old"}]
        self.api.state["tunnels"] += [tunnel("new", "DE")]
        await self.coordinator.change_app_tunnel("youtube")
        self.assertEqual(self.api.writes, [("app", "youtube", "new")])

    async def test_change_rechecks_device_state_instead_of_cached_route(self):
        self.coordinator.data = {"apps": [{"app": "telegram", "tunnel": "old"}]}
        self.api.state["apps"] = [{"app": "telegram", "tunnel": "new"}]
        self.api.state["tunnels"] += [tunnel("new", "DE")]
        await self.coordinator.change_app_tunnel("telegram")
        self.assertEqual(self.api.writes, [("app", "telegram", "old")])

    async def test_missing_app_does_not_send_a_write(self):
        with self.assertRaises(workflow.HomeAssistantError):
            await self.coordinator.change_app_tunnel("whatsapp")
        self.assertEqual(self.api.writes, [])
