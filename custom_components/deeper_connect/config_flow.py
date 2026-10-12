"""UI setup, credentials renewal and optional telemetry mappings."""
import json

try:
    import probatio as vol  # Home Assistant 2026.10
except ImportError:
    import voluptuous as vol  # Earlier Home Assistant releases
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import DeeperApi, DeeperAuthError, DeeperError, normalize_url
from .auth import InvalidPassword, prepare_credentials
from .const import DOMAIN
from .telemetry import validate_profile


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
        vol.Required("password_is_encrypted", default=data.get("password_is_encrypted", "password" in data)): bool,
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
                    return self.async_update_reload_and_abort(entry, data_updates=prepared)
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
                    return self.async_update_reload_and_abort(entry, data_updates=prepared, reason="reconfigure_successful")
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
        errors = {}
        if user_input is not None:
            try:
                user_input["telemetry_profile"] = validate_profile(json.loads(user_input["telemetry_profile"]))
                return self.async_create_entry(title="", data=user_input)
            except (ValueError, TypeError):
                errors["base"] = "invalid_profile"
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Required("scan_interval", default=options.get("scan_interval", 60)): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
            vol.Required("auto_refresh", default=options.get("auto_refresh", False)): bool,
            vol.Required("telemetry_profile", default=json.dumps(options.get("telemetry_profile", {}), ensure_ascii=False, indent=2)): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
