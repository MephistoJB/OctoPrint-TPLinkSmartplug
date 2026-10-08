import copy
import json
from unittest.mock import Mock, patch

import pytest
from octoprint.plugin import PluginSettings
from octoprint.settings import Settings

from octoprint_tplinksmartplug import tplinksmartplugPlugin
from octoprint_tplinksmartplug.tapo_credentials import prepare_settings, public_plugs

CID = "test-credential-id"
PASSWORD = "test-password-not-a-real-secret"
ACCOUNT = {CID: {"username": "test@example.invalid", "password": PASSWORD}}
PLUG = {"ip": "192.0.2.1", "backend": "tapo", "tapoCredentialId": CID}


def payload(**fields):
    return {"arrSmartplugs": [dict(PLUG, **fields)]}


def test_password_never_appears_in_admin_settings_response():
    result = public_plugs([PLUG], ACCOUNT, admin=True)
    assert result[0]["tapoUsername"] == "test@example.invalid"
    assert result[0]["tapoPassword"] == ""
    assert result[0]["tapoPasswordSet"] is True
    assert PASSWORD not in json.dumps(result)
    assert ACCOUNT[CID]["password"] == PASSWORD


def test_non_admin_does_not_receive_email_or_password_status():
    result = public_plugs([dict(PLUG, tapoPassword=PASSWORD)], ACCOUNT, admin=False)
    assert "tapoUsername" not in result[0]
    assert "tapoPassword" not in result[0]
    assert "tapoPasswordSet" not in result[0]


def test_blank_password_preserves_saved_password():
    clean, accounts = prepare_settings(payload(tapoUsername="test@example.invalid", tapoPassword=""), [PLUG], ACCOUNT, True)
    assert accounts == ACCOUNT
    assert clean == payload()


def test_new_password_replaces_old_password_and_is_not_in_public_plug():
    request = payload(tapoUsername="new@example.invalid", tapoPassword="new-test-password")
    clean, accounts = prepare_settings(request, [PLUG], ACCOUNT, True)
    assert accounts[CID] == {"username": "new@example.invalid", "password": "new-test-password"}
    assert "tapoPassword" not in clean["arrSmartplugs"][0]
    assert ACCOUNT[CID]["password"] == PASSWORD
    assert request["arrSmartplugs"][0]["tapoPassword"] == "new-test-password"


def test_explicit_removal_replaces_private_store_even_when_email_is_in_form():
    clean, accounts = prepare_settings(payload(tapoUsername="test@example.invalid", tapoPassword="", tapoClearCredentials=True), [PLUG], ACCOUNT, True)
    assert accounts == {}
    assert clean == payload()


def test_ip_change_preserves_account_identity():
    request = payload(tapoUsername="test@example.invalid", tapoPassword="")
    request["arrSmartplugs"][0]["ip"] = "192.0.2.2"
    _, accounts = prepare_settings(request, [PLUG], ACCOUNT, True)
    assert accounts == ACCOUNT


def test_deleting_plug_removes_orphaned_credentials():
    _, accounts = prepare_settings({"arrSmartplugs": []}, [PLUG], ACCOUNT, True)
    assert accounts == {}


def test_direct_private_store_submission_cannot_override_password():
    request = payload()
    request["tapoCredentials"] = {CID: {"password": "injected"}}
    clean, accounts = prepare_settings(request, [PLUG], ACCOUNT, True)
    assert "tapoCredentials" not in clean
    assert accounts == ACCOUNT


@pytest.mark.parametrize("fields", [{"tapoUsername": "new@example.invalid"}, {"tapoPassword": "new-test-password"}, {"tapoClearCredentials": True}])
def test_credential_changes_require_administrator(fields):
    with pytest.raises(PermissionError, match="administrators"):
        prepare_settings(payload(**fields), [PLUG], ACCOUNT, False)


def test_changing_account_without_password_fails_before_persisting():
    with pytest.raises(ValueError, match="new password"):
        prepare_settings(payload(tapoUsername="other@example.invalid", tapoPassword=""), [PLUG], ACCOUNT, True)
    assert ACCOUNT[CID]["username"] == "test@example.invalid"


def test_missing_email_for_new_password_is_rejected():
    with pytest.raises(ValueError, match="account email"):
        prepare_settings(payload(tapoUsername="", tapoPassword="new-test-password"), [PLUG], {}, True)


def test_two_plugs_cannot_share_credential_identifier_by_accident():
    with pytest.raises(ValueError, match="separate credential identifier"):
        prepare_settings({"arrSmartplugs": [PLUG, dict(PLUG, ip="192.0.2.2")]}, [PLUG], ACCOUNT, True)


