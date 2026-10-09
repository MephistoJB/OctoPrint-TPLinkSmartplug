import copy
from unittest.mock import AsyncMock, Mock, patch

import pytest

from octoprint_tplinksmartplug import tplinksmartplugPlugin
from octoprint_tplinksmartplug.tapo_transport import TapoError
from octoprint_tplinksmartplug.tapo_device import TapoDevice

STATUS = {"system": {"get_sysinfo": {}}}
ON = {"system": {"set_relay_state": {"state": 1}}}
OFF = {"system": {"set_relay_state": {"state": 0}}}

@pytest.fixture
def plugin():
    p = tplinksmartplugPlugin()
    p._settings = Mock()
    p._printer = Mock()
    p._plugin_manager = Mock()
    config = p.get_settings_defaults()
    p._settings.get.side_effect = lambda path: config.get(path[0])
    p._test_config = config
    yield p
    p.on_shutdown()


def configure(plugin, **overrides):
    plug = dict(ip="192.0.2.1", backend="tapo", useCountdownRules=False,
                autoConnect=False, autoDisconnect=False, gcodeCmdOn=False,
                gcodeCmdOff=False, sysCmdOn=False, sysCmdOff=False,
                automaticShutdownEnabled=False, event_on_startup=False)
    plug.update(overrides)
    plugin._test_config['arrSmartplugs'] = [plug]
    return plug


def tapo_transport(plugin, state=True):
    adapter = Mock()
    def send(command, plug, credentials=None):
        nonlocal state
        if command == STATUS:
            return {"system": {"get_sysinfo": {"relay_state": int(state)}}}
        state = command == ON
        return {"system": {"set_relay_state": {"err_code": 0}}}
    adapter.send.side_effect = send
    plugin._tapo_transport = adapter
    return adapter


@pytest.mark.parametrize('backend', ['kasa', None])
def test_normal_and_legacy_plugs_use_upstream_python_kasa(plugin, backend):
    plug = configure(plugin, backend=backend)
    if backend is None: del plug['backend']
    device = Mock()
    with patch.object(plugin, 'get_device_config', return_value={'host':plug['ip']}), patch.object(plugin, 'connect_device', new=AsyncMock(return_value=device)) as connect:
        assert plugin.get_device(plug['ip']) is device
    connect.assert_awaited_once_with({'host':plug['ip']})
    assert plugin._tapo_transport is None


def test_tpap_uses_only_the_retained_adapter(plugin):
    plug = configure(plugin)
    adapter = tapo_transport(plugin)
    with patch.object(plugin, 'get_device_config') as config:
        device = plugin.get_device(plug['ip'])
    assert isinstance(device, TapoDevice)
    assert device.is_on is True
    config.assert_not_called()
    adapter.send.assert_called_once_with(STATUS, plug, credentials=None)


@pytest.mark.parametrize('method,command,state', [('turn_on', ON, 'on'), ('turn_off', OFF, 'off')])
def test_tpap_switches_through_common_v2_device_path(plugin, method, command, state):
    plug = configure(plugin)
    adapter = tapo_transport(plugin, state=method != 'turn_on')
    result = getattr(plugin,method)(plug['ip'])
    assert result == {'ip':plug['ip'], 'currentState':state, 'emeter':None}
    writes = [call for call in adapter.send.call_args_list if call.args[0] != STATUS]
    assert len(writes) == 1
    assert writes[0].args[0] == command
    assert not plugin._printer.mock_calls


@pytest.mark.parametrize('backend', ['kasa','tapo'])
@pytest.mark.parametrize('method', ['turn_on','turn_off'])
def test_removed_timers_never_silently_become_immediate_writes(plugin, backend, method):
    plug = configure(plugin, backend=backend, useCountdownRules=True, autoDisconnect=True, sysCmdOff=True)
    with patch.object(plugin,'get_device') as get_device:
        result = getattr(plugin,method)(plug['ip'])
    assert result['currentState'] == 'unknown'
    assert 'countdown timers' in result['error']
    get_device.assert_not_called()
    assert not plugin._printer.mock_calls


@pytest.mark.parametrize('method', ['turn_on','turn_off'])
def test_failed_write_is_never_reported_as_successful_read(plugin, method):
    plug = configure(plugin)
    adapter = tapo_transport(plugin)
    original = adapter.send.side_effect
    def send(command, *args, **kwargs):
        if command != STATUS: raise TapoError('Tapo communication failed; the command was not retried.')
        return original(command, *args, **kwargs)
    adapter.send.side_effect = send
    with patch.object(plugin,'check_status') as status:
        result = getattr(plugin,method)(plug['ip'])
    assert result['currentState'] == 'unknown'
    assert 'not retried' in result['error']
    assert adapter.send.call_count == 2 # one preflight read and one failed write
    status.assert_not_called()


