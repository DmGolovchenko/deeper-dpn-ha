"""UI setup, credentials renewal and optional telemetry mappings."""

try:
    import probatio as vol  # Home Assistant 2026.10
except ImportError:
    import voluptuous as vol  # Earlier Home Assistant releases
from uuid import uuid4

from homeassistant import config_entries
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import DeeperApi, DeeperAuthError, DeeperError, normalize_url
from .auth import InvalidPassword, prepare_credentials
from .const import DIRECT, DOMAIN, UNASSIGNED
from .app_routes import app_route_options
from .localization import ha_language
from .services_config import app_details, parse_domains, selected_apps


async def probe(data):
    api = DeeperApi(data["base_url"], data["username"], data["password"])
    try:
        await api.snapshot()
        try:
            return await api.request("GET", "/system-info/hardware-info")
        except DeeperAuthError:
            raise
        except DeeperError:
            return {}
    finally:
        await api.close()


def credentials_schema(data=None):
    data = data or {}
    return vol.Schema({
        vol.Required("base_url", default=data.get("base_url", "http://34.34.34.34/api")): str,
        vol.Required("username", default=data.get("username", "admin")): str,
        vol.Required("password"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
    })


class DeeperConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input["base_url"] = normalize_url(user_input["base_url"])
                prepared = prepare_credentials(user_input)
                hardware = await probe(prepared)
                serial = (hardware.get("deviceId") or hardware.get("SN")) if isinstance(hardware, dict) else None
                if serial:
                    await self.async_set_unique_id(str(serial))
                    self._abort_if_unique_id_configured()
                if any(e.data["base_url"] == user_input["base_url"] for e in self._async_current_entries()):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(title="Deeper Connect Mini", data=prepared)
            except DeeperAuthError:
                errors["base"] = "invalid_auth"
            except DeeperError:
                errors["base"] = "cannot_connect"
            except InvalidPassword:
                errors["base"] = "invalid_password"
            except ValueError:
                errors["base"] = "invalid_url"
        return self.async_show_form(step_id="user", data_schema=credentials_schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                data["base_url"] = normalize_url(data["base_url"])
                prepared = prepare_credentials(data)
                hardware = await probe(prepared)
                serial = (hardware.get("deviceId") or hardware.get("SN")) if isinstance(hardware, dict) else None
                if entry.unique_id and serial != entry.unique_id:
                    errors["base"] = "wrong_device"
                else:
                    return self.async_update_reload_and_abort(entry, data=prepared)
            except DeeperAuthError:
                errors["base"] = "invalid_auth"
            except DeeperError:
                errors["base"] = "cannot_connect"
            except InvalidPassword:
                errors["base"] = "invalid_password"
            except ValueError:
                errors["base"] = "invalid_url"
        return self.async_show_form(step_id="reauth_confirm", data_schema=credentials_schema({**entry.data, **(user_input or {})}), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        # The same form permits an IP or credentials change outside a reauth error.
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            try:
                user_input["base_url"] = normalize_url(user_input["base_url"])
                prepared = prepare_credentials(user_input)
                hardware = await probe(prepared)
                serial = (hardware.get("deviceId") or hardware.get("SN")) if isinstance(hardware, dict) else None
                if entry.unique_id and serial != entry.unique_id:
                    errors["base"] = "wrong_device"
                elif any(e.entry_id != entry.entry_id and e.data["base_url"] == user_input["base_url"] for e in self._async_current_entries()):
                    errors["base"] = "already_configured"
                else:
                    return self.async_update_reload_and_abort(entry, data=prepared, reason="reconfigure_successful")
            except DeeperAuthError:
                errors["base"] = "invalid_auth"
            except DeeperError:
                errors["base"] = "cannot_connect"
            except InvalidPassword:
                errors["base"] = "invalid_password"
            except ValueError:
                errors["base"] = "invalid_url"
        return self.async_show_form(step_id="reconfigure", data_schema=credentials_schema({**entry.data, **(user_input or {})}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DeeperOptionsFlow()


class DeeperOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["settings", "application", "custom_service"])

    def _finish(self, updates):
        return self.async_create_entry(title="", data={**self.config_entry.options, **updates})

    def _coordinator(self):
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None:
            raise HomeAssistantError("Integration is not loaded")
        return coordinator

    async def _snapshot(self):
        coordinator = self._coordinator()
        async with coordinator.operation_lock:
            return await coordinator.api.snapshot()

    def _route_selector(self, snapshot, custom=False):
        choices = app_route_options({**snapshot, "apps": []}, "", ha_language(self.hass))
        return selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value": code, "label": label} for label, code in choices.items() if not custom or code != UNASSIGNED],
            mode=selector.SelectSelectorMode.DROPDOWN,
        ))

    async def async_step_settings(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self._finish({**user_input, "auto_refresh_confirmed": True})
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Required("scan_interval", default=options.get("scan_interval", 60)): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
            vol.Required("auto_refresh", default=options.get("auto_refresh", False) and options.get("auto_refresh_confirmed", False)): bool,
            vol.Required("refresh_interval_minutes", default=options.get("refresh_interval_minutes", 60)): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        })
        return self.async_show_form(step_id="settings", data_schema=schema, errors=errors)


    async def async_step_application(self, user_input=None):
        errors = {}
        try:
            snapshot = await self._snapshot()
        except (DeeperError, HomeAssistantError):
            return self.async_abort(reason="cannot_connect")
        apps = {app["app"] for app in snapshot["apps"]}
        if user_input is not None:
            if user_input["application"] not in apps:
                errors["base"] = "application_missing"
            else:
                try:
                    await self._coordinator().set_app(user_input["application"], code=user_input["tunnel"])
                    displayed = selected_apps(self.config_entry.options)
                    if user_input["application"] not in displayed:
                        displayed.append(user_input["application"])
                    return self._finish({"selected_apps": displayed})
                except HomeAssistantError:
                    errors["base"] = "operation_failed"
        schema = vol.Schema({
            vol.Required("application"): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[{"value": app, "label": app_details(app)["name"]} for app in sorted(apps)],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )),
            vol.Required("tunnel"): self._route_selector(snapshot),
        })
        return self.async_show_form(step_id="application", data_schema=schema, errors=errors)

    async def async_step_custom_service(self, user_input=None):
        errors = {}
        try:
            snapshot = await self._snapshot()
        except (DeeperError, HomeAssistantError):
            return self.async_abort(reason="cannot_connect")
        services = list(self.config_entry.options.get("custom_services", []))
        if user_input is not None:
            name = user_input["name"].strip()
            domains = None
            try:
                domains = parse_domains(user_input["domains"])
            except ValueError:
                errors["domains"] = "invalid_domains"
            if not name or len(name) > 60:
                errors["name"] = "invalid_name"
            elif any(service["name"].casefold() == name.casefold() for service in services):
                errors["name"] = "name_exists"
            if domains and any(set(domains) & set(service["domains"]) for service in services):
                errors["domains"] = "domain_in_use"
            if not errors:
                try:
                    await self._coordinator().configure_domains(domains, user_input["tunnel"])
                    services.append({"id": uuid4().hex, "name": name, "domains": domains})
                    return self._finish({"custom_services": services})
                except HomeAssistantError:
                    errors["base"] = "operation_failed"
        schema = vol.Schema({
            vol.Required("name"): str,
            vol.Required("domains"): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required("tunnel"): self._route_selector(snapshot, custom=True),
        })
        return self.async_show_form(step_id="custom_service", data_schema=schema, errors=errors)
