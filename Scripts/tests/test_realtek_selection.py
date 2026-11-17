"""Which Realtek the launcher drives when several carry the DarkFirmware address.

pi0-2 has four. On 2026-11-17 the launcher switched from hci4 to hci3 after a
power cycle, BlueZ had no adapter for hci3, and discovery never resumed.

The same day on pi0-3 the dongle's firmware stopped answering, the kernel reset
it, and it sat on its port with address 00:00:00:00:00:00. The launcher, which
looked for it by address, never power cycled it, and discovery stayed dead.
"""
import asyncio
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


FOUR = {'hci4': '1-1.4.4', 'hci3': '1-1.4.2', 'hci2': '1-1.3', 'hci1': '1-1.1'}


class WedgedRealtekTests(unittest.TestCase):
    """Our dongle is on its USB port but no longer carries the address."""
    def setUp(self):
        self.host = Host(FOUR, managed={'hci4'})
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for p in self.host.patches():
            self.stack.enter_context(p)
        self.on_port = True
        self.stack.enter_context(patch.object(cal, '_usb_device_present', side_effect=lambda port: self.on_port))
        self.stack.enter_context(patch.object(cal, '_hub_supports_ppps', return_value=True))
        self.stack.enter_context(patch.object(cal, '_realtek_cycle_disabled', False))
        self.stack.enter_context(patch.object(cal, '_realtek_consecutive_cycle_failures', 0))
        self.stack.enter_context(patch.object(cal, '_realtek_hci_current_path', '/org/bluez/hci4'))
        self.stack.enter_context(patch.object(cal.time, 'sleep'))
        cal._realtek_cycle_pending.clear()
        self.addCleanup(cal._realtek_cycle_pending.clear)
        self.assertEqual(cal.find_realtek_hci(), ('hci4', '/org/bluez/hci4'))      # pins 1-1.4.4
        self.commands = []

    def wedge(self):
        """The kernel reset it: same port, new hci number, no DarkFirmware address."""
        self.host.dongles = {hci: port for hci, port in FOUR.items() if hci != 'hci4'}
        self.host.managed = set()

    def run_command(self, command, **kwargs):
        self.commands.append(command)
        if command[0] == 'uhubctl':                       # cold boot: firmware and address are back
            self.host.dongles = {'hci5': '1-1.4.4', **self.host.dongles}
            self.host.managed = {'hci5'}
        return type('Done', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

    def test_the_pinned_port_is_still_known_while_the_address_is_gone(self):
        self.assertEqual(cal._realtek_sysfs_id(), '1-1.4.4')
        self.wedge()
        self.assertEqual(cal.find_realtek_hci(), (None, None))
        self.assertEqual(cal._realtek_sysfs_id(), '1-1.4.4')
        self.assertEqual(cal.find_realtek_hub_and_port(), ('1-1.4', '4'))
        self.on_port = False                               # unplugged: nothing to cycle
        self.assertIsNone(cal._realtek_sysfs_id())
        self.assertEqual(cal.find_realtek_hub_and_port(), (None, None))

    def test_a_power_cycle_brings_it_back_and_restarts_discovery(self):
        self.wedge()
        with patch.object(cal.subprocess, 'run', side_effect=self.run_command):
            cal.cycle_realtek_adapter()
        self.assertEqual(self.commands[0], ['uhubctl', '-l', '1-1.4', '-p', '4', '-a', 'cycle'])
        self.assertTrue(cal._realtek_cycle_pending.is_set())
        self.assertEqual(cal.get_realtek_dbus_path(), '/org/bluez/hci5')
        self.assertEqual(cal._realtek_consecutive_cycle_failures, 0)
        self.assertEqual(cal.find_realtek_hci(), ('hci5', '/org/bluez/hci5'))

    def test_the_watchdog_cycles_it_after_two_looks_and_only_when_that_can_help(self):
        look = lambda misses: asyncio.run(cal._realtek_watchdog(misses))
        with patch.object(cal, 'cycle_realtek_adapter') as cycle:
            self.assertEqual(look(1), 0)                   # present: the count starts over
            self.wedge()
            self.assertEqual(look(0), 1)                   # one look proves nothing (it may be mid-cycle)
            cycle.assert_not_called()
            self.assertEqual(look(1), 0)
            cycle.assert_called_once()
            cycle.reset_mock()
            self.on_port = False                           # unplugged: wait, do not count failed cycles
            self.assertEqual(look(1), 0)
            self.on_port = True
            with cal._realtek_cycle_lock:                  # the BTC worker is cycling it right now
                self.assertEqual(look(1), 0)
            with patch.object(cal, '_realtek_cycle_disabled', True):
                self.assertEqual(look(1), 0)
            cycle.assert_not_called()

    def test_nothing_is_probed_through_another_adapter_while_it_is_away(self):
        from novelty.discovery import Report
        self.wedge()
        for name in ('btc_bdaddrs', 'device_connect_attempts', 'device_total_attempts', 'device_last_seen',
                     'sdp_success_bdaddrs', 'lmp2thprint_success_bdaddrs', 'ble_address_types'):
            self.stack.enter_context(patch.object(cal, name, {}))
        self.stack.enter_context(patch.object(cal, 'novelty_mode', False))
        self.stack.enter_context(patch.object(cal, '_lmp_invocations_since_cycle', 0))
        self.stack.enter_context(patch.object(cal.time, 'sleep', side_effect=Stop))
        target = 'ce:00:00:00:00:01'
        cal._handle_discovery_report(Report(target, 'public', 'BTC', -50, ()))
        with patch.object(cal.subprocess, 'Popen') as spawn, patch.object(cal, 'external_log_write') as log, \
             patch.object(cal, 'cycle_realtek_adapter'):
            # One pass over the queue: the second look at the same device ends the replay.
            passes = iter([cal._candidate_skip_reason, Stop])
            real = cal._candidate_skip_reason
            def once_then_stop(*args):
                if next(passes) is Stop:
                    raise Stop
                return real(*args)
            with patch.object(cal, '_candidate_skip_reason', side_effect=once_then_stop):
                with self.assertRaises(Stop):
                    cal.btc_thread_function()
        self.assertEqual(spawn.call_count, 0)              # neither LMP nor SDP
        self.assertFalse(log.called)                       # and no attempt written to the logs
        self.assertEqual((cal.device_connect_attempts[target], cal.device_total_attempts[target]), (0, 0))
        self.assertIn(target, cal.btc_bdaddrs)             # still a candidate for when the dongle is back


class Stop(BaseException):
    pass


if __name__ == '__main__':
    unittest.main()
