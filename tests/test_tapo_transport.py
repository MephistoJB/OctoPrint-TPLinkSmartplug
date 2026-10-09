import asyncio
import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

# The transport is deliberately independent of the OctoPrint runtime.
spec = importlib.util.spec_from_file_location("transport", Path(__file__).parents[1] / "octoprint_tplinksmartplug" / "tapo_transport.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TapoTransport, TapoError = module.TapoTransport, module.TapoError

STATUS = {"system": {"get_sysinfo": {}}}
ON = {"system": {"set_relay_state": {"state": 1}}}
OFF = {"system": {"set_relay_state": {"state": 0}}}

@pytest.fixture
def plug(monkeypatch):
    monkeypatch.setenv("TAPO_USERNAME", "test@example.invalid")
    monkeypatch.setenv("TAPO_PASSWORD", "dummy-password-for-tests")
    return {"backend": "tapo", "ip": "192.0.2.1"}

@pytest.fixture
def transport():
    device = Mock()
    device.on = AsyncMock()
    device.off = AsyncMock()
    device.get_device_info = AsyncMock(return_value=Mock(to_dict=lambda: {"device_on": True, "on_time": 45}))
    client = Mock(p110=AsyncMock(return_value=device))
    factory = Mock(return_value=client)
    adapter = TapoTransport(factory)
    yield adapter, device, factory
    adapter.close()

@pytest.mark.parametrize("state,relay", [(True, 1), (False, 0)])
def test_status_is_read_only(transport, plug, state, relay):
    adapter, device, factory = transport
    device.get_device_info.return_value = Mock(to_dict=lambda: {"device_on": state})
    result = adapter.send(STATUS, plug)
    assert result["system"]["get_sysinfo"]["relay_state"] == relay
    assert result["system"]["get_sysinfo"]["feature"] == ""
    device.on.assert_not_awaited()
    device.off.assert_not_awaited()
    factory.assert_called_once_with("test@example.invalid", "dummy-password-for-tests")

@pytest.mark.parametrize("command,method,other", [(ON, "on", "off"), (OFF, "off", "on")])
def test_switch_awaits_acknowledgement(transport, plug, command, method, other):
    adapter, device, _ = transport
    assert adapter.send(command, plug) == {"system": {"set_relay_state": {"err_code": 0}}}
    getattr(device, method).assert_awaited_once()
    getattr(device, other).assert_not_awaited()
    device.get_device_info.assert_not_awaited()

@pytest.mark.parametrize("command", [{"count_down": {"add_rule": {"delay": 10, "act": 0}}}, {"count_down": {"delete_all_rules": None}}, {"system": {"reboot": {}}}, {"system": {"set_relay_state": {"state": 3}}}])
def test_unsupported_commands_never_connect(transport, plug, command):
    adapter, _, factory = transport
    with pytest.raises(TapoError, match="not supported"):
        adapter.send(command, plug)
    factory.assert_not_called()

@pytest.mark.parametrize("ip", ["", "192.0.2.1/1"])
def test_invalid_host_does_not_connect(transport, plug, ip):
    adapter, _, factory = transport
    plug["ip"] = ip
    with pytest.raises(TapoError, match="socket index"):
        adapter.send(ON, plug)
    factory.assert_not_called()

@pytest.mark.parametrize("missing", ["TAPO_USERNAME", "TAPO_PASSWORD"])
def test_missing_credentials_do_not_connect(transport, plug, monkeypatch, missing):
    adapter, _, factory = transport
    monkeypatch.delenv(missing)
    with pytest.raises(TapoError, match="credentials are missing"):
        adapter.send(STATUS, plug)
    factory.assert_not_called()


def test_custom_account_variables(transport, plug, monkeypatch):
    adapter, _, factory = transport
    monkeypatch.setenv("OTHER_USER", "other@example.invalid")
    monkeypatch.setenv("OTHER_PASS", "other-dummy-password")
    plug.update(tapoUsernameEnv="OTHER_USER", tapoPasswordEnv="OTHER_PASS")
    adapter.send(STATUS, plug)
    factory.assert_called_once_with("other@example.invalid", "other-dummy-password")


def test_timeout_does_not_replay_write(transport, plug):
    adapter, device, _ = transport
    adapter._timeout = 0.01
    async def slow():
        await asyncio.sleep(1)
    device.off.side_effect = slow
    with pytest.raises(TapoError, match="timed out"):
        adapter.send(OFF, plug)
    device.off.assert_awaited_once()


def test_authentication_failure_blocks_polling_without_exposing_secrets(transport, plug, monkeypatch):
    adapter, device, factory = transport
    device.get_device_info.side_effect = RuntimeError("TPAP_CREDENTIALS dummy-password-for-tests test@example.invalid")
    with pytest.raises(TapoError) as result:
        adapter.send(STATUS, plug)
    assert "dummy-password" not in str(result.value)
    assert "test@example" not in str(result.value)
    with pytest.raises(TapoError, match="login is blocked"):
        adapter.send(STATUS, plug)
    assert factory.call_count == 1
    # Rotating a credential allows a new attempt; settings save can clear the block too.
    monkeypatch.setenv("TAPO_PASSWORD", "rotated-dummy-password")
    device.get_device_info.side_effect = None
    adapter.send(STATUS, plug)
    assert factory.call_count == 2
    adapter.reset_authentication()


@pytest.mark.parametrize("failure", ["Unauthorized", "TPAP_HASH_MISMATCH"])
def test_settings_retry_clears_authentication_block(transport, plug, failure):
    adapter, device, factory = transport
    device.get_device_info.side_effect = RuntimeError(failure)
    with pytest.raises(TapoError):
        adapter.send(STATUS, plug)
    adapter.reset_authentication()
    device.get_device_info.side_effect = None
    adapter.send(STATUS, plug)
    assert factory.call_count == 2


def test_network_failure_does_not_replay_or_reveal_exception(transport, plug):
    adapter, device, _ = transport
    device.on.side_effect = RuntimeError("Socket problem with dummy-password-for-tests")
    with pytest.raises(TapoError) as result:
        adapter.send(ON, plug)
    assert "dummy-password" not in str(result.value)
    device.on.assert_awaited_once()

@pytest.mark.parametrize("info", [{}, {"device_on": None}, {"device_on": "false"}, {"device_on": 1}])
def test_invalid_relay_state_is_not_reported_as_on(transport, plug, info):
    adapter, device, _ = transport
    device.get_device_info.return_value = Mock(to_dict=lambda: info)
    with pytest.raises(TapoError, match="valid relay state"):
        adapter.send(STATUS, plug)


def test_can_be_called_from_a_running_octoprint_event_loop(transport, plug):
    adapter, _, _ = transport
    async def caller():
        return adapter.send(STATUS, plug)
    assert asyncio.run(caller())["system"]["get_sysinfo"]["relay_state"] == 1


def test_concurrent_calls_are_serialized(transport, plug):
    adapter, device, _ = transport
    active = 0
    maximum = 0
    async def info():
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return Mock(to_dict=lambda: {"device_on": True})
    device.get_device_info.side_effect = info
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: adapter.send(STATUS, plug), range(3)))
    assert maximum == 1
    assert len(results) == 3


