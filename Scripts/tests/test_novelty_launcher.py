"""QA replay through the real launcher queues, worker loops and spawn boundary.

Only the operating-system process/radio boundary is faked. The same raw reports
are exercised with novelty_mode both True and False on both transports.
"""
from collections import OrderedDict
import contextlib
import io
from pathlib import Path
from queue import Queue
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import central_app_launcher as cal
from novelty.discovery import Report, parse_event
from novelty.rules import AdvertisementEvidence, NoveltyRules
from test_novelty_rules import ad, sd, ADDRESS, PRIVATE_DIR, HAVE_PRIVATE_RULES
from test_novelty_discovery import legacy, inquiry, monitor


class StopWorker(BaseException):
    pass


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        for name in ('ble_bdaddrs','btc_bdaddrs','ble_gatt_value_deprioritized_bdaddrs','ble_address_types',
                     'gatt_success_bdaddrs','sdp_success_bdaddrs','lmp2thprint_success_bdaddrs',
                     'device_connect_attempts','device_total_attempts','device_last_seen'):
            self.stack.enter_context(patch.object(cal,name,{}))
        self.stack.enter_context(patch.object(cal,'gatt_force_read_bdaddrs',set()))
        self.stack.enter_context(patch.object(cal,'bg_inflight_bdaddrs',set()))
        self.stack.enter_context(patch.object(cal,'novelty_evidence',AdvertisementEvidence(NoveltyRules())))
        self.stack.enter_context(patch.object(cal,'novelty_remembered',OrderedDict()))
        self.stack.enter_context(patch.object(cal,'novelty_mode',True))
        self.stack.enter_context(patch.object(cal,'skip_these_addresses',[]))
        self.stack.enter_context(patch.object(cal,'print_verbose',False))
        self.stack.enter_context(patch.object(cal,'print_skipped',False))
        self.stack.enter_context(patch.object(cal,'_lmp_invocations_since_cycle',0))
        self.stack.enter_context(patch.object(cal,'better_getter_enabled',True))
        self.stack.enter_context(patch.object(cal,'lmp2thprint_enabled',True))
        self.stack.enter_context(patch.object(cal,'btc_sdp_gatt_enabled',True))
        queue=Queue();queue.put('/fake/sonoff')
        self.stack.enter_context(patch.object(cal,'bg_dongle_queue',queue))

    def feed(self, raw, kind='BLE', address=ADDRESS):
        packet=legacy(raw) if kind=='BLE' else inquiry(raw)
        report=parse_event(packet)[0]
        # Give each replay candidate a distinct, synthetic non-vendor address.
        report=Report(address,report.address_type,kind,report.rssi,report.frames,report.connectable)
        cal._handle_discovery_report(report)
        return report

    def test_on_off_raw_report_to_worker_subprocesses(self):
        packets=[ad(9,'Novel Sensor'),ad(9,'LE-WH-CH720N'),ad(9,'LE_WH-1000XM4'),
                 ad(9,'S21 FE de Silva'),sd(0xfcf1),ad(9,'TELLURIDE Digital Key'),
                 ad(255,bytes.fromhex('4c001005')),ad(255,b'\x75\x00\x01'),
                 ad(255,bytes.fromhex('2d0104000202b03108')+bytes(13)),
                 ad(9,'BYD Key'),ad(9,'NKEY eLatch')]
        for enabled in (True,False):
            for kind in ('BLE','BTC'):
                with self.subTest(novelty_mode=enabled,transport=kind):
                    cal.novelty_mode=enabled
                    for store in (cal.ble_bdaddrs,cal.btc_bdaddrs,cal.gatt_success_bdaddrs,
                                  cal.sdp_success_bdaddrs,cal.lmp2thprint_success_bdaddrs,
                                  cal.device_connect_attempts,cal.device_total_attempts): store.clear()
                    addresses=[f'ce:00:00:00:01:{n:02x}' for n in range(len(packets))]
                    for address,raw in zip(addresses,packets): self.feed(raw,kind,address)
                    launched=[]
                    opened_outputs=[]
                    def popen(cmd,**kwargs):
                        launched.append(cmd)
                        if kwargs.get("stdout"): opened_outputs.append(kwargs["stdout"])
                        return type('Process',(),{'pid':100})()
                    class FakeThread:
                        is_terminated=True
                        def __init__(self,process,bdaddr,info_type,**kwargs):
                            self.bdaddr,self.info_type,self.kwargs=bdaddr,info_type,kwargs
                        def start(self):
                            if self.info_type=='GATT':
                                cal.gatt_success_bdaddrs[self.bdaddr]=1
                                cal.ble_bdaddrs.pop(self.bdaddr,None)
                                cal.bg_inflight_bdaddrs.discard(self.bdaddr)
                                cal.bg_dongle_queue.put(self.kwargs['bg_dongle_path'])
                            elif self.info_type=='LMP2thprint':
                                cal.lmp2thprint_success_bdaddrs[self.bdaddr]=1
                            else:
                                cal.sdp_success_bdaddrs[self.bdaddr]=1
                                cal.btc_bdaddrs.pop(self.bdaddr,None)
                        def join(self): pass
                    with patch.object(cal.subprocess,'Popen',side_effect=popen), patch.object(cal,'ApplicationThread',FakeThread), \
                         patch.object(cal,'external_log_write'), patch.object(cal,'cycle_realtek_adapter'), \
                         patch.object(cal.time,'sleep',side_effect=StopWorker):
                        with self.assertRaises(StopWorker):
                            (cal.ble_thread_function if kind=='BLE' else cal.btc_thread_function)()
                    actual={item.split('=',1)[1] for cmd in launched for item in cmd if item.startswith(('-b=','--bdaddr=','--target='))}
                    expected={addresses[n] for n in (0,9,10)} if enabled else set(addresses)
                    self.assertEqual(actual,expected)
                    self.assertEqual(len(launched),len(expected)*(1 if kind=='BLE' else 2))
                    # Better_Getter's own skip-Apple early exit is one of the skipping
                    # mechanisms: on with novelty mode, absent without it, never on BTC tools.
                    self.assertEqual({'-A' in cmd for cmd in launched},{enabled and kind=='BLE'})
                    self.assertTrue(all(stream.closed for stream in opened_outputs))

    def run_ble_worker(self, dongles=2, finish=lambda bdaddr: None):
        """Drive the real BLE worker loop. Better_Getter runs stay in flight until the
        loop sleeps; each sleep ends the in-flight runs as failures. A sleep with
        nothing in flight means the loop is idle, which ends the replay."""
        queue=Queue()
        for n in range(dongles): queue.put(f'/fake/sonoff{n}')
        launched,running=[],{}
        class FakeThread:
            is_terminated=False
            def __init__(self,process,bdaddr,info_type,**kwargs):
                self.bdaddr,self.kwargs=bdaddr,kwargs
            def start(self): running[self.bdaddr]=self.kwargs['bg_dongle_path']
        def sleep(_):
            if not running: raise StopWorker
            for bdaddr,dongle in list(running.items()):
                finish(bdaddr)
                cal.bg_inflight_bdaddrs.discard(bdaddr)
                queue.put(dongle)
                del running[bdaddr]
        def popen(cmd,**kwargs):
            launched.append(cmd)
            return type('Process',(),{'pid':100})()
        with patch.object(cal,'bg_dongle_queue',queue), patch.object(cal.subprocess,'Popen',side_effect=popen), \
             patch.object(cal,'ApplicationThread',FakeThread), patch.object(cal,'external_log_write'), \
             patch.object(cal.time,'sleep',side_effect=sleep):
            with self.assertRaises(StopWorker):
                cal.ble_thread_function()
        return launched

    def test_run_still_in_flight_is_one_attempt_not_three(self):
        """With a spare dongle the loop comes straight back to an address whose
        Better_Getter is still running. That is the same attempt: counting it again
        spent the whole retry budget on one 20-second run, permanently."""
        for enabled in (True,False):
            with self.subTest(novelty_mode=enabled):
                cal.novelty_mode=enabled
                for store in (cal.ble_bdaddrs,cal.device_connect_attempts,cal.device_total_attempts): store.clear()
                self.feed(ad(9,'Novel Sensor'))
                launched=self.run_ble_worker(dongles=2)
                self.assertEqual(len(launched),cal.max_connect_attempts)
                self.assertEqual(cal.device_connect_attempts[ADDRESS],cal.max_connect_attempts)
                self.assertEqual(cal.device_total_attempts[ADDRESS],cal.max_connect_attempts)
                # ...and after that many real failures it is skipped thereafter.
                self.assertNotIn(ADDRESS,cal.ble_bdaddrs)
                self.assertEqual(cal._candidate_skip_reason('BLE',ADDRESS,'random'),'retry limit')
                self.feed(ad(9,'Novel Sensor'))
                self.assertNotIn(ADDRESS,cal.ble_bdaddrs)

    def test_success_is_not_retried_and_other_candidates_still_run(self):
        other='ce:00:00:00:00:02'
        self.feed(ad(9,'Novel Sensor'))
        self.feed(ad(9,'Other Sensor'),address=other)
        def finish(bdaddr):
            if bdaddr==ADDRESS:
                cal.gatt_success_bdaddrs[bdaddr]=1
                cal.ble_bdaddrs.pop(bdaddr,None)
        launched=self.run_ble_worker(dongles=3,finish=finish)
        targets=[item for cmd in launched for item in cmd if item.startswith('-b=')]
        self.assertEqual(targets.count(f'-b={ADDRESS}'),1)
        self.assertEqual(targets.count(f'-b={other}'),cal.max_connect_attempts)
        self.assertEqual(cal._candidate_skip_reason('BLE',ADDRESS,'random'),'already completed')

    def test_late_evidence_while_waiting_for_a_dongle_is_not_an_attempt(self):
        """A scan response that arrives while the worker waits for a dongle cancels
        the probe. No connection was tried, so the retry budget is untouched."""
        late=ad(9,'LE-WH-CH720N')
        for withdraw in ('report handler dequeues','launch gate refuses'):
            with self.subTest(path=withdraw):
                cal.novelty_mode=True
                for store in (cal.ble_bdaddrs,cal.device_connect_attempts,cal.device_total_attempts): store.clear()
                cal.novelty_evidence.entries.clear();cal.novelty_remembered.clear()
                self.feed(ad(9,'Novel Sensor'))
                class LateQueue(Queue):
                    def get(queue,*args,**kwargs):
                        if withdraw=='report handler dequeues':
                            self.feed(late)
                        else:  # evidence recorded, candidate not yet dequeued
                            cal.novelty_evidence.observe(ADDRESS,'random','BLE',parse_event(legacy(late))[0].frames)
                        return Queue.get(queue,*args,**kwargs)
                queue=LateQueue();queue.put('/fake/sonoff')
                with patch.object(cal,'bg_dongle_queue',queue), patch.object(cal.subprocess,'Popen') as spawn, \
                     patch.object(cal,'external_log_write'), patch.object(cal.time,'sleep',side_effect=StopWorker):
                    with self.assertRaises(StopWorker):
                        cal.ble_thread_function()
                self.assertEqual(spawn.call_count,0)
                self.assertEqual(cal.device_connect_attempts[ADDRESS],0)
                self.assertEqual(cal.device_total_attempts[ADDRESS],0)
                self.assertEqual(queue.qsize(),1)            # dongle returned
                self.assertFalse(cal.bg_inflight_bdaddrs)    # no stale in-flight marker
                self.assertNotIn(ADDRESS,cal.ble_bdaddrs)

    def quiet_for(self, seconds, address=ADDRESS):
        cal.device_last_seen[address]=cal.datetime.datetime.now()-cal.datetime.timedelta(seconds=seconds)

    def test_a_category_verdict_stands_for_the_run_after_its_evidence_has_expired(self):
        """Evidence is forgotten ten minutes after it was last heard, and a weak
        device's name is not in every report. A device skipped as headphones must
        not come back as an ordinary candidate once its name has expired: that
        happened on both Pis on 2026-11-17, and the device was probed."""
        now=[1000.0]
        for kind,atype,queue in (('BLE','random',cal.ble_bdaddrs),('BTC','public',cal.btc_bdaddrs)):
            with self.subTest(kind=kind):
                cal.novelty_evidence=AdvertisementEvidence(NoveltyRules(),clock=lambda: now[0])
                self.feed(ad(9,'LE-WH-CH720N'),kind)
                self.assertEqual(cal._candidate_skip_reason(kind,ADDRESS,atype),'novelty:AUDIO')
                now[0]+=cal.novelty_evidence.lifetime+1                       # the name has expired
                self.assertFalse(cal.novelty_evidence.reasons(ADDRESS,atype,kind))
                self.feed(ad(1,b'\x06'),kind)                                  # heard again, without the name
                self.assertNotIn(ADDRESS,queue)
                self.assertEqual(cal._candidate_skip_reason(kind,ADDRESS,atype),'novelty:AUDIO')
                cal.novelty_mode=False                                        # off means off
                self.assertIsNone(cal._category_skip_reason(kind,ADDRESS,atype))
                self.feed(ad(1,b'\x06'),kind)
                self.assertIn(ADDRESS,queue)
                cal.novelty_mode=True
                queue.clear()

    def test_a_retained_brand_name_overrides_an_earlier_verdict(self):
        """A retained vehicle that first shows only a shared Apple service is skipped
        as Apple until its name arrives. The verdict memory must not undo that."""
        self.feed(sd(0xfd6f)+ad(255,b'\x4c\0\x10\x01'))
        self.assertEqual(cal._candidate_skip_reason('BLE',ADDRESS,'random'),'novelty:APPLE')
        self.feed(ad(9,'BYD Key'))
        self.assertIsNone(cal._candidate_skip_reason('BLE',ADDRESS,'random'))
        self.assertIn(ADDRESS,cal.ble_bdaddrs)
        self.assertNotIn(('BLE',ADDRESS),cal.novelty_remembered)

    def test_the_verdict_memory_is_bounded(self):
        with patch.object(cal,'NOVELTY_REMEMBERED_MAX',3):
            for n in range(5):
                self.feed(ad(9,'LE-WH-CH720N'),address=f'ce:00:00:00:01:{n:02x}')
        self.assertEqual(list(cal.novelty_remembered),[('BLE',f'ce:00:00:00:01:{n:02x}') for n in (2,3,4)])

    def test_a_candidate_that_has_gone_quiet_leaves_the_queue_until_heard_again(self):
        """Nothing else takes a device out of the queue when it goes out of range.
        On pi0-2 the first attempt came a median of 25 minutes after the device was
        first heard, and none of 716 attempts in 140 minutes succeeded."""
        for kind,worker,queue in (('BLE',self.run_ble_worker,cal.ble_bdaddrs),('BTC',self.run_btc_worker,cal.btc_bdaddrs)):
            limit=cal.CANDIDATE_STALE_S[kind]
            with self.subTest(kind=kind):
                for store in (cal.ble_bdaddrs,cal.btc_bdaddrs,cal.device_connect_attempts,cal.device_total_attempts,
                              cal.device_last_seen): store.clear()
                self.feed(ad(9,'Novel Sensor'),kind)
                self.quiet_for(limit+1)
                self.assertEqual(worker(),[])                             # nothing launched
                self.assertNotIn(ADDRESS,queue)
                self.assertEqual((cal.device_connect_attempts[ADDRESS],cal.device_total_attempts[ADDRESS]),(0,0))
                self.assertIsNone(cal._candidate_skip_reason(kind,ADDRESS,'random' if kind=='BLE' else 'public'))
                self.feed(ad(9,'Novel Sensor'),kind)                      # heard again: a candidate again
                self.assertIn(ADDRESS,queue)
                self.quiet_for(limit-1)                                   # still inside the window
                self.assertTrue(worker())

    def test_a_candidate_that_goes_quiet_while_waiting_for_a_dongle_is_not_probed(self):
        self.feed(ad(9,'Novel Sensor'))
        class SlowQueue(Queue):
            def get(queue,*args,**kwargs):
                self.quiet_for(cal.CANDIDATE_STALE_S['BLE']+1)            # the wait outlasted the device
                return Queue.get(queue,*args,**kwargs)
        queue=SlowQueue();queue.put('/fake/sonoff')
        with patch.object(cal,'bg_dongle_queue',queue), patch.object(cal.subprocess,'Popen') as spawn, \
             patch.object(cal,'external_log_write'), patch.object(cal.time,'sleep',side_effect=StopWorker):
            with self.assertRaises(StopWorker):
                cal.ble_thread_function()
        self.assertEqual(spawn.call_count,0)
        self.assertEqual((cal.device_connect_attempts[ADDRESS],cal.device_total_attempts[ADDRESS]),(0,0))
        self.assertEqual(queue.qsize(),1)                                 # dongle returned
        self.assertFalse(cal.bg_inflight_bdaddrs)
        self.assertNotIn(ADDRESS,cal.ble_bdaddrs)

    def test_a_device_being_probed_is_not_dropped_for_being_quiet(self):
        """It stops advertising while Better Getter is connected to it."""
        self.feed(ad(9,'Novel Sensor'))
        self.quiet_for(cal.CANDIDATE_STALE_S['BLE']+60)
        cal.bg_inflight_bdaddrs.add(ADDRESS)
        self.assertFalse(cal._drop_stale_candidate('BLE',ADDRESS))
        self.assertIn(ADDRESS,cal.ble_bdaddrs)
        cal.bg_inflight_bdaddrs.discard(ADDRESS)
        self.assertTrue(cal._drop_stale_candidate('BLE',ADDRESS))
        self.assertFalse(cal._drop_stale_candidate('BLE',ADDRESS))       # already gone

    def run_btc_worker(self):
        """Drive the real BTC worker loop once; every probe it launches fails."""
        launched=[]
        class FakeThread:
            def __init__(self,process,bdaddr,info_type,**kwargs): pass
            def start(self): pass
            def join(self): pass
        def popen(cmd,**kwargs):
            launched.append(cmd)
            return type('Process',(),{'pid':100})()
        with patch.object(cal.subprocess,'Popen',side_effect=popen), patch.object(cal,'ApplicationThread',FakeThread), \
             patch.object(cal,'external_log_write'), patch.object(cal,'cycle_realtek_adapter'), \
             patch.object(cal,'_realtek_other_usb',set()), patch.object(cal.time,'sleep',side_effect=StopWorker):
            with self.assertRaises(StopWorker):
                cal.btc_thread_function()
        return launched

    def test_btc_probe_refused_at_launch_is_not_an_attempt(self):
        cal.novelty_mode=True
        self.feed(ad(9,'Novel Sensor'),'BTC')
        late=parse_event(inquiry(ad(9,'LE-WH-CH720N')))[0].frames
        def cycle_then_identify(*args,**kwargs):
            cal.novelty_evidence.observe(ADDRESS,'public','BTC',late)
        with patch.object(cal,'_lmp_invocations_since_cycle',cal.LMP_SCANS_BEFORE_REALTEK_CYCLE), \
             patch.object(cal,'cycle_realtek_adapter',side_effect=cycle_then_identify), \
             patch.object(cal.subprocess,'Popen') as spawn, patch.object(cal,'external_log_write'), \
             patch.object(cal.time,'sleep',side_effect=StopWorker):
            with self.assertRaises(StopWorker):
                cal.btc_thread_function()
        self.assertEqual(spawn.call_count,0)
        self.assertEqual(cal.device_connect_attempts[ADDRESS],0)
        self.assertEqual(cal.device_total_attempts[ADDRESS],0)
        self.assertNotIn(ADDRESS,cal.btc_bdaddrs)

    def test_scan_response_gives_evidence_but_never_admits_a_candidate(self):
        """ADV_SCAN_IND devices answer scans but refuse connections; their SCAN_RSP
        must not queue a probe. Its content still counts as evidence."""
        for enabled in (True,False):
            with self.subTest(novelty_mode=enabled):
                cal.novelty_mode=enabled
                cal.ble_bdaddrs.clear();cal.novelty_evidence.entries.clear();cal.novelty_remembered.clear()
                for event_type in (2,4,1):   # ADV_SCAN_IND, SCAN_RSP, ADV_DIRECT_IND
                    cal._handle_discovery_report(parse_event(legacy(ad(9,'Novel Sensor'),event_type=event_type))[0])
                self.assertFalse(cal.ble_bdaddrs)
                # A connectable device identified only by its scan response:
                cal._handle_discovery_report(parse_event(legacy(ad(1,b'\x06'),event_type=0))[0])
                self.assertIn(ADDRESS,cal.ble_bdaddrs)
                cal._handle_discovery_report(parse_event(legacy(ad(9,'LE-WH-CH720N'),event_type=4))[0])
                self.assertEqual(ADDRESS in cal.ble_bdaddrs,not enabled)
                cal._handle_discovery_report(parse_event(legacy(ad(1,b'\x06'),event_type=0))[0])
                self.assertEqual(ADDRESS in cal.ble_bdaddrs,not enabled)

    @unittest.skipUnless(HAVE_PRIVATE_RULES,'novelty_names.json is not installed in Analysis/metadata/private')
    def test_private_nameprint_rules_skip_through_the_launcher(self):
        cal.novelty_evidence=AdvertisementEvidence(NoveltyRules(PRIVATE_DIR))
        for enabled in (True,False):
            for kind in ('BLE','BTC'):
                with self.subTest(novelty_mode=enabled,transport=kind):
                    cal.novelty_mode=enabled
                    cal.ble_bdaddrs.clear();cal.btc_bdaddrs.clear()
                    self.feed(ad(9,'TOZO-T10'),kind)
                    queue=cal.ble_bdaddrs if kind=='BLE' else cal.btc_bdaddrs
                    self.assertEqual(ADDRESS in queue,not enabled)

    def test_success_retry_total_and_personal_caps_in_both_modes(self):
        for enabled in (True,False):
            for kind in ('BLE','BTC'):
                for cap in ('success','attempt','total','personal'):
                    with self.subTest(mode=enabled,kind=kind,cap=cap):
                        cal.novelty_mode=enabled
                        for store in (cal.gatt_success_bdaddrs,cal.sdp_success_bdaddrs,
                                      cal.lmp2thprint_success_bdaddrs,cal.device_connect_attempts,
                                      cal.device_total_attempts): store.clear()
                        cal.skip_these_addresses=[]
                        if cap=='success':
                            for store in (cal.gatt_success_bdaddrs,cal.sdp_success_bdaddrs,cal.lmp2thprint_success_bdaddrs): store[ADDRESS]=1
                        elif cap=='attempt': cal.device_connect_attempts[ADDRESS]=cal.max_connect_attempts
                        elif cap=='total': cal.device_total_attempts[ADDRESS]=cal.max_total_attempts
                        else: cal.skip_these_addresses=[ADDRESS]
                        for _ in range(3): self.feed(ad(9,'Novel Sensor'),kind)
                        self.assertNotIn(ADDRESS,cal.ble_bdaddrs)
                        self.assertNotIn(ADDRESS,cal.btc_bdaddrs)
                        self.assertIsNotNone(cal._candidate_skip_reason(kind,ADDRESS,'random' if kind=='BLE' else 'public'))

    def test_one_remaining_attempt_is_still_eligible(self):
        for enabled in (True,False):
            cal.novelty_mode=enabled
            cal.device_connect_attempts[ADDRESS]=cal.max_connect_attempts-1
            cal.device_total_attempts[ADDRESS]=cal.max_total_attempts-1
            self.feed(ad(9,'Novel Sensor'))
            self.assertIsNone(cal._candidate_skip_reason('BLE',ADDRESS,'random'))

    def test_late_scan_response_cancels_queue_and_stale_spawn(self):
        for kind in ('BLE','BTC'):
            for enabled in (True,False):
                cal.novelty_mode=enabled
                self.feed(ad(9,'Novel Sensor'),kind)
                self.feed(ad(9,'LE-WH-CH720N'),kind)
                queue=cal.ble_bdaddrs if kind=='BLE' else cal.btc_bdaddrs
                self.assertEqual(ADDRESS in queue,not enabled)
                with patch.object(cal.subprocess,'Popen') as spawn:
                    cal.launch_application(['fake'],'.',target=(kind,ADDRESS,'random' if kind=='BLE' else 'public'))
                    self.assertEqual(spawn.call_count,0 if enabled else 1)

    def test_deferred_gatt_queue_is_filtered_but_retained_when_off(self):
        for enabled in (True,False):
            cal.novelty_mode=enabled
            self.feed(ad(9,'LE-WH-CH720N'))
            cal.ble_gatt_value_deprioritized_bdaddrs[ADDRESS]=('random',-40)
            self.assertEqual(cal.reprioritize_ble_gatt_value_bdaddr(ADDRESS),not enabled)
            self.assertEqual(ADDRESS in cal.gatt_force_read_bdaddrs,not enabled)
        cal.novelty_mode=True
        novel='ce:00:00:00:00:02'     # another device: the headphones above stay skipped for the run
        self.feed(ad(9,'Novel Sensor'),address=novel)
        cal.ble_bdaddrs.clear()
        cal.ble_gatt_value_deprioritized_bdaddrs[novel]=('random',-40)
        cal._promote_ble_fallbacks_for_capacity()
        self.assertIn(novel,cal.ble_bdaddrs)
        self.assertIn(novel,cal.gatt_force_read_bdaddrs)

    def test_discovery_failure_is_a_nonzero_launcher_exit(self):
        with patch.object(sys,'argv',['central_app_launcher.py','--discovery-only']), \
             patch.object(cal,'_initialize_realtek'), patch.object(cal.threading,'Thread'), \
             patch.object(cal,'dbus_discovery_loop',new=lambda: None), \
             patch.object(cal.asyncio,'run',side_effect=OSError('monitor unavailable')), \
             patch.object(cal.traceback,'print_exc'):
            with self.assertRaises(SystemExit) as result:
                cal.main()
            self.assertEqual(result.exception.code,1)

    def test_mislabelled_public_report_does_not_resurrect_a_skipped_random_device(self):
        """Seen live on pi0-2 (Realtek and Broadcom alike): an iPhone on a random
        address, a few percent of whose reports arrive typed "public", empty scan
        responses included. That is one device. It must stay skipped, not come
        back as a second candidate with no evidence and the wrong address type."""
        apple=ad(1,b'\x1a')+ad(255,bytes.fromhex('4c001006451d752c4d78'))
        def report(raw,atype,connectable=True):
            return Report(ADDRESS,atype,'BLE',-68,parse_event(legacy(raw))[0].frames,connectable)
        for enabled in (True,False):
            with self.subTest(novelty_mode=enabled):
                cal.novelty_mode=enabled
                for store in (cal.ble_bdaddrs,cal.ble_address_types): store.clear()
                cal.novelty_evidence.entries.clear();cal.novelty_remembered.clear()
                for _ in range(5): cal._handle_discovery_report(report(apple,'random'))
                cal._handle_discovery_report(report(b'','public',connectable=False))   # empty SCAN_RSP
                cal._handle_discovery_report(report(b'','public'))                     # evidence-free ADV
                cal._handle_discovery_report(report(apple,'public'))
                if enabled:
                    self.assertNotIn(ADDRESS,cal.ble_bdaddrs)
                    for atype in ('random','public'):
                        self.assertEqual(cal._candidate_skip_reason('BLE',ADDRESS,atype),'novelty:APPLE')
                else:   # still one candidate, still probed as the random address it is
                    self.assertEqual(cal.ble_bdaddrs[ADDRESS][0],'random')

    def test_candidate_is_probed_with_the_address_type_most_reports_carry(self):
        novel=ad(9,'Novel Sensor')
        def report(atype):
            return Report(ADDRESS,atype,'BLE',-60,parse_event(legacy(novel))[0].frames,True)
        for _ in range(4): cal._handle_discovery_report(report('random'))
        cal._handle_discovery_report(report('public'))            # one stray report
        self.assertEqual(cal.ble_bdaddrs[ADDRESS][0],'random')
        launched=self.run_ble_worker(dongles=1)
        self.assertTrue(launched)
        self.assertFalse(any('-P' in cmd for cmd in launched))    # -P means "public address"
        # A first report that was the stray one is corrected once the real type leads.
        for store in (cal.ble_bdaddrs,cal.ble_address_types,cal.device_connect_attempts,cal.device_total_attempts): store.clear()
        cal._handle_discovery_report(report('public'))
        self.assertEqual(cal.ble_bdaddrs[ADDRESS][0],'public')
        for _ in range(2): cal._handle_discovery_report(report('random'))
        self.assertEqual(cal.ble_bdaddrs[ADDRESS][0],'random')
        cal.ble_bdaddrs.clear()
        cal.ble_gatt_value_deprioritized_bdaddrs[ADDRESS]=('public',-40)
        cal._handle_discovery_report(report('random'))
        self.assertEqual(cal.ble_gatt_value_deprioritized_bdaddrs[ADDRESS][0],'random')

    def test_evidence_under_either_address_type_skips_the_one_device(self):
        """The identifying field may be the one that arrived mislabelled."""
        cal._handle_discovery_report(Report(ADDRESS,'random','BLE',-40,((1,b'\x06'),)))
        self.assertIn(ADDRESS,cal.ble_bdaddrs)
        cal._handle_discovery_report(Report(ADDRESS,'public','BLE',-40,((9,b'LE-WH-CH720N'),),False))
        self.assertNotIn(ADDRESS,cal.ble_bdaddrs)
        self.assertEqual(cal._candidate_skip_reason('BLE',ADDRESS,'random'),'novelty:AUDIO')
        cal._handle_discovery_report(Report(ADDRESS,'random','BLE',-40,((1,b'\x06'),)))
        self.assertNotIn(ADDRESS,cal.ble_bdaddrs)
        # A different address is unaffected, and so is BR/EDR with the same octets.
        cal._handle_discovery_report(Report('ce:00:00:00:00:02','random','BLE',-40,((1,b'\x06'),)))
        self.assertIn('ce:00:00:00:00:02',cal.ble_bdaddrs)
        self.assertIsNone(cal._candidate_skip_reason('BTC',ADDRESS,'public'))

    def test_nonconnectable_advertisement_never_admits_probe(self):
        report=parse_event(legacy(ad(9,'Novel Sensor'),event_type=3))[0]
        for enabled in (True,False):
            cal.novelty_mode=enabled
            cal._handle_discovery_report(report)
            self.assertFalse(cal.ble_bdaddrs)

    def test_off_does_not_change_partial_btc_success_behavior(self):
        for enabled in (True,False):
            cal.novelty_mode=enabled
            cal.lmp2thprint_success_bdaddrs[ADDRESS]=1
            self.feed(ad(9,'Novel Sensor'),'BTC')
            self.assertIn(ADDRESS,cal.btc_bdaddrs)
            self.assertIsNone(cal._candidate_skip_reason('BTC',ADDRESS,'public'))



