from unittest.mock import Mock

import pytest

from octoprint_tplinksmartplug.auto_connect import AutoConnect


@pytest.fixture
def setup():
    plugin = Mock()
    plug = {"ip": "192.0.2.1", "autoConnect": True, "autoConnectDelay": 10}
    plugin._settings.get.return_value = [plug]
    plugin.plug_search.return_value = plug
    plugin.check_status.return_value = {"currentState": "on"}
    printer = plugin._printer
    printer.is_operational.return_value = False
    printer.is_closed_or_error.return_value = True
    printer.is_error.return_value = False
    printer.get_connection_options.return_value = {
        "ports": ["/dev/ttyUSB0"], "portPreference": None,
        "baudratePreference": 250000,
    }
    clock = Mock(return_value=0)
    controller = AutoConnect(plugin, clock)
    return plugin, printer, controller, clock, plug


def test_external_power_on_waits_for_delay_and_usb(setup):
    plugin, printer, controller, clock, _ = setup
    plugin.check_status.return_value = {"currentState": "off"}
    controller.tick()
    plugin.check_status.return_value = {"currentState": "on"}
    controller.tick()
    clock.return_value = 9
    controller.tick()
    printer.connect.assert_not_called()
    clock.return_value = 10
    printer.get_connection_options.return_value["ports"] = []
    controller.tick()
    printer.connect.assert_not_called()
    clock.return_value = 20
    printer.get_connection_options.return_value["ports"] = ["/dev/ttyUSB0"]
    controller.tick()
    printer.connect.assert_called_once_with(port="AUTO", baudrate=250000)


def test_error_connection_is_released_before_retry(setup):
    _, printer, controller, clock, _ = setup
    controller.tick()
    clock.return_value = 10
    printer.is_error.return_value = True
    controller.tick()
    assert [c[0] for c in printer.mock_calls][-3:] == [
        "disconnect", "is_closed_or_error", "connect"]
    clock.return_value = 24
    controller.tick()
    assert printer.connect.call_count == 1
    clock.return_value = 25
    controller.tick()
    assert printer.connect.call_count == 2


@pytest.mark.parametrize("state", ["off", "unknown"])
def test_no_connection_when_power_off_or_unconfirmed(setup, state):
    plugin, printer, controller, clock, _ = setup
    controller.tick()
    clock.return_value = 10
    plugin.check_status.return_value = {"currentState": state}
    controller.tick()
    printer.connect.assert_not_called()


def test_connected_printer_and_manual_disconnect_are_respected(setup):
    _, printer, controller, clock, _ = setup
    controller.tick()
    clock.return_value = 10
    printer.is_operational.return_value = True
    printer.is_closed_or_error.return_value = False
    controller.tick()
    printer.is_operational.return_value = False
    printer.is_closed_or_error.return_value = True
    clock.return_value = 20
    controller.tick()
    printer.connect.assert_not_called()
    printer.disconnect.assert_not_called()


def test_retry_limit_and_new_power_cycle(setup):
    plugin, printer, controller, clock, _ = setup
    controller.tick()
    for n in range(12):
        clock.return_value = 10 + n * 15
        controller.tick()
    assert printer.connect.call_count == 6
    plugin.check_status.return_value = {"currentState": "off"}
    controller.tick()
    plugin.check_status.return_value = {"currentState": "on"}
    controller.tick()
    clock.return_value += 10
    controller.tick()
    assert printer.connect.call_count == 7


def test_disabled_option_cancels_pending_connection(setup):
    _, printer, controller, clock, plug = setup
    controller.tick()
    plug["autoConnect"] = False
    clock.return_value = 10
    controller.tick()
    assert not controller.pending
    printer.connect.assert_not_called()


def test_configured_port_must_be_present(setup):
    _, printer, controller, clock, _ = setup
    controller.tick()
    printer.get_connection_options.return_value["portPreference"] = "/dev/ttyACM0"
    clock.return_value = 10
    controller.tick()
    printer.connect.assert_not_called()
    printer.get_connection_options.return_value["ports"].append("/dev/ttyACM0")
    controller.tick()
    printer.connect.assert_called_once_with(port="/dev/ttyACM0", baudrate=250000)


def test_connecting_is_never_interrupted(setup):
    _, printer, controller, clock, _ = setup
    controller.tick()
    clock.return_value = 10
    printer.is_closed_or_error.return_value = False
    controller.tick()
    printer.disconnect.assert_not_called()
    printer.connect.assert_not_called()


def test_usb_wait_has_bounded_deadline(setup):
    _, printer, controller, clock, _ = setup
    printer.get_connection_options.return_value["ports"] = []
    controller.tick()
    clock.return_value = 191
    controller.tick()
    assert not controller.pending
    printer.connect.assert_not_called()