def test_failed_authentication_precedes_printer_or_system_effects(plugin):
    plug = configure(plugin, autoDisconnect=True, gcodeCmdOff=True, gcodeRunCmdOff='M104 S0', sysCmdOff=True)
    plugin._tapo_transport = Mock()
    plugin._tapo_transport.send.side_effect = TapoError('Tapo authentication failed.')
    with patch('octoprint_tplinksmartplug.os.system') as system:
        result = plugin.turn_off(plug['ip'])
    assert result['currentState'] == 'unknown'
    assert not plugin._printer.mock_calls
    system.assert_not_called()


@pytest.mark.parametrize('relay,state', [(True,'on'),(False,'off')])
def test_status_has_no_invented_energy_readings(plugin,relay,state):
    plug=configure(plugin);tapo_transport(plugin,relay)
    assert plugin.check_status(plug['ip']) == {'ip':plug['ip'],'currentState':state,'emeter':None}


def test_exception_details_never_reach_logs_or_api(plugin,caplog):
    plug=configure(plugin);plugin._tapo_transport=Mock()
    plugin._tapo_transport.send.side_effect=RuntimeError('private-session-password')
    result=plugin.check_status(plug['ip'])
    assert result['currentState']=='unknown'
    assert 'private-session-password' not in str(result)
    assert 'private-session-password' not in caplog.text


def test_unknown_backend_cannot_fall_back_to_other_connection(plugin):
    plug=configure(plugin,backend='typo')
    with patch.object(plugin,'get_device_config') as config:
        result=plugin.turn_on(plug['ip'])
    assert result['currentState']=='unknown'
    config.assert_not_called()


def test_private_account_overrides_default_for_python_kasa(plugin):
    plug=configure(plugin,backend='kasa',tapoCredentialId='id')
    plugin._test_config.update(tapoCredentials={'id':{'username':'test@example.invalid','password':'test-private'}},username='default@example.invalid',password='test-default',device_configs={plug['ip']:{'host':plug['ip'],'credentials_hash':'stale-hash'}})
    result=plugin.get_device_config(plug['ip'])
    assert result['credentials']=={'username':'test@example.invalid','password':'test-private'}
    assert 'credentials_hash' not in result
    assert 'credentials' not in plugin._test_config['device_configs'][plug['ip']]


def test_newly_discovered_config_never_persists_password(plugin):
    plug=configure(plugin,backend='kasa')
    plugin._test_config.update(username='test@example.invalid',password='test-default')
    device=Mock();device.config.to_dict.return_value={'host':plug['ip'],'credentials':{'username':'test@example.invalid','password':'test-default'}}
    with patch('octoprint_tplinksmartplug.Discover.discover_single', new=AsyncMock(return_value=device)):
        result=plugin.get_device_config(plug['ip'])
    stored=plugin._settings.set.call_args.args[1]
    assert 'credentials' not in stored[plug['ip']]
    assert result['credentials']['password']=='test-default'


def test_update_source_remains_with_upstream(plugin):
    plugin._plugin_version='2.0.0rc8'
    info=plugin.get_update_information()['tplinksmartplug']
    assert info['user']=='jneilliii'
    assert 'github.com/jneilliii/' in info['pip']


def test_discovery_error_never_returns_or_logs_library_exception_details(plugin,caplog):
    import flask
    configure(plugin,backend='kasa')
    app=flask.Flask(__name__)
    with app.test_request_context(), patch('octoprint_tplinksmartplug.Permissions') as permissions, patch.object(plugin,'discover_devices',new=AsyncMock(side_effect=RuntimeError('private-session-password'))):
        permissions.PLUGIN_TPLINKSMARTPLUG_CONTROL.can.return_value=True
        permissions.ADMIN.can.return_value=True
        response=plugin.on_api_command('discoverDevices',{'username':'','password':''})
    assert response.status_code==502
    assert 'private-session-password' not in response.get_data(as_text=True)
    assert 'private-session-password' not in caplog.text


def test_discovered_device_update_does_not_log_account_exception(plugin,caplog):
    device=Mock();device.update=AsyncMock(side_effect=RuntimeError('private-session-password'))
    plugin._run_device_task(plugin.update_device(device))
    assert 'private-session-password' not in caplog.text
