# OctoPrint-TPLinkSmartplug — 2.0 migration branch

This branch integrates upstream 2.0 and keeps the additional **Tapo P110 TPAP**
transport for firmware that `python-kasa` does not yet support. Normal Kasa and
supported Tapo devices use upstream's new python-kasa connection, discovery,
event handling, light support and energy graphs.

It also preserves write-only account settings, sidebar On/Off controls, and
adds migration from the tested 1.x fork without silently enabling automations.
Python 3.11 or newer is required.

**This is a prepared development version, not an installed OctoPi update.**
The tested final version remains [1.1.0](https://github.com/MephistoJB/OctoPrint-TPLinkSmartplug/releases/tag/1.1.0).

See [configuration, protocol comparison, migration, validation and rollback](docs/TAPO.md).

The upstream project is [jneilliii/OctoPrint-TPLinkSmartplug](https://github.com/jneilliii/OctoPrint-TPLinkSmartplug).
Licensed under AGPLv3.
