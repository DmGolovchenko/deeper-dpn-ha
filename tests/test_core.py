"""Routing policy and HTTP behavior tested without a Home Assistant installation."""
import asyncio
import importlib
from pathlib import Path
import sys
import types
import unittest

from aiohttp import web

PACKAGE = "deeper_test_component"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components" / "deeper_connect")]
sys.modules[PACKAGE] = package
api_module = importlib.import_module(f"{PACKAGE}.api")
policy = importlib.import_module(f"{PACKAGE}.policy")
telemetry = importlib.import_module(f"{PACKAGE}.telemetry")


def tunnel(code, country, count=1):
    return {"tunnelCode": code, "countryCode": country, "activeNum": count}


class PolicyTests(unittest.TestCase):
    def test_country_is_not_tunnel_code(self):
        tunnels = [tunnel("tunnel-tr", "TR"), tunnel("tunnel-se", "SE")]
        self.assertEqual(policy.choose_tunnel(tunnels, "telegram"), "tunnel-tr")
        self.assertEqual(policy.choose_tunnel(tunnels, "instagram"), "tunnel-se")

    def test_empty_and_inactive(self):
        for tunnels in ([], [tunnel("SE", "SE", 0)]):
            with self.assertRaises(ValueError):
                policy.choose_tunnel(tunnels)

    def test_global_priority(self):
        self.assertEqual(policy.choose_tunnel([tunnel("US", "US"), tunnel("DE", "DE")]), "DE")

    def test_repair_preserves_ignored_apps_and_special_modes(self):
        snapshot = {"tunnels": [tunnel("new", "SE")], "apps": [
            {"app": "youtube", "tunnel": "old"}, {"app": "plex", "tunnel": "old"},
            {"app": "netflix", "tunnel": "old"}, {"app": "direct", "tunnel": "LL"},
            {"app": "unassigned", "tunnel": "ZZ"}, {"app": "working", "tunnel": "new"},
            {"app": "telegram", "tunnel": "old"}], "domains": [
            {"domainName": "direct.example", "tunnelCode": "LL"},
            {"domainName": "unassigned.example", "tunnelCode": "ZZ"},
            {"domainName": "broken.example", "tunnelCode": "old"}]}
        apps, domains = policy.repair_plan(snapshot)
        self.assertEqual(apps, [("telegram", "new")])
        self.assertEqual(domains, [("broken.example", "old", "new")])
        snapshot["tunnels"] = []
        self.assertEqual(policy.repair_plan(snapshot), ([], []))


