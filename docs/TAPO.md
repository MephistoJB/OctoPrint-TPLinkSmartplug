# TP-Link 2.0 with Tapo P110 TPAP support

This contribution is based on the upstream 2.0 `rc` branch and retains upstream
release versioning and update sources. Its 2.0 integration has been tested with
fake devices, an offline browser fixture and a real P110 using TPAP on OctoPi
(OctoPrint 1.11.8, Python 3.11.2, armv7).
Migration from the earlier 1.x fork is supported; that version is preserved as the final
[1.1.0 release](https://github.com/MephistoJB/OctoPrint-TPLinkSmartplug/releases/tag/1.1.0).

## Which implementation is still needed?

- Upstream 2.0 already uses `python-kasa` for legacy Kasa and supported Tapo
  devices, discovery, lights, event switching and energy data. This branch uses
  those implementations rather than maintaining the old socket/encryption code.
- `python-kasa==0.11.0.1` supports AES, KLAP and XOR, but not TPAP. Its
  [TPAP issue](https://github.com/python-kasa/python-kasa/issues/1590) and
  [implementation PR](https://github.com/python-kasa/python-kasa/pull/1592) were
  still open when this branch was prepared. General P110 model support does not
  establish compatibility with every firmware protocol.
- The additional `tapo==0.11.1` transport therefore remains necessary for P110
  firmware using TPAP. A small device adapter connects it to the same 2.0
  switching paths. There is no automatic fallback or replay to another backend.
- This branch also keeps write-only credentials and controls in the sidebar for
  all plugs, including devices without energy readings.

## Requirements and device settings

OctoPrint itself must run on Python 3.11 or newer. Installation declares
`python-kasa>=0.11.0.1,<0.12` and `tapo==0.11.1`.

Select **python-kasa** for normal Kasa or Tapo devices supported by that library.
Select **Tapo P110 TPAP** for the additional transport. Enter its IP/hostname
without a socket suffix. A legacy Kasa device does not need account credentials.

Administrators can set an account per plug. The private account follows its
internal identifier if the IP changes. Leaving the password blank preserves it;
changing the email requires a new password. Removing the account is explicit.
The optional default account from upstream 2.0 is also write-only. Per-plug
credentials take priority over the default account. For TPAP only, environment
variables are a final fallback when no stored per-plug or default account exists.
The default names are `TAPO_USERNAME` and `TAPO_PASSWORD`.

Passwords and device authentication configurations are never returned in settings
or plug-list responses, copied into navbar data, or logged by these paths.
Credentials are stored on the OctoPrint host without plugin-level encryption.
New password inputs are cleared when settings close.

## Migration

Settings version **19** distinguishes this migration from both the 1.x fork and
upstream 2.0, which used settings version 18 for different changes.

- Migrates upstream 1.0.4, our 1.1.0/1.1.0rc3 configuration and upstream 2.0.
- Preserves plug identity, IP, label, stored accounts, connection delays and idle
  timeout values. Adds new 2.0 connection/light fields only where missing.
- Converts the old global event-monitor switches into the effective per-plug
  settings used by 2.0. A previously disabled monitor does not become enabled.
- Preserves the effective idle shutdown state when moving from 1.x.
- Moves upstream cached device credentials into the private per-plug store.
- Makes no device requests, switches no relay and issues no printer commands
  during migration. Device discovery occurs later when explicitly requested or
  needed for a device operation.
- Retains an old enabled countdown setting as a switching guard. Since 2.0
  removed device timers, an administrator must explicitly uncheck that setting
  before immediate switching is allowed. A delayed shutdown never silently
  becomes immediate power removal during migration.

## Supported behavior and limitations

Sidebar On/Off buttons preserve the configured off confirmation and require the
plugin control permission. HTTP failures release busy controls. Cancelling or
closing the sidebar off confirmation does not leave a pending request.

TPAP supports P110 on, off and status. It reports no invented energy readings.
Energy graphs remain available for devices that supply data through python-kasa.
Device countdown timers are unavailable in 2.0. Other Tapo models and TPAP strip
socket indices are outside this adapter's scope.

TPAP requests are serialized, with a 10-second operation timeout. The 2.0 adapter serializes
status and switching requests through a cancellation-aware async gate, so a
concurrent poll cannot suppress automatic power-off. A cancelled queued write
is removed before it is submitted to a thread. Direct concurrent writes outside
that gate are rejected. Failed TPAP writes
are not retried. Authentication failures block further requests for that account
until credentials change or settings are saved. A failed write is reported as
unknown instead of being hidden by a later successful status read. A timed-out
write may still have reached the device; check status before another attempt.
Upstream python-kasa manages its own internal protocol retry policy.

The 2.0 worker starts its event loop before accepting tasks and cancels pending
tasks before closing it. Device operations have bounded waits. Accounts/device
configuration are injected in memory for normal python-kasa connections.

## Validation and installation

```
python -m pip install OctoPrint uptime 'python-kasa>=0.11.0.1,<0.12' tapo==0.11.1 pytest
python -m pytest -q
node tests/test_frontend.js
```

Tests use fake devices and real OctoPrint settings persistence. They require no
real credentials or network devices. Browser validation uses an isolated local
page with the actual 2.0 templates and Knockout bindings.

Before a future installation: stop/finish prints, back up the complete OctoPrint
configuration, review enabled automations, install this branch and restart
OctoPrint. Enabling startup power-on will power the printer at that restart.
Then test the actual device, off confirmation, startup, upload and idle actions.
The P110 TPAP integration passed these physical checks:

- Installation and migration to settings version 19 preserved plug identity,
  stored credentials, connection delays and effective automation flags.
- On/Off, read-back, automatic connection/disconnection, startup power-on and
  credential persistence across service restarts worked.
- Sidebar On/Off and confirmation cancel/proceed worked in the real browser.
  Blank password saves preserved the account; cancelling settings cleared inputs.
  Passwords/private stores were absent from public APIs and account values were
  absent from plugin/installation logs.
- Automatic idle shutdown worked with concurrent status polling: a temporary
  one-minute idle interval and five-second cancellation window powered off in
  about 67 seconds. Original 30-minute settings were restored. An initial
  status/write conflict was fixed with the async gate and covered by regression
  tests; live timer interval changes now take effect immediately.
- Upload power-on was checked both disabled and temporarily enabled, using a
  comment-only file without selecting or printing it. The file was deleted and
  original flags restored. The final relay state was off and the printer offline.

The automated suite contains 97 tests and passed CI on Python 3.11 and 3.13.
These checks did not start a print, heat or move the printer. Other Kasa/Tapo
models and lighting operations have not been physically tested.

For an unreleased PR build, OctoPrint's release-channel switching may offer an
older upstream release as an update. Temporarily disable only this plugin's
update check while testing a PR to preserve the tested implementation; re-enable
it when a published release contains the changes.

Rollback requires reinstalling the 1.1.0 release **and restoring the pre-migration
configuration backup**. The same plugin identifier is used, so versions cannot be
installed side by side. The original account store is preserved, but converted
monitor flags and settings-version changes require restoring the backup.
