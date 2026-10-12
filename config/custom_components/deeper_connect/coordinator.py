"""Coordinated polling and serialized routing changes."""
import asyncio
from datetime import timedelta
import logging

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeeperAuthError, DeeperCommandUncertain, DeeperError
from .const import APP_CONTROLS, DIRECT, UNASSIGNED
from .policy import active_tunnels, choose_tunnel, next_app_tunnel, repair_plan
from .routing import route_parameters
from .services_config import domain_plan

_LOGGER = logging.getLogger(__name__)


class DeeperCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        super().__init__(hass, _LOGGER, name="Deeper Connect", config_entry=entry,
                         update_interval=timedelta(seconds=entry.options.get("scan_interval", 60)))
        self.api = api
        self.entry = entry
        self.operation_lock = asyncio.Lock()
        self.refresh_lock = asyncio.Lock()
        self.jobs = set()
        self.stopping = False

    async def _read(self):
        snapshot = await self.api.snapshot()
        responses = {}
        for key, endpoint in {
            "hardware": "/system-info/hardware-info",
            "software": "/system-info/software-info",
        }.items():
            try:
                snapshot[key] = await self.api.info(endpoint)
                responses[endpoint] = snapshot[key]
            except DeeperAuthError:
                raise
            except DeeperError:
                snapshot[key] = {}
                responses[endpoint] = None
        snapshot["telemetry"], snapshot["telemetry_errors"] = await self.api.telemetry(responses)
        if "temperature" not in self.api.profile:
            from .telemetry import extract_value
            snapshot["telemetry"]["temperature"] = extract_value(
                snapshot["hardware"], {"path": ["tempInCelsius"]}, "temperature"
            )
        try:
            snapshot["routing"] = await self.api.routing()
        except DeeperAuthError:
            raise
        except DeeperError:
            snapshot["routing"] = {}
        return snapshot

    async def _async_update_data(self):
        try:
            async with self.operation_lock:
                return await self._read()
        except DeeperAuthError as err:
            raise ConfigEntryAuthFailed("Deeper credentials rejected") from err
        except DeeperError as err:
            raise UpdateFailed(str(err)) from err

    async def _operation(self, operation):
        if self.stopping:
            raise HomeAssistantError("Deeper integration is unloading")
        try:
            async with self.operation_lock:
                await operation()
                self.async_set_updated_data(await self._read())
        except DeeperAuthError as err:
            self.entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Deeper credentials rejected") from err
        except (DeeperError, ValueError) as err:
            # State must be read back after a partially successful operation.
            self.entry.async_create_task(self.hass, self.async_request_refresh(), "Deeper state refresh")
            raise HomeAssistantError(str(err)) from err

    async def set_app(self, app, code=None, enabled=None):
        async def operation():
            snapshot = await self.api.snapshot()
            if app not in {a["app"] for a in snapshot["apps"]}:
                raise ValueError("Application is no longer present")
            target = code
            if enabled is not None:
                target = choose_tunnel(snapshot["tunnels"], app) if enabled else UNASSIGNED
            valid = {t["tunnelCode"] for t in active_tunnels(snapshot["tunnels"])} | {DIRECT, UNASSIGNED}
            if target not in valid:
                raise ValueError("Tunnel is unavailable")
            await self.api.set_app(app, target)
        await self._operation(operation)

    async def change_app_tunnel(self, app):
        async def operation():
            if app not in APP_CONTROLS:
                raise ValueError("Application is not supported by these controls")
            snapshot = await self.api.snapshot()
            rule = next((a for a in snapshot["apps"] if a["app"] == app), None)
            if rule is None:
                raise ValueError("Application is no longer present")
            target = next_app_tunnel(snapshot["tunnels"], app, rule["tunnel"])
            await self.api.set_app(app, target)
        await self._operation(operation)

    async def set_domain(self, name, target):
        async def operation():
            snapshot = await self.api.snapshot()
            domain = next((d for d in snapshot["domains"] if d["domainName"] == name), None)
            if not domain:
                raise ValueError("Domain does not exist in the whitelist")
            valid = {t["tunnelCode"] for t in active_tunnels(snapshot["tunnels"])} | {DIRECT, UNASSIGNED}
            if target not in valid:
                raise ValueError("Tunnel is unavailable")
            await self.api.set_domain(name, domain["tunnelCode"], target)
        await self._operation(operation)

    async def configure_domains(self, domains, target):
        async def operation():
            snapshot = await self.api.snapshot()
            valid = {t["tunnelCode"] for t in active_tunnels(snapshot["tunnels"])} | {DIRECT}
            if target not in valid:
                raise ValueError("Tunnel is unavailable")
            for name, old, new in domain_plan(snapshot, domains, target):
                if old is None:
                    await self.api.add_domain(name, new)
                else:
                    await self.api.set_domain(name, old, new)
        await self._operation(operation)

    async def refresh_one(self, code):
        async def operation():
            if code not in {t["tunnelCode"] for t in await self.api.tunnels()}:
                raise ValueError("Unknown tunnel")
            await self.api.refresh_tunnel(code)
        await self._operation(operation)

    async def set_routing_mode(self, mode):
        async def operation():
            params = route_parameters(await self.api.routing(), mode, await self.api.tunnels())
            await self.api.set_routing(params["dpnMode"], params["tunnelCode"])
        await self._operation(operation)

    async def reboot(self):
        if self.stopping:
            raise HomeAssistantError("Deeper integration is unloading")
        # Do not resume pending route repairs after a user-requested restart.
        jobs = [job for job in self.jobs if job is not asyncio.current_task()]
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        try:
            async with self.operation_lock:
                await self.api.reboot()
                self.async_set_update_error(UpdateFailed("Device is restarting"))
        except DeeperAuthError as err:
            self.entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Deeper credentials rejected") from err
        except DeeperCommandUncertain as err:
            self.async_set_update_error(UpdateFailed("Reboot result is unconfirmed"))
            raise HomeAssistantError(str(err)) from err
        except DeeperError as err:
            raise HomeAssistantError(str(err)) from err

    async def shutdown(self):
        self.stopping = True
        jobs = list(self.jobs)
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        await self.api.close()

    async def refresh_all(self, repair=True):
        if self.stopping:
            raise HomeAssistantError("Deeper integration is unloading")
        task = asyncio.current_task()
        self.jobs.add(task)
        try:
            await self._refresh_all(repair)
        finally:
            self.jobs.discard(task)

    async def _refresh_all(self, repair=True):
        """Refresh, wait for the device, then repair a fresh snapshot of rules."""
        if self.refresh_lock.locked():
            raise HomeAssistantError("Tunnel refresh is already running")
        async with self.refresh_lock:
            async def refresh():
                # Keep the original behavior: refresh tunnels with active IPs.
                for tunnel in active_tunnels(await self.api.tunnels()):
                    await self.api.refresh_tunnel(tunnel["tunnelCode"])
            await self._operation(refresh)
            await asyncio.sleep(60)
            async def finish():
                if repair:
                    apps, domains = repair_plan(await self.api.snapshot())
                    for app, code in apps:
                        await self.api.set_app(app, code)
                    for name, old, new in domains:
                        await self.api.set_domain(name, old, new)
            await self._operation(finish)
