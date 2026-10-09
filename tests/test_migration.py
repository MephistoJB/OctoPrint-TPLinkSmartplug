import copy
import json
from unittest.mock import Mock, patch

import pytest
from octoprint.plugin import PluginSettings
from octoprint.settings import Settings

from octoprint_tplinksmartplug import tplinksmartplugPlugin
from octoprint_tplinksmartplug.migration import migrate_v2_settings


def old_settings():
    return dict(arrSmartplugs=[dict(ip='192.0.2.1',label='Printer plug',backend='tapo',tapoCredentialId='existing-id',
        event_on_startup=True,event_on_upload=False,event_on_error=True,event_on_disconnect=False,event_on_shutdown=False,
        automaticShutdownEnabled=True,autoConnect=True,autoConnectDelay=10,autoDisconnect=True,autoDisconnectDelay=0,
        useCountdownRules=False)],tapoCredentials={'existing-id':{'username':'test@example.invalid','password':'dummy-password'}},
        powerOffWhenIdle=True,event_on_startup_monitoring=True,event_on_upload_monitoring=True,event_on_error_monitoring=True,
        event_on_disconnect_monitoring=False,event_on_shutdown_monitoring=False,idleTimeout=30,abortTimeout=30)


def test_our_installed_settings_keep_account_identity_and_enabled_automation():
    old=old_settings();snapshot=copy.deepcopy(old)
    result=migrate_v2_settings(old,True)
    plug=result['arrSmartplugs'][0]
    assert result['tapoCredentials']==old['tapoCredentials']
    assert plug['tapoCredentialId']=='existing-id'
    for key,value in old['arrSmartplugs'][0].items():assert plug[key]==value
    assert plug['connect_on_connect'] is False
    assert plug['receives_led_commands'] is False
    assert result['idleTimeout']==30
    assert result['abortTimeout']==30
    assert old==snapshot, 'migration must not mutate the source'


@pytest.mark.parametrize('event',['startup','upload','error','disconnect','shutdown'])
def test_old_disabled_global_monitor_does_not_arm_per_plug_event(event):
    old=old_settings();old['arrSmartplugs'][0]['event_on_'+event]=True;old['event_on_'+event+'_monitoring']=False
    result=migrate_v2_settings(old,True)
    assert result['arrSmartplugs'][0]['event_on_'+event] is False


def test_old_disabled_idle_switch_does_not_arm_shutdown():
    old=old_settings();old['powerOffWhenIdle']=False
    assert migrate_v2_settings(old,True)['arrSmartplugs'][0]['automaticShutdownEnabled'] is False


def test_upstream_v2_keeps_its_existing_event_state_without_legacy_global_flags():
    old=old_settings();old['event_on_startup_monitoring']=False;old['arrSmartplugs'][0]['connect_on_connect']=True
    result=migrate_v2_settings(old,False)
    assert result['arrSmartplugs'][0]['event_on_startup'] is True
    assert result['arrSmartplugs'][0]['connect_on_connect'] is True


def test_migration_is_idempotent_and_keeps_explicit_timer_guard():
    old=old_settings();old['arrSmartplugs'][0]['useCountdownRules']=True
    once=migrate_v2_settings(old,True)
    assert migrate_v2_settings(once,True)==once
    assert once['arrSmartplugs'][0]['useCountdownRules'] is True


def test_upstream_device_config_credentials_move_out_of_public_plugs():
    old=old_settings();old['arrSmartplugs'][0].pop('tapoCredentialId');old['tapoCredentials']={}
    old['device_configs']={'192.0.2.1':{'host':'192.0.2.1','credentials':{'username':'test@example.invalid','password':'dummy-password'}}}
    result=migrate_v2_settings(old)
    cid=result['arrSmartplugs'][0]['tapoCredentialId']
    assert result['tapoCredentials'][cid]['password']=='dummy-password'
    assert 'credentials' not in result['device_configs']['192.0.2.1']
    assert 'dummy-password' not in json.dumps(result['arrSmartplugs'])


@pytest.mark.parametrize('source_version',[16,18])
def test_real_octoprint_migration_and_reload_never_contact_device(tmp_path,source_version):
    config=tmp_path/'config.yaml';settings=Settings(configfile=str(config),basedir=str(tmp_path))
    p=tplinksmartplugPlugin();p._printer=Mock();p._settings=PluginSettings(settings,'tplinksmartplug',defaults=p.get_settings_defaults())
    try:
        old=old_settings()
        if source_version==16:
            old['arrSmartplugs'][0].pop('backend');old['arrSmartplugs'][0].pop('tapoCredentialId');old['tapoCredentials']={}
        for key,value in old.items():p._settings.set([key],value)
        with patch.object(p,'get_device') as device,patch.object(p,'get_device_config') as discovery:
            p.on_settings_migrate(19,source_version)
        device.assert_not_called();discovery.assert_not_called();assert not p._printer.mock_calls
        settings.save()
        reloaded=Settings(configfile=str(config),basedir=str(tmp_path));wrapper=PluginSettings(reloaded,'tplinksmartplug',defaults=p.get_settings_defaults())
        plug=wrapper.get(['arrSmartplugs'])[0]
        assert plug['event_on_startup'] is True
        assert plug['automaticShutdownEnabled'] is True
        assert plug['connect_on_connect'] is False
        assert plug['receives_led_commands'] is False
        assert p.get_settings_version()==19
        if source_version==18:
            assert wrapper.get(['tapoCredentials'])['existing-id']['password']=='dummy-password'
    finally:p.on_shutdown()
