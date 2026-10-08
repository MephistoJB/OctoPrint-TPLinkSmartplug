"""Tapo P110 transport, isolated from OctoPrint and the legacy Kasa protocol.

Credentials are read from the service environment, never from persisted settings.
All requests run in one worker to keep asyncio out of OctoPrint's event loop.
"""
import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor


class TapoError(Exception):
    """A safe, user-visible message containing no library exception details."""


class TapoTransport:
    def __init__(self, client_factory=None, timeout=10):
        self._client_factory = client_factory
        self._timeout = timeout
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tplink-tapo")
        # Authentication failures stop polling until configuration/credentials change.
        self._blocked = {}

    def close(self):
        with self._lock:
            self._executor.shutdown(wait=True)

    def send(self, command, plug):
        ip = plug.get("ip", "")
        if not ip or "/" in ip:
            raise TapoError("Tapo P110 requires a host without a socket index.")
        if command == {"system": {"get_sysinfo": {}}}:
            action = "status"
        elif command == {"system": {"set_relay_state": {"state": 1}}}:
            action = "on"
        elif command == {"system": {"set_relay_state": {"state": 0}}}:
            action = "off"
        else:
            raise TapoError("This command is not supported for Tapo P110.")

        username = os.environ.get(plug.get("tapoUsernameEnv") or "TAPO_USERNAME", "")
        password = os.environ.get(plug.get("tapoPasswordEnv") or "TAPO_PASSWORD", "")
        if not username or not password:
            raise TapoError("Tapo credentials are missing from the OctoPrint service environment.")

        # Do not queue commands that could execute after their caller has timed out.
        # Serialise submission and wait for the coroutine's own bounded timeout.
        with self._lock:
            credentials = (username, password)
            if self._blocked.get(ip) == credentials:
                raise TapoError("Tapo login is blocked after an authentication failure. Check credentials and save settings before retrying.")
            try:
                return self._executor.submit(self._run, action, ip, username, password).result()
            except TapoError as exc:
                if str(exc) == "Tapo authentication failed. Check the account credentials or device login lock.":
                    self._blocked[ip] = credentials
                raise

    def reset_authentication(self):
        with self._lock:
            self._blocked.clear()

    def _run(self, action, ip, username, password):
        try:
            return asyncio.run(asyncio.wait_for(self._query(action, ip, username, password), self._timeout))
        except TimeoutError:
            raise TapoError("Tapo request timed out. The plug state is unknown; the command was not retried.") from None
        except TapoError:
            raise
        except Exception as exc:
            # Native library errors may contain request details; never log or expose them.
            description = str(exc).upper()
            if any(word in description for word in ("UNAUTHORIZED", "CREDENTIAL", "AUTH", "PASSWORD", "LOGIN")):
                raise TapoError("Tapo authentication failed. Check the account credentials or device login lock.") from None
            raise TapoError("Tapo communication failed. Check reachability and credentials; the command was not retried.") from None

    async def _query(self, action, ip, username, password):
        factory = self._client_factory
        if factory is None:
            try:
                from tapo import ApiClient
            except ImportError:
                raise TapoError("Tapo support requires Python 3.11 or newer and tapo 0.11.1.") from None
            factory = ApiClient
        # Fresh sessions avoid stale tokens; there is no replay of a failed write.
        device = await factory(username, password).p110(ip)
        if action in ("on", "off"):
            await getattr(device, action)()
            return {"system": {"set_relay_state": {"err_code": 0}}}
        info = (await device.get_device_info()).to_dict()
        state = info.get("device_on")
        if not isinstance(state, bool):
            raise TapoError("Tapo returned no valid relay state.")
        return {"system": {"get_sysinfo": {
            "relay_state": int(state), "on_time": info.get("on_time", 0),
            "feature": "", "err_code": 0,
        }}}
