"""Keep write-only credentials separate from public plug settings."""
import copy
import uuid

FORM_FIELDS = ("tapoUsername", "tapoPassword", "tapoPasswordSet", "tapoClearCredentials")


def public_plugs(plugs, credentials, admin=False):
    result = copy.deepcopy(plugs)
    for plug in result:
        for field in FORM_FIELDS:
            plug.pop(field, None)
        if admin:
            account = credentials.get(plug.get("tapoCredentialId"), {})
            plug.update(tapoUsername=account.get("username", ""), tapoPassword="",
                        tapoPasswordSet=bool(account.get("password")), tapoClearCredentials=False)
    return result


def prepare_settings(data, current_plugs, credentials, admin):
    """Validate the complete update before changing any persistent setting."""
    clean = copy.deepcopy(data)
    clean.pop("tapoCredentials", None)  # API clients cannot overwrite the private store directly.
    accounts = copy.deepcopy(credentials)
    if "arrSmartplugs" not in clean:
        return clean, accounts
    previous_ids = {plug["ip"]: plug.get("tapoCredentialId") for plug in current_plugs}
    used_ids = set()
    for plug in clean["arrSmartplugs"]:
        submitted = any(field in plug for field in FORM_FIELDS)
        if submitted and not admin:
            raise PermissionError("Only administrators can configure Tapo credentials.")
        identifier = plug.get("tapoCredentialId") or previous_ids.get(plug["ip"]) or str(uuid.uuid4())
        if identifier in used_ids:
            raise ValueError("Each plug must have a separate credential identifier.")
        used_ids.add(identifier)
        plug["tapoCredentialId"] = identifier
        old = accounts.get(identifier, {})
        if plug.get("tapoClearCredentials") is True:
            accounts.pop(identifier, None)
        else:
            username = plug.get("tapoUsername", old.get("username", ""))
            password = plug.get("tapoPassword", "")
            if not isinstance(username, str) or not isinstance(password, str):
                raise ValueError("Tapo email and password must be text.")
            username = username.strip()
            if password:
                if not username:
                    raise ValueError("Enter the Tapo account email before saving a new password.")
                accounts[identifier] = {"username": username, "password": password}
            elif username != old.get("username", ""):
                raise ValueError("Enter a new password when changing the Tapo account email, or explicitly remove the stored credentials.")
        for field in FORM_FIELDS:
            plug.pop(field, None)
    # Removing a plug also removes its otherwise orphaned account credentials.
    accounts = {key: value for key, value in accounts.items() if key in used_ids}
    return clean, accounts