class LauncherWiringTests(unittest.TestCase):
    def test_launcher_reads_private_rules_from_the_private_metadata_directory(self):
        rules=cal.novelty_evidence.rules
        self.assertEqual(rules.private_file is not None,HAVE_PRIVATE_RULES)
        if HAVE_PRIVATE_RULES:
            self.assertEqual(rules.private_file,cal.REPO_ROOT/'Analysis/metadata/private/novelty_names.json')
            self.assertGreater(rules.private_name_rules,0)
        self.assertIn('public name rules',rules.describe())


class MonitorLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_bad_packet_does_not_end_discovery(self):
        """Discovery ending takes the whole launcher down. A packet that trips a
        handler bug must be logged and skipped, as the old D-Bus router did."""
        good=monitor(legacy(ad(9,'Novel Sensor')))
        class FakeLoop:
            packets=[b'bad packet',good]
            async def sock_recv(self,sock,size): return self.packets.pop(0) if self.packets else b''
        real=cal.parse_monitor
        def parse(packet,index):
            if packet==b'bad packet': raise ValueError('handler bug')
            return real(packet,index)
        output=io.StringIO()
        with patch.object(cal,'ble_bdaddrs',{}), patch.object(cal,'device_connect_attempts',{}), \
             patch.object(cal,'device_total_attempts',{}), patch.object(cal,'device_last_seen',{}), \
             patch.object(cal,'novelty_evidence',AdvertisementEvidence(NoveltyRules())), \
             patch.object(cal,'novelty_remembered',OrderedDict()), \
             patch.object(cal,'get_realtek_dbus_path',return_value='/org/bluez/hci1'), \
             patch.object(cal,'parse_monitor',side_effect=parse), patch.object(cal.traceback,'print_exc'), \
             patch.object(cal.asyncio,'get_running_loop',return_value=FakeLoop()), \
             contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,'monitor closed'):
                await cal._monitor_discovery(object())
            self.assertIn(ADDRESS,cal.ble_bdaddrs)
        self.assertIn('ValueError: handler bug',output.getvalue())

    async def test_start_failure_closes_monitor_and_disconnects_bus(self):
        from unittest.mock import AsyncMock, MagicMock
        bus=MagicMock()
        adapter=MagicMock()
        adapter.call_set_discovery_filter=AsyncMock()
        adapter.call_start_discovery=AsyncMock(side_effect=RuntimeError('test start failure'))
        adapter.call_stop_discovery=AsyncMock()
        monitor=MagicMock()
        async def idle(_):
            import asyncio
            await asyncio.Future()
        factory=MagicMock();factory.return_value.connect=AsyncMock(return_value=bus)
        with patch.object(cal,'MessageBus',factory), patch.object(cal,'find_realtek_hci',return_value=('hci1','/org/bluez/hci1')), \
             patch.object(cal,'_resolve_adapter',AsyncMock(return_value=adapter)), patch.object(cal,'open_monitor',return_value=monitor), \
             patch.object(cal,'_monitor_discovery',side_effect=idle):
            with self.assertRaisesRegex(RuntimeError,'test start failure'):
                await cal.dbus_discovery_loop()
        monitor.close.assert_called_once()
        bus.disconnect.assert_called_once()
        adapter.call_stop_discovery.assert_awaited_once()

    async def test_cycle_wait_cancels_without_waiting_for_hardware(self):
        import asyncio
        cal._realtek_cycle_pending.clear()
        task=asyncio.create_task(cal._restart_discovery_after_cycle(None))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task,1)


if __name__=='__main__': unittest.main()