def test_installed_tapo_library_has_expected_api():
    from tapo import ApiClient
    assert callable(ApiClient.p110)


def test_saved_credentials_override_environment(transport, plug):
    adapter, _, factory = transport
    adapter.send(STATUS, plug, credentials={"username": "saved@example.invalid", "password": "saved-test-password"})
    factory.assert_called_once_with("saved@example.invalid", "saved-test-password")


def test_incomplete_saved_account_does_not_silently_use_environment(transport, plug):
    adapter, _, factory = transport
    with pytest.raises(TapoError, match="credentials are missing"):
        adapter.send(STATUS, plug, credentials={"username": "saved@example.invalid"})
    factory.assert_not_called()


def test_write_is_not_queued_behind_another_request(transport, plug):
    adapter, device, _ = transport
    entered = threading.Event()
    release = threading.Event()
    async def info():
        entered.set()
        await asyncio.to_thread(release.wait)
        return Mock(to_dict=lambda: {'device_on':True})
    device.get_device_info.side_effect = info
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(adapter.send, STATUS, plug)
        assert entered.wait(2)
        try:
            with pytest.raises(TapoError, match='command was not sent'):
                adapter.send(OFF, plug)
        finally:
            release.set()
        assert pending.result()['system']['get_sysinfo']['relay_state']==1
    device.off.assert_not_awaited()
