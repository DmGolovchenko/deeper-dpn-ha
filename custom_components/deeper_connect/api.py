"""AtomOS HTTP client using a private cookie jar, including IP-address cookies."""
import asyncio
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from .const import DEFAULT_TELEMETRY, UNASSIGNED
from .telemetry import extract_value, validate_profile


class DeeperError(Exception):
    """Communication, protocol, or operation failure."""


class DeeperCommandUncertain(DeeperError):
    """The device disconnected after a command; do not replay it."""


class DeeperAuthError(DeeperError):
    """Authentication rejected."""


def normalize_url(value):
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use an http(s) device API URL without credentials, query, or fragment")
    if parsed.path not in {"", "/api"}:
        raise ValueError("Use the device URL or its /api base URL")
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, "", ""))


class DeeperApi:
    def __init__(self, base_url, username, password, profile=None):
        self.base_url = normalize_url(base_url)
        self.username = username
        self.password = password
        self.profile = validate_profile({**DEFAULT_TELEMETRY, **(profile or {})})
        self._version_check = None
        self._version_checked_at = 0
        self._session = None
        self._authenticated = False
        self._lock = asyncio.Lock()

    async def close(self):
        if self._session is not None:
            await self._session.close()

    def _get_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                timeout=aiohttp.ClientTimeout(total=20),
            )
        return self._session

    async def _raw(self, method, path, **kwargs):
        try:
            async with self._get_session().request(method, self.base_url + path, allow_redirects=False, **kwargs) as response:
                if response.status in (401, 403):
                    raise DeeperAuthError("Session rejected")
                if response.status >= 300:
                    raise DeeperError(f"AtomOS HTTP {response.status}")
                # Some firmware sends JSON with a non-JSON Content-Type.
                return await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise DeeperError("AtomOS request failed or returned invalid JSON") from err

    async def _login(self):
        # password is the opaque API-ready encrypted value from AtomOS.
        # Send it verbatim: do not strip, decode, hash or encrypt it again.
        self._authenticated = False
        result = await self._raw("POST", "/admin/login", json={"username": self.username, "password": self.password})
        if not isinstance(result, dict) or result.get("success") is not True:
            raise DeeperAuthError("Login rejected")
        self._authenticated = True

    async def request(self, method, path, **kwargs):
        async with self._lock:
            if not self._authenticated:
                await self._login()
            try:
                result = await self._raw(method, path, **kwargs)
            except DeeperAuthError:
                await self._login()
                result = await self._raw(method, path, **kwargs)
            if isinstance(result, dict) and result.get("success") is False:
                raise DeeperError("AtomOS rejected the operation")
            return result

    async def mutate(self, path, payload):
        result = await self.request("POST", path, json=payload)
        if not isinstance(result, dict) or result.get("success") is not True:
            raise DeeperError("AtomOS did not confirm the operation")

    async def tunnels(self):
        result = await self.request("GET", "/smartRoute/listTunnels")
        if not isinstance(result, list) or any(not isinstance(t, dict) or not isinstance(t.get("tunnelCode"), str) or not isinstance(t.get("activeNum"), (int, float)) for t in result):
            raise DeeperError("Unexpected tunnels response")
        return result

    async def apps(self):
        result = await self.request("GET", "/appRelocator/apps")
        try:
            category = next(x for x in result if x["category"] == "allCategories")
            apps = next(x["apps"] for x in category["appsBySubcategory"] if x["subcategory"] == "allCountries")
            if not isinstance(apps, list) or any(not isinstance(a, dict) or not isinstance(a.get("app"), str) or not isinstance(a.get("tunnel"), str) for a in apps):
                raise ValueError
            return apps
        except (StopIteration, KeyError, TypeError, ValueError) as err:
            raise DeeperError("Unexpected apps response") from err

    async def domains(self):
        result = []
        for page in range(1, 501):
            data = await self.request("GET", "/smartRoute/getRoutingWhitelist/domain", params={"pageNo": page, "pageSize": 100})
            items = data.get("list") if isinstance(data, dict) else None
            if not isinstance(items, list) or any(not isinstance(d, dict) or not isinstance(d.get("domainName"), str) or not isinstance(d.get("tunnelCode"), str) for d in items):
                raise DeeperError("Unexpected domains response")
            result.extend(items)
            if len(items) < 100:
                return result
        raise DeeperError("Whitelist pagination limit exceeded")

    async def snapshot(self):
        return {"tunnels": await self.tunnels(), "apps": await self.apps(), "domains": await self.domains()}

    async def set_app(self, app, tunnel):
        await self.mutate("/appRelocator/delApp" if tunnel == UNASSIGNED else "/appRelocator/addApp", {"appName": app, "tunnelCode": tunnel})

    async def set_domain(self, name, old, new):
        await self.mutate("/smartRoute/editWhiteEntry/domain", {"domainName": name, "fromTunnelCode": old, "toTunnelCode": new})

    async def add_domain(self, name, target):
        await self.mutate("/smartRoute/addToWhitelist/domain", {"domainName": name, "tunnelCode": target})

    async def refresh_tunnel(self, code):
        await self.mutate("/smartRoute/refreshTunnel", {"tunnelCode": code})

    async def routing(self):
        result = await self.info("/smartRoute/getDpnMode")
        if result.get("dpnMode") not in {"disabled", "smart", "full"}:
            raise DeeperError("Unexpected routing mode response")
        return result

    async def set_routing(self, mode, code):
        if mode not in {"disabled", "smart", "full"} or not isinstance(code, str) or not code:
            raise DeeperError("Invalid routing parameters")
        await self.mutate("/smartRoute/setDpnMode", {"dpnMode": mode, "tunnelCode": code})

    async def reboot(self):
        """Send once; an empty successful response is valid for this endpoint."""
        async with self._lock:
            if not self._authenticated:
                await self._login()
            try:
                async with self._get_session().post(
                    self.base_url + "/admin/reboot", allow_redirects=False,
                ) as response:
                    if response.status in (401, 403):
                        self._authenticated = False
                        raise DeeperAuthError("Reboot authentication rejected")
                    if response.status >= 300:
                        raise DeeperError(f"AtomOS HTTP {response.status}")
                    body = await response.read()
                    if body:
                        import json
                        try:
                            result = json.loads(body)
                        except ValueError:
                            result = None
                        if isinstance(result, dict) and result.get("success") is False:
                            raise DeeperError("AtomOS rejected reboot")
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientPayloadError, asyncio.TimeoutError) as err:
                raise DeeperCommandUncertain(
                    "Device disconnected after reboot request; the result is unconfirmed. Check device status before retrying."
                ) from err
            except aiohttp.ClientError as err:
                raise DeeperError("Could not send reboot request") from err
            finally:
                self._authenticated = False

    async def hardware(self):
        result = await self.request("GET", "/system-info/hardware-info")
        if not isinstance(result, dict):
            raise DeeperError("Unexpected hardware response")
        return result

    async def info(self, endpoint):
        result = await self.request("GET", endpoint)
        if not isinstance(result, dict):
            raise DeeperError("Unexpected device information response")
        return result

    def invalidate_version_check(self):
        self._version_checked_at = 0
        self._version_check = None

    async def telemetry(self, initial=None):
        values, errors, responses = {}, [], dict(initial or {})
        for field, spec in self.profile.items():
            endpoint = spec["endpoint"]
            if endpoint not in responses:
                try:
                    if endpoint == "/system-info/get-latestversion":
                        from time import monotonic
                        if self._version_check is None or monotonic() - self._version_checked_at >= 21600:
                            self._version_check = await self.request("GET", endpoint)
                            self._version_checked_at = monotonic()
                        responses[endpoint] = self._version_check
                    else:
                        responses[endpoint] = await self.request("GET", endpoint)
                except DeeperAuthError:
                    raise
                except DeeperError:
                    responses[endpoint] = None
            value = extract_value(responses[endpoint], spec, field)
            values[field] = value
            if value is None:
                errors.append(field)
        return values, errors
