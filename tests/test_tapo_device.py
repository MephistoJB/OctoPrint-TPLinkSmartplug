import asyncio
import threading
from unittest.mock import Mock

import pytest

from octoprint_tplinksmartplug.tapo_device import TapoDevice
from octoprint_tplinksmartplug.tapo_transport import TapoTransport

PLUG={'ip':'192.0.2.1'}
ACCOUNT={'username':'test@example.invalid','password':'test-private'}


def run_case(cancel=False, cancel_read=False):
    entered=threading.Event()
    release=threading.Event()
    writes=[]
    class Device:
        async def get_device_info(self):
            entered.set()
            await asyncio.to_thread(release.wait)
            return Mock(to_dict=lambda:{'device_on':True})
        async def off(self):writes.append('off')
    device=Device()
    class Client:
        async def p110(self,ip):return device
    transport=TapoTransport(lambda *args:Client())
    async def scenario():
        reader=TapoDevice(transport,PLUG,ACCOUNT)
        writer=TapoDevice(transport,PLUG,ACCOUNT)
        read=asyncio.create_task(reader.update())
        assert await asyncio.to_thread(entered.wait,2)
        if cancel_read:read.cancel()
        write=asyncio.create_task(writer.turn_off())
        await asyncio.sleep(0.03)
        assert not writes
        if cancel:
            write.cancel()
            with pytest.raises(asyncio.CancelledError):await write
        release.set()
        if cancel_read:
            with pytest.raises(asyncio.CancelledError):await read
        else:await read
        if not cancel:await write
        await asyncio.sleep(0.03)
    try:asyncio.run(scenario())
    finally:release.set();transport.close()
    return writes


def test_status_poll_does_not_drop_concurrent_off():
    assert run_case()==['off']


def test_cancelled_queued_off_is_never_sent_later():
    assert run_case(cancel=True)==[]


def test_cancelled_inflight_status_keeps_gate_until_transport_finishes():
    assert run_case(cancel_read=True)==['off']
