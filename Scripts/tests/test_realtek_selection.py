"""Which Realtek the launcher drives when several carry the DarkFirmware address.

pi0-2 has four. On 2026-11-17 the launcher switched from hci4 to hci3 after a
power cycle, BlueZ had no adapter for hci3, and discovery never resumed.
"""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import central_app_launcher as cal


class Host:
    """A fake host: {hciN: USB port} of the dongles with the sentinel address."""
    def __init__(self, dongles, managed=()):
        self.dongles, self.managed = dict(dongles), set(managed)

    def patches(self):
        return (patch.object(cal, '_sentinel_hcis', side_effect=lambda: list(self.dongles)),
                patch.object(cal, '_hci_usb_id', side_effect=lambda hci: self.dongles.get(hci)),
                patch.object(cal, '_bluez_manages', side_effect=lambda hci: hci in self.managed),
                patch.object(cal, '_realtek_pinned_usb', None),
                patch.object(cal, '_realtek_other_usb', set()),
                contextlib.redirect_stdout(io.StringIO()))


class RealtekSelectionTests(unittest.TestCase):
    def host(self, dongles, managed=()):
        host = Host(dongles, managed)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for p in host.patches():
            stack.enter_context(p)
        return host

    def test_one_dongle_is_found_wherever_it_is(self):
        host = self.host({'hci0': '1-1.3'})
        self.assertEqual(cal.find_realtek_hci(), ('hci0', '/org/bluez/hci0'))
        host.dongles = {}                                   # power cycle: gone
        self.assertEqual(cal.find_realtek_hci(), (None, None))
        host.dongles = {'hci1': '1-1.3'}                    # back, renumbered
        self.assertEqual(cal.find_realtek_hci(), ('hci1', '/org/bluez/hci1'))
        host.dongles = {'hci2': '1-1.2'}                    # replugged in another port
        self.assertEqual(cal.find_realtek_hci(), ('hci2', '/org/bluez/hci2'))
        self.assertFalse(cal._realtek_other_usb)

    def test_with_several_it_takes_the_one_bluez_manages_and_keeps_to_its_port(self):
        four = {'hci4': '1-1.4.4', 'hci3': '1-1.4.2', 'hci2': '1-1.3', 'hci1': '1-1.1'}
        host = self.host(four, managed={'hci2'})
        self.assertEqual(cal.find_realtek_hci(), ('hci2', '/org/bluez/hci2'))   # not the first listed
        self.assertEqual(cal._realtek_other_usb, {'1-1.4.4', '1-1.4.2', '1-1.1'})
        # Power cycle: our dongle is away and the others are still listed.
        host.dongles = {hci: port for hci, port in four.items() if hci != 'hci2'}
        for _ in range(3):
            self.assertEqual(cal.find_realtek_hci(), (None, None))             # never hci4 or hci3
        # It comes back on the same port under another number.
        host.dongles = {'hci5': '1-1.3', **host.dongles}
        self.assertEqual(cal.find_realtek_hci(), ('hci5', '/org/bluez/hci5'))
        self.assertEqual(cal._realtek_pinned_usb, '1-1.3')

    def test_it_waits_while_bluez_has_registered_none_of_several(self):
        host = self.host({'hci2': '1-1.3', 'hci1': '1-1.1'})
        self.assertEqual(cal.find_realtek_hci(), (None, None))
        self.assertIsNone(cal._realtek_pinned_usb)
        host.managed = {'hci1'}
        self.assertEqual(cal.find_realtek_hci(), ('hci1', '/org/bluez/hci1'))

    def test_without_busctl_it_falls_back_to_the_first_listed(self):
        self.host({'hci2': '1-1.3', 'hci1': '1-1.1'})
        with patch.object(cal, '_bluez_manages', return_value=None):
            self.assertEqual(cal.find_realtek_hci(), ('hci2', '/org/bluez/hci2'))

    def test_lmp_tool_is_told_which_dongle_only_when_there_are_several(self):
        from novelty.discovery import Report
        from queue import Queue
        for dongles, managed, expect in (({'hci0': '1-1.3'}, {'hci0'}, None),
                                         ({'hci4': '1-1.4.4', 'hci3': '1-1.4.2'}, {'hci4'}, '--hci=hci4')):
            with self.subTest(dongles=len(dongles)), contextlib.ExitStack() as stack:
                for p in Host(dongles, managed).patches():
                    stack.enter_context(p)
                for name in ('btc_bdaddrs', 'device_connect_attempts', 'device_total_attempts', 'device_last_seen',
                             'sdp_success_bdaddrs', 'lmp2thprint_success_bdaddrs', 'ble_address_types'):
                    stack.enter_context(patch.object(cal, name, {}))
                stack.enter_context(patch.object(cal, 'novelty_mode', False))
                stack.enter_context(patch.object(cal, '_lmp_invocations_since_cycle', 0))
                cal.find_realtek_hci()
                launched = []

                class Done:
                    def __init__(self, process, bdaddr, info_type, **kwargs):
                        self.bdaddr, self.info_type = bdaddr, info_type
                    def start(self):
                        store = cal.lmp2thprint_success_bdaddrs if self.info_type == 'LMP2thprint' else cal.sdp_success_bdaddrs
                        store[self.bdaddr] = 1
                        if self.info_type != 'LMP2thprint':
                            cal.btc_bdaddrs.pop(self.bdaddr, None)
                    def join(self): pass

                class Stop(BaseException): pass
                cal._handle_discovery_report(Report('ce:00:00:00:00:01', 'public', 'BTC', -50, ()))
                with patch.object(cal.subprocess, 'Popen', side_effect=lambda cmd, **kw: launched.append(cmd) or type('P', (), {'pid': 1})()), \
                     patch.object(cal, 'ApplicationThread', Done), patch.object(cal, 'external_log_write'), \
                     patch.object(cal, 'cycle_realtek_adapter'), patch.object(cal.time, 'sleep', side_effect=Stop):
                    with self.assertRaises(Stop):
                        cal.btc_thread_function()
                lmp = next(cmd for cmd in launched if 'DarkFirmware_VSC_LMP' in cmd[0])
                self.assertEqual([arg for arg in lmp if arg.startswith('--hci')], [expect] if expect else [])


if __name__ == '__main__':
    unittest.main()
