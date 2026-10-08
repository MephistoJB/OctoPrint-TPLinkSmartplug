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
adding a second controller. Its version is `1.1.0rc1`. Updates point to this fork
so an upstream update cannot remove Tapo support. Plugin installation/activation
normally requires an OctoPrint restart; development and tests do not.

## Account and device settings

1. The Python interpreter running **OctoPrint** must be **3.11+**. An upgraded
   system Python alone is not enough. `tapo==0.11.1` is installed automatically on
   supported Python versions. Kasa support remains available on older Python.
2. Supply the Tapo account email and password to the OctoPrint **process
   environment**, as `TAPO_USERNAME` and `TAPO_PASSWORD`. Use the host's existing
   secret-management mechanism. The plugin does not save credentials in settings,
   send them to the browser, or log them. Do not put passwords in committed
   configuration or shell commands.
3. In Settings → TP-Link Smartplug, edit/add a plug, select **Tapo P110** and enter
   its IP or hostname without a `/1` socket suffix. The account variable fields
   contain **environment variable names**, never the actual email/password.
   Custom names can select different accounts for different plugs.
4. Disable **Use Timers** and save the main settings. Check status first, then
   test on/off while idle. Review Auto Connect/Disconnect, GCODE, startup and
   automatic shutdown options before enabling them.

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
  fixed diagnostic messages. Credentials remain only in process memory.
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
