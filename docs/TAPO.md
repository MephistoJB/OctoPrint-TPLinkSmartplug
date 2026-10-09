# Tapo P110 configuration

This fork supports P110 on/off and status through `tapo==0.11.1`, including the
TPAP protocol used by current firmware. Existing Kasa plugs keep their original
communication protocol and configuration.

## Installation

Finish all prints first. Install this fork through OctoPrint's Plugin Manager:

```
https://github.com/MephistoJB/OctoPrint-TPLinkSmartplug/archive/refs/heads/feature/tapo-p110-tpap.zip
```

The identifier is unchanged, so this replaces the original plugin rather than
adding a second controller. Its version is `1.1.0rc3`. Updates point to this fork
so an upstream update cannot remove Tapo support. Plugin installation/activation
normally requires an OctoPrint restart; development and tests do not.

## Account and device settings

1. The Python interpreter running **OctoPrint** must be **3.11+**. An upgraded
   system Python alone is not enough. `tapo==0.11.1` is installed automatically on
   supported Python versions. Kasa support remains available on older Python.
2. In Settings → TP-Link Smartplug, edit/add a plug, select **Tapo P110** and
   enter its IP or hostname without a `/1` socket suffix.
3. Administrators can enter the **Tapo account email and password** directly in
   the plug editor. Save the main settings. Credentials persist in the OctoPrint
   configuration on the host; the plugin does not encrypt this local store.
   The password is never returned by the settings or plug-list API and is never
   written to plugin logs. The browser receives only the account email and a
   "Password saved" indicator. An empty password field preserves the saved
   password. Changing the account email requires entering its password again.
4. To remove a stored account, select **Remove stored account credentials** and
   save. Removing a plug also removes its private credentials. IP address changes
   keep the saved account, using an internal identifier rather than the address.
5. Environment-based setup remains available under **Advanced**. If no account
   is stored, the plugin reads the variables named there, defaulting to
   `TAPO_USERNAME` and `TAPO_PASSWORD`. Saved credentials take priority; the two
   sources are not mixed. Removing the saved account restores environment mode.
6. Disable **Use Timers**. Check status first, then test on/off while idle. Review
   Auto Connect/Disconnect, GCODE, startup and automatic shutdown options before
   enabling them.

## Supported functions and limitations

- P110 on, off and status polling, including the existing event/GCODE switching
  paths. Other Tapo models and strip socket indices are outside this release.
- Tapo device countdown timers and energy charts are not implemented.
  Timer-enabled Tapo switching is rejected before printer/system side effects;
  it never silently becomes an immediate power-off.
- Requests run in a serial worker, outside OctoPrint's event loop, with a fresh
  login/session and a 10-second coroutine timeout. Failed writes are not replayed.
  After a timeout the state is unknown: a device may have acted before losing
  its reply. Check status before deciding whether to switch again.
- Authentication failures block further attempts for that host/account until
  credentials change or settings are saved. Correct the account, or wait for a
  device login lock to expire, before saving/retrying.
- Library exception details are never logged or sent to the browser; errors are
  fixed diagnostic messages. New passwords are cleared from the browser model
  when the settings dialog closes and are omitted from navbar plug data.
- Commands go to the local plug IP, with no cloud API used for switching. Login
  still requires the existing Tapo account credentials.

## Development and validation

```
python -m pip install OctoPrint uptime tapo==0.11.1 pytest
python -m pytest -q
```

Tests use fake devices for the transport and the real OctoPrint plugin for Kasa
regression, migration, routing, timer guards and failed-write handling. They make
no network requests and need no real credentials.

## Rollback

Back up your OctoPrint configuration. Reinstall the upstream plugin with its
original Plugin Manager URL, and restart OctoPrint while idle. The upstream
version cannot operate Tapo plugs; do not change their type to Kasa.

The TP-Link Smartplug sidebar lists every configured plug, including Tapo plugs without energy readings. Use On and Off there to switch the relay; Off retains the configured confirmation dialog. Status updates after switching and through the refresh icon. Controls require the plugin control permission and are disabled while a request is pending.