class TelemetryTests(unittest.TestCase):
    def test_hardware_temperature(self):
        self.assertEqual(telemetry.extract_value({"tempInCelsius": 48.75}, {"path": ["tempInCelsius"]}, "temperature"), 48.75)

    def test_scaled_cpu_and_nested_path(self):
        spec = {"endpoint": "/confirmed", "path": ["data", 0, "cpu"], "scale": 100}
        self.assertEqual(telemetry.extract_value({"data": [{"cpu": 0.23}]}, spec, "cpu_usage"), 23)
        self.assertEqual(telemetry.validate_profile({"cpu_usage": spec}), {"cpu_usage": spec})

    def test_missing_and_nonfinite_are_unknown(self):
        for payload in ({}, {"cpu": None}, {"cpu": "unknown"}, {"cpu": "NaN"}):
            self.assertIsNone(telemetry.extract_value(payload, {"path": ["cpu"]}, "cpu_usage"))

    def test_external_and_ambiguous_paths_rejected(self):
        for endpoint in ("https://example.com", "//example.com/path", "/../x", "/%2e%2e/x", "/x#fragment", "/x\\y"):
            with self.assertRaises(ValueError):
                telemetry.validate_profile({"cpu_usage": {"endpoint": endpoint, "path": ["cpu"]}})

    def test_unknown_mapping_fields_rejected(self):
        with self.assertRaises(ValueError):
            telemetry.validate_profile({"made_up": {"endpoint": "/x", "path": []}})
        with self.assertRaises(ValueError):
            telemetry.validate_profile({"cpu_usage": {"endpoint": "/x", "path": "cpu"}})


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.logins = 0
        self.login_payloads = []
        self.reject_login = False
        self.cookies = []
        self.writes = []
        self.page_requests = []
        self.expire = False
        self.fail_mutation = False
        self.invalid_apps = False
        self.invalid_json = False
        self.routing_state = {"dpnMode": "smart", "tunnelCode": "US", "smartTunnel": "US", "fullTunnel": "SE"}
        self.reboot_behavior = "success"
        app = web.Application()
        app.router.add_route("*", "/api/{tail:.*}", self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.client = api_module.DeeperApi(f"http://127.0.0.1:{port}/api", "test", "test")

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()

    async def handle(self, request):
        path = request.match_info["tail"]
        if path == "admin/login":
            self.login_payloads.append(await request.json())
            self.logins += 1
            result = web.json_response({"success": not self.reject_login})
            result.set_cookie("session", str(self.logins))
            return result
        if self.expire:
            self.expire = False
            return web.json_response({}, status=401)
        self.cookies.append(request.cookies.get("session"))
        if request.cookies.get("session") != str(self.logins):
            return web.json_response({}, status=401)
        if path == "smartRoute/getDpnMode":
            return web.json_response(self.routing_state)
        if path == "smartRoute/setDpnMode":
            payload = await request.json()
            self.writes.append((path, payload))
            if not self.fail_mutation:
                self.routing_state.update(payload)
            return web.json_response({"success": not self.fail_mutation})
        if path == "admin/reboot":
            self.writes.append((path, None))
            if self.reboot_behavior == "disconnect":
                request.transport.close()
                return web.Response()
            if self.reboot_behavior == "reject":
                return web.json_response({"success": False})
            if self.reboot_behavior == "unauthorized":
                return web.Response(status=401)
            return web.Response(status=200)
        if path == "smartRoute/listTunnels":
            if self.invalid_json:
                return web.Response(text="<html>login</html>")
            return web.json_response([tunnel("SE", "SE")])
        if path == "appRelocator/apps":
            if self.invalid_apps:
                return web.json_response({"wrong": "shape"})
            return web.json_response([{"category": "allCategories", "appsBySubcategory": [{"subcategory": "allCountries", "apps": [{"app": "youtube", "tunnel": "ZZ"}]}]}])
        if path == "smartRoute/getRoutingWhitelist/domain":
            page = int(request.query["pageNo"])
            self.page_requests.append(page)
            count = 100 if page == 1 else 2
            return web.json_response({"list": [{"domainName": f"{page}-{i}.example", "tunnelCode": "SE"} for i in range(count)]})
        if path == "system-info/hardware-info":
            return web.json_response({"tempInCelsius": 48.75, "cpuCount": 4, "totalMem": 2074693632})
        if path == "system-info/get-latestversion":
            return web.json_response({"latestVersion": "2.0.6.h3", "currentVersion": "2.0.6.h2"})
        if path == "system-info/software-info":
            return web.json_response({"softwareVersion": "2.0.6.h2", "appSigVersion": "20260412"})
        if path == "confirmed-metrics":
            return web.json_response({"cpu": 0.25, "ram": 30})
        if path == "redirect":
            return web.Response(status=302, headers={"Location": "/api/confirmed-metrics"})
        if request.method == "POST":
            self.writes.append((path, await request.json()))
            return web.json_response({"success": not self.fail_mutation})
        return web.json_response({}, status=404)

    async def test_cookie_auth_on_ip_and_paginated_snapshot(self):
        snapshot = await self.client.snapshot()
        self.assertEqual(len(snapshot["domains"]), 102)
        self.assertEqual(self.page_requests, [1, 2])
        self.assertEqual(self.logins, 1)
        self.assertEqual(set(self.cookies), {"1"})

    async def test_session_expiration_reauthenticates_once(self):
        await self.client.tunnels()
        self.expire = True
        await self.client.tunnels()
        self.assertEqual(self.logins, 2)

    async def test_encrypted_password_sent_verbatim_on_login_and_reauth(self):
        # Synthetic opaque test value, not a user credential.
        encrypted = "dGVzdC9jaXBoZXJ0ZXh0K3ZhbHVlPQ=="
        self.client.password = encrypted
        await self.client.tunnels()
        self.expire = True
        await self.client.tunnels()
        self.assertEqual(self.login_payloads, [
            {"username": "test", "password": encrypted},
            {"username": "test", "password": encrypted},
        ])

    async def test_login_failure_stops_before_writes(self):
        self.reject_login = True
        with self.assertRaises(api_module.DeeperAuthError):
            await self.client.set_app("youtube", "SE")
        self.assertEqual(self.writes, [])

    async def test_disabled_and_direct_modes(self):
        await self.client.set_app("youtube", "ZZ")
        await self.client.set_app("youtube", "LL")
        self.assertEqual(self.writes, [("appRelocator/delApp", {"appName": "youtube", "tunnelCode": "ZZ"}), ("appRelocator/addApp", {"appName": "youtube", "tunnelCode": "LL"})])

    async def test_mutation_failure_is_not_success(self):
        self.fail_mutation = True
        with self.assertRaises(api_module.DeeperError):
            await self.client.refresh_tunnel("SE")
        self.assertEqual(len(self.writes), 1)

    async def test_malformed_apps_and_html_rejected(self):
        self.invalid_apps = True
        with self.assertRaises(api_module.DeeperError):
            await self.client.apps()
        self.invalid_json = True
        with self.assertRaises(api_module.DeeperError):
            await self.client.tunnels()

    async def test_metric_endpoint_deduplicated_and_failure_isolated(self):
        self.client.profile = telemetry.validate_profile({
            "cpu_usage": {"endpoint": "/confirmed-metrics", "path": ["cpu"], "scale": 100},
            "memory_usage": {"endpoint": "/confirmed-metrics", "path": ["ram"]},
            "latest_version": {"endpoint": "/missing", "path": ["version"]}})
        values, errors = await self.client.telemetry()
        self.assertEqual(values, {"cpu_usage": 25, "memory_usage": 30, "latest_version": None})
        self.assertEqual(errors, ["latest_version"])
        self.assertEqual(len(self.cookies), 2)

    async def test_redirect_is_not_followed(self):
        with self.assertRaises(api_module.DeeperError):
            await self.client.request("GET", "/redirect")
        self.assertEqual(len(self.cookies), 1)

    async def test_hardware(self):
        self.assertEqual((await self.client.hardware())["tempInCelsius"], 48.75)

    async def test_confirmed_versions_and_check_cache(self):
        values, errors = await self.client.telemetry()
        self.assertEqual(values, {"installed_version": "2.0.6.h2", "latest_version": "2.0.6.h3"})
        self.assertEqual(errors, [])
        self.assertEqual(len(self.cookies), 2)
        await self.client.telemetry()
        self.assertEqual(len(self.cookies), 3)
        self.client.invalidate_version_check()
        await self.client.telemetry()
        self.assertEqual(len(self.cookies), 5)

    async def test_routing_state_and_full_mode_payload(self):
        self.assertEqual((await self.client.routing())["fullTunnel"], "SE")
        await self.client.set_routing("full", "SE")
        self.assertEqual(self.writes, [("smartRoute/setDpnMode", {"dpnMode": "full", "tunnelCode": "SE"})])
        self.assertEqual((await self.client.routing())["dpnMode"], "full")

    async def test_routing_rejection_does_not_report_success(self):
        self.fail_mutation = True
        with self.assertRaises(api_module.DeeperError):
            await self.client.set_routing("disabled", "US")
        self.assertEqual(self.routing_state["dpnMode"], "smart")

    async def test_reboot_empty_success_response_is_valid(self):
        await self.client.reboot()
        self.assertEqual(self.writes, [("admin/reboot", None)])
        self.assertFalse(self.client._authenticated)

    async def test_reboot_rejection_is_reported(self):
        self.reboot_behavior = "reject"
        with self.assertRaises(api_module.DeeperError):
            await self.client.reboot()
        self.assertEqual(len(self.writes), 1)

    async def test_reboot_disconnect_is_uncertain_and_not_retried(self):
        self.reboot_behavior = "disconnect"
        with self.assertRaises(api_module.DeeperCommandUncertain):
            await self.client.reboot()
        self.assertEqual(self.writes, [("admin/reboot", None)])

    async def test_reboot_unauthorized_is_not_replayed(self):
        self.reboot_behavior = "unauthorized"
        with self.assertRaises(api_module.DeeperAuthError):
            await self.client.reboot()
        self.assertEqual(self.logins, 1)
        self.assertEqual(len(self.writes), 1)

    async def test_add_custom_domain_uses_whitelist_endpoint(self):
        await self.client.add_domain("example.org", "SE")
        self.assertEqual(self.writes, [("smartRoute/addToWhitelist/domain", {"domainName": "example.org", "tunnelCode": "SE"})])

    async def test_concurrent_requests_login_once(self):
        await asyncio.gather(*(self.client.tunnels() for _ in range(8)))
        self.assertEqual(self.logins, 1)


if __name__ == "__main__":
    unittest.main()
