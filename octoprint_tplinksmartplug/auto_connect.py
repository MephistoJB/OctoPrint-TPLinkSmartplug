"""Connect once per power cycle, allowing time for the printer's USB startup."""

import threading
import time


class AutoConnect:
    WINDOW = 180
    RETRY_DELAY = 15
    MAX_ATTEMPTS = 6

    def __init__(self, plugin, clock=time.monotonic):
        self.plugin = plugin
        self.clock = clock
        self.lock = threading.RLock()
        self.states = {}
        self.pending = {}

    def observe(self, ip, state, explicit=False):
        with self.lock:
            plug = self.plugin.plug_search(
                self.plugin._settings.get(["arrSmartplugs"]), "ip", ip)
            if not plug or not plug.get("autoConnect"):
                self.pending.pop(ip, None)
                self.states.pop(ip, None)
                return
            if state not in ("on", "off"):
                return
            previous = self.states.get(ip)
            self.states[ip] = state
            if state == "off":
                self.pending.pop(ip, None)
            elif (previous != "on" or explicit) and ip not in self.pending:
                if self.plugin._printer.is_closed_or_error():
                    now = self.clock()
                    delay = max(0, int(plug.get("autoConnectDelay", 10)))
                    self.pending[ip] = [now + delay, now + delay + self.WINDOW, 0]

    def clear(self):
        with self.lock:
            self.pending.clear()
            self.states.clear()

    def connected(self):
        with self.lock:
            self.pending.clear()

    def tick(self):
        plugs = self.plugin._settings.get(["arrSmartplugs"]) or []
        enabled = {p["ip"] for p in plugs if p.get("autoConnect")}
        with self.lock:
            for ip in set(self.states) - enabled:
                self.states.pop(ip, None)
                self.pending.pop(ip, None)
        for ip in enabled:
            status = self.plugin.check_status(ip)
            self.observe(ip, status.get("currentState"))
            with self.lock:
                attempt = self.pending.get(ip)
                if not attempt:
                    continue
                printer = self.plugin._printer
                if printer.is_operational():
                    self.pending.pop(ip, None)
                    continue
                now = self.clock()
                if now >= attempt[1] or attempt[2] >= self.MAX_ATTEMPTS:
                    self.pending.pop(ip, None)
                    self.plugin._logger.warning("Automatic printer connection timed out for %s", ip)
                    continue
                if status.get("currentState") != "on" or now < attempt[0]:
                    continue
                if not printer.is_closed_or_error():
                    continue
                options = printer.get_connection_options()
                port = options.get("portPreference")
                ports = options.get("ports") or []
                if not ports or (port and port != "AUTO" and port not in ports):
                    continue
                attempt[0] = now + self.RETRY_DELAY
                attempt[2] += 1
                try:
                    # OctoPrint retains the communication object after a serial error.
                    # connect() alone would then silently return without reconnecting.
                    if printer.is_error():
                        printer.disconnect()
                    if printer.is_closed_or_error():
                        printer.connect(port=port or "AUTO", baudrate=options.get("baudratePreference"))
                        self.plugin._logger.info("Automatic printer connection attempt %s for %s", attempt[2], ip)
                except Exception:
                    self.plugin._logger.warning("Automatic printer connection attempt failed for %s", ip)
