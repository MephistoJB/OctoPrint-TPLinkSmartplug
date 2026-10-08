import json
from unittest.mock import Mock, patch

import pytest

from octoprint_tplinksmartplug import tplinksmartplugPlugin

STATUS = {"system": {"get_sysinfo": {}}}
ON = {"system": {"set_relay_state": {"state": 1}}}
OFF = {"system": {"set_relay_state": {"state": 0}}}

@pytest.fixture
def plugin():
    p = tplinksmartplugPlugin()
    p._settings = Mock()
    p._printer = Mock()
    p._plugin_manager = Mock()
    yield p
    p.on_shutdown()


def configure(plugin, **overrides):
    plug = dict(ip="192.0.2.1", backend="tapo", useCountdownRules=False,
                autoConnect=False, autoDisconnect=False, gcodeCmdOn=False,
                gcodeCmdOff=False, sysCmdOn=False, sysCmdOff=False,
                automaticShutdownEnabled=False)
    plug.update(overrides)
    plugin._settings.get.return_value = [plug]
    return plug


def test_kasa_remains_default_and_uses_original_wire_protocol(plugin):
    configure(plugin, backend="kasa")
    socket = Mock()
    response = plugin.encrypt(json.dumps({"system": {"get_sysinfo": {"relay_state": 1}}}))
    socket.recv.return_value = response
    with patch("octoprint_tplinksmartplug.socket.socket", return_value=socket):
        result = plugin.sendCommand(STATUS, "192.0.2.1")
    socket.connect.assert_called_once_with(("192.0.2.1", 9999))
    socket.send.assert_called_once_with(plugin.encrypt(json.dumps(STATUS)))
    assert result["system"]["get_sysinfo"]["relay_state"] == 1
    assert plugin._tapo_transport is None


def test_existing_plug_without_backend_remains_kasa(plugin):
    plug = configure(plugin)
    del plug["backend"]
    with patch("octoprint_tplinksmartplug.socket.socket") as socket:
        socket.return_value.recv.return_value = plugin.encrypt(json.dumps({"system": {"get_sysinfo": {"relay_state": 0}}}))
        assert plugin.sendCommand(STATUS, "192.0.2.1")["system"]["get_sysinfo"]["relay_state"] == 0
    socket.return_value.connect.assert_called_once_with(("192.0.2.1", 9999))


def test_tapo_dispatch_never_uses_kasa_socket(plugin):
    plug = configure(plugin)
    adapter = Mock()
    plugin._tapo_transport = adapter
    adapter.send.return_value = {"system": {"get_sysinfo": {"relay_state": 1}}}
    with patch("octoprint_tplinksmartplug.socket.socket") as socket:
        assert plugin.sendCommand(STATUS, plug["ip"]) == adapter.send.return_value
    socket.assert_not_called()
    adapter.send.assert_called_once_with(STATUS, plug)


@pytest.mark.parametrize("method", ["turn_on", "turn_off"])
def test_tapo_device_timers_are_blocked_before_any_side_effect(plugin, method):
    plug = configure(plugin, useCountdownRules=True, autoDisconnect=True, sysCmdOff=True)
    with patch.object(plugin, "sendCommand") as send:
        result = getattr(plugin, method)(plug["ip"])
    assert result["currentState"] == "unknown"
    assert "countdown timers" in result["error"]
    send.assert_not_called()
    assert not plugin._printer.mock_calls


@pytest.mark.parametrize("method,command", [("turn_on", ON), ("turn_off", OFF)])
def test_failed_tapo_write_does_not_get_reported_as_successful_read(plugin, method, command):
    plug = configure(plugin)
    with patch.object(plugin, "sendCommand", return_value={"system": {"set_relay_state": {"err_code": -1}}}) as send, patch.object(plugin, "check_status") as status:
        result = getattr(plugin, method)(plug["ip"])
    assert result["currentState"] == "unknown"
    assert "switching failed" in result["error"]
    send.assert_called_once_with(command, plug["ip"], 0)
    status.assert_not_called()
    assert not plugin._printer.mock_calls


@pytest.mark.parametrize("relay,state", [(1, "on"), (0, "off")])
def test_tapo_status_maps_to_existing_frontend_without_energy_database(plugin, relay, state):
    plug = configure(plugin)
    with patch.object(plugin, "sendCommand", return_value={"system": {"get_sysinfo": {"relay_state": relay, "feature": "", "on_time": 10}}}) as send:
        result = plugin.check_status(plug["ip"])
    assert result == {"currentState": state, "emeter": None, "ip": plug["ip"]}
    send.assert_called_once()


def test_tapo_status_error_is_available_to_frontend(plugin):
    plug = configure(plugin)
    with patch.object(plugin, "sendCommand", return_value={"system": {"get_sysinfo": {"relay_state": 3}}, "error": "Safe error"}):
        result = plugin.check_status(plug["ip"])
    assert result["currentState"] == "unknown"
    assert result["error"] == "Safe error"


def test_migration_preserves_existing_plug_and_automations(plugin):
    plug = {"ip": "192.0.2.5", "event_on_startup": True, "automaticShutdownEnabled": False}
    plugin._settings.get.return_value = [plug]
    plugin.on_settings_migrate(17, 16)
    assert plugin.get_settings_version() == 18
    import uuid
    uuid.UUID(plug.pop("tapoCredentialId"))
    assert plug == {"ip": "192.0.2.5", "event_on_startup": True, "automaticShutdownEnabled": False,
                    "backend": "kasa", "tapoUsernameEnv": "TAPO_USERNAME", "tapoPasswordEnv": "TAPO_PASSWORD"}
    assert not plugin._printer.mock_calls


def test_unknown_backend_does_not_switch_any_device(plugin):
    configure(plugin, backend="typo")
    with patch("octoprint_tplinksmartplug.socket.socket") as socket:
        result = plugin.sendCommand(ON, "192.0.2.1")
    assert result["system"]["set_relay_state"]["err_code"] == -1
    socket.assert_not_called()


def test_exception_details_never_reach_logs_or_api(plugin, caplog):
    configure(plugin)
    plugin._tapo_transport = Mock()
    plugin._tapo_transport.send.side_effect = RuntimeError("private-session-password")
    result = plugin.sendCommand(ON, "192.0.2.1")
    assert "private-session-password" not in str(result)
    assert "private-session-password" not in caplog.text


def test_fork_update_source_will_not_replace_tapo_support(plugin):
    plugin._plugin_version = "1.1.0rc1"
    info = plugin.get_update_information()["tplinksmartplug"]
    assert info["user"] == "MephistoJB"
    assert "github.com/MephistoJB/" in info["pip"]
