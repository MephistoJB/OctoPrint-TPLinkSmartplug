"""Adapt the TPAP-only P110 transport to the device interface used by 2.0.

python-kasa handles every other configured device. This small adapter keeps
the existing TPAP implementation out of the printer/event switching paths.
"""
import asyncio
import threading
import weakref


_request_locks = weakref.WeakKeyDictionary()
_request_locks_guard = threading.Lock()

from .tapo_transport import TapoError


class TapoDevice:
    has_emeter = False
    children = ()

    def __init__(self, transport, plug, credentials=None):
        self._transport = transport
        self._plug = plug
        self._credentials = credentials
        self.is_on = None
        self.state_information = {}

    async def _send(self, command):
        # All adapter instances share the worker's gate for this transport. Waiting
        # happens in asyncio, so cancellation removes a queued write before any
        # thread is created. A status read must not make an automatic Off fail.
        loop = asyncio.get_running_loop()
        with _request_locks_guard:
            locks = _request_locks.setdefault(self._transport, {})
            lock = locks.setdefault(loop, asyncio.Lock())
        async with lock:
            task = asyncio.create_task(asyncio.to_thread(
                self._transport.send, command, self._plug, credentials=self._credentials
            ))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Keep the gate until an already-started, bounded request ends.
                # Its outcome is uncertain, and no request is replayed here.
                try:
                    await asyncio.shield(task)
                except Exception:
                    pass
                raise

    async def update(self):
        result = await self._send({"system": {"get_sysinfo": {}}})
        state = result.get("system", {}).get("get_sysinfo", {}).get("relay_state")
        if type(state) is not int or state not in (0, 1):
            raise TapoError("Tapo returned no valid relay state.")
        self.is_on = bool(state)
        self.state_information = {"Relay state": self.is_on}

    async def _switch(self, state):
        result = await self._send({"system": {"set_relay_state": {"state": state}}})
        if result.get("system", {}).get("set_relay_state", {}).get("err_code") != 0:
            raise TapoError("Tapo switching failed. Check the plug status; the command was not retried.")

    async def turn_on(self):
        await self._switch(1)

    async def turn_off(self):
        await self._switch(0)
