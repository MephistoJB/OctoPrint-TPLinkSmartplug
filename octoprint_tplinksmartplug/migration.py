"""Pure migration from the 1.x fork or upstream 2.0 to settings version 19."""
import copy
import uuid


def migrate_v2_settings(settings, legacy_base=False):
    result = copy.deepcopy(settings)
    accounts = result.get("tapoCredentials") or {}
    configs = result.get("device_configs") or {}
    plugs = result.get("arrSmartplugs") or []
    for plug in plugs:
        plug.setdefault("backend", "kasa")
        plug.setdefault("tapoCredentialId", str(uuid.uuid4()))
        plug.setdefault("tapoUsernameEnv", "TAPO_USERNAME")
        plug.setdefault("tapoPasswordEnv", "TAPO_PASSWORD")
        plug.setdefault("connect_on_connect", False)
        plug.setdefault("receives_led_commands", False)
        # 2.0 removed the old global monitoring switches. Transfer their effective
        # state so a previously disabled event cannot unexpectedly start switching.
        if legacy_base:
            for event in ("startup", "upload", "error", "disconnect", "shutdown"):
                enabled = settings.get("event_on_" + event + "_monitoring", False)
                plug["event_on_" + event] = bool(plug.get("event_on_" + event) and enabled)
            if not settings.get("powerOffWhenIdle", False):
                plug["automaticShutdownEnabled"] = False
        # Existing upstream device credentials move to the same private store.
        config = configs.get(plug["ip"], {})
        account = config.pop("credentials", None)
        if account and plug["tapoCredentialId"] not in accounts:
            accounts[plug["tapoCredentialId"]] = account
        # Preserve old timer settings for the explicit switching guard/UI. Never
        # convert a delayed shutdown into immediate power removal during migration.
        plug.setdefault("useCountdownRules", False)
        for field in ("tapoUsername", "tapoPassword", "tapoPasswordSet", "tapoClearCredentials"):
            plug.pop(field, None)
    for config in configs.values():
        config.pop("credentials", None)
    result.update(arrSmartplugs=plugs, tapoCredentials=accounts, device_configs=configs)
    return result
