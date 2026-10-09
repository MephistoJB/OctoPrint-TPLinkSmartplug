import asyncio
from unittest.mock import Mock

import pytest

from octoprint_tplinksmartplug.worker import AsyncTaskWorker
from octoprint_tplinksmartplug.tapo_device import TapoDevice
from octoprint_tplinksmartplug.tapo_transport import TapoError


def test_worker_is_ready_on_construction_and_can_shutdown_immediately():
    worker=AsyncTaskWorker()
    worker.shutdown()
    assert not worker._thread.is_alive()
    assert worker.loop.is_closed()
    worker.shutdown()


def test_worker_cancels_pending_task_and_rejects_new_tasks_after_shutdown():
    worker=AsyncTaskWorker()
    started=__import__('threading').Event()
    async def task():
        started.set()
        await asyncio.sleep(30)
    future=worker.run_coroutine_threadsafe(task())
    assert started.wait(2)
    worker.shutdown()
    assert future.cancelled()
    with pytest.raises(RuntimeError):worker.run_coroutine_threadsafe(task())


def test_adapter_requires_a_write_acknowledgement_and_never_fakes_energy():
    transport=Mock();transport.send.return_value={'system':{'set_relay_state':{'err_code':-1}}}
    device=TapoDevice(transport,{'ip':'192.0.2.1'})
    with pytest.raises(TapoError,match='switching failed'):asyncio.run(device.turn_off())
    assert transport.send.call_count==1
    assert device.is_on is None
    assert device.has_emeter is False


@pytest.mark.parametrize('state',[None,3,True,'1'])
def test_adapter_does_not_interpret_invalid_status_as_powered_on(state):
    transport=Mock();transport.send.return_value={'system':{'get_sysinfo':{'relay_state':state}}}
    device=TapoDevice(transport,{'ip':'192.0.2.1'})
    with pytest.raises(TapoError,match='valid relay state'):asyncio.run(device.update())