@pytest.fixture
def persisted_plugin(tmp_path):
    config = tmp_path / "config.yaml"
    settings = Settings(configfile=str(config), basedir=str(tmp_path))
    p = tplinksmartplugPlugin()
    p._settings = PluginSettings(settings, "tplinksmartplug", defaults=p.get_settings_defaults())
    p._settings.set(["arrSmartplugs"], [copy.deepcopy(PLUG)])
    yield p, settings, config, tmp_path
    p.on_shutdown()


def test_real_octoprint_settings_persist_password_but_never_return_it(persisted_plugin, caplog):
    p, settings, config, basedir = persisted_plugin
    with patch("octoprint_tplinksmartplug.Permissions.ADMIN.can", return_value=True):
        p.on_settings_save(payload(tapoUsername="test@example.invalid", tapoPassword=PASSWORD))
        settings.save()
        response = p.on_settings_load()
        assert "tapoCredentials" not in response
        assert PASSWORD not in json.dumps(response)
        assert response["arrSmartplugs"][0]["tapoPasswordSet"] is True
        p.on_settings_save(payload(tapoUsername="test@example.invalid", tapoPassword=""))
        settings.save()
    reloaded = Settings(configfile=str(config), basedir=str(basedir))
    wrapper = PluginSettings(reloaded, "tplinksmartplug", defaults=p.get_settings_defaults())
    assert wrapper.get(["tapoCredentials"])[CID]["password"] == PASSWORD
    assert "tapoPassword" not in wrapper.get(["arrSmartplugs"])[0]
    assert PASSWORD not in caplog.text


def test_real_settings_removal_is_not_undone_by_recursive_merge(persisted_plugin):
    p, settings, config, basedir = persisted_plugin
    p._settings.set(["tapoCredentials"], copy.deepcopy(ACCOUNT))
    with patch("octoprint_tplinksmartplug.Permissions.ADMIN.can", return_value=True):
        p.on_settings_save(payload(tapoUsername="test@example.invalid", tapoPassword="", tapoClearCredentials=True))
    settings.save()
    reloaded = Settings(configfile=str(config), basedir=str(basedir))
    wrapper = PluginSettings(reloaded, "tplinksmartplug", defaults=p.get_settings_defaults())
    assert wrapper.get(["tapoCredentials"]) == {}


def test_non_admin_save_cannot_modify_real_settings(persisted_plugin):
    p, _, _, _ = persisted_plugin
    p._settings.set(["tapoCredentials"], copy.deepcopy(ACCOUNT))
    with patch("octoprint_tplinksmartplug.Permissions.ADMIN.can", return_value=False), pytest.raises(PermissionError):
        p.on_settings_save(payload(tapoUsername="new@example.invalid", tapoPassword="new-test-password"))
    assert p._settings.get(["tapoCredentials"]) == ACCOUNT


def test_private_credentials_are_only_passed_to_transport(persisted_plugin):
    p, _, _, _ = persisted_plugin
    p._settings.set(["tapoCredentials"], copy.deepcopy(ACCOUNT))
    p._tapo_transport = Mock()
    p.sendCommand({"system": {"get_sysinfo": {}}}, PLUG["ip"])
    p._tapo_transport.send.assert_called_once_with({"system": {"get_sysinfo": {}}}, PLUG, credentials=ACCOUNT[CID])


def test_legacy_plug_list_api_contains_no_credentials(persisted_plugin):
    p, _, _, _ = persisted_plugin
    with patch("octoprint_tplinksmartplug.Permissions.ADMIN.can", return_value=True):
        p.on_settings_save(payload(tapoUsername="test@example.invalid", tapoPassword=PASSWORD))
    with patch("octoprint_tplinksmartplug.Permissions") as permissions:
        permissions.PLUGIN_TPLINKSMARTPLUG_CONTROL.can.return_value = True
        response = p.on_api_command("getListPlug", {})
    assert PASSWORD not in response
    assert "test@example.invalid" not in response


def test_real_non_admin_settings_response_has_no_account_details(persisted_plugin):
    p, _, _, _ = persisted_plugin
    p._settings.set(["tapoCredentials"], copy.deepcopy(ACCOUNT))
    with patch("octoprint_tplinksmartplug.Permissions.ADMIN.can", return_value=False):
        response = p.on_settings_load()
    assert "tapoCredentials" not in response
    assert "tapoUsername" not in response["arrSmartplugs"][0]
    assert "tapoPasswordSet" not in response["arrSmartplugs"][0]
    assert PASSWORD not in json.dumps(response)
