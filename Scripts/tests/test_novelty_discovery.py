import struct
import unittest
from test_novelty_rules import ad
from novelty.discovery import parse_event, parse_monitor

ADDR=bytes.fromhex('0100000000ce')


def event(code, body):
    return bytes([code,len(body)])+body


def legacy(raw, addr=ADDR, atype=1, event_type=0):
    return event(0x3e,b'\x02\x01'+bytes([event_type,atype])+addr+bytes([len(raw)])+raw+b'\xc0')


def extended(raw, flags=1, atype=1):
    header=struct.pack('<HB6sBBBbbHB6sB',flags,atype,ADDR,1,0,0,0,-64,0,0,bytes(6),len(raw))
    return event(0x3e,b'\x0d\x01'+header+raw)


def inquiry(raw):
    return event(0x2f,b'\x01'+ADDR+b'\x01\x00'+bytes(3)+bytes(2)+b'\xc0'+raw.ljust(240,b'\0'))


def monitor(evt,index=1,opcode=3):
    return struct.pack('<HHH',opcode,index,len(evt))+evt


class DiscoveryTests(unittest.TestCase):
    def test_legacy_and_scan_response(self):
        raw=ad(9,'LE-WH-CH720N')
        # Every legacy PDU type supplies evidence; only ADV_IND invites us to connect.
        # ADV_DIRECT_IND (1) targets another central, ADV_SCAN_IND (2) and
        # ADV_NONCONN_IND (3) are not connectable, and a SCAN_RSP (4) also answers
        # for ADV_SCAN_IND advertisers, so it cannot prove connectability.
        for t,connectable in ((0,True),(1,False),(2,False),(3,False),(4,False)):
            with self.subTest(event_type=t):
                r=parse_event(legacy(raw,event_type=t))[0]
                self.assertEqual((r.address,r.address_type,r.transport,r.rssi,r.connectable),('ce:00:00:00:00:01','random','BLE',-64,connectable))
                self.assertEqual(r.frames,((9,b'LE-WH-CH720N'),))

    def test_extended_connectability_follows_event_type_bits(self):
        raw=ad(9,'Novel Sensor')
        # bit0 connectable, bit1 scannable, bit2 directed, bit3 scan response, bit4 legacy
        # A scan response (0x1b, 0x1a, 0x08) is evidence only: its ADV_IND admits the device.
        for flags,connectable in ((0x13,True),(0x01,True),(0x1b,False),(0x15,False),(0x05,False),
                                  (0x12,False),(0x1a,False),(0x10,False),(0x00,False),(0x08,False)):
            with self.subTest(flags=hex(flags)):
                self.assertEqual(parse_event(extended(raw,flags=flags))[0].connectable,connectable)

    def test_extended_report_and_fragment_rejection(self):
        raw=ad(9,'S21 FE de Silva')
        r=parse_event(extended(raw))[0]
        self.assertEqual(r.frames,((9,b'S21 FE de Silva'),))
        self.assertEqual(r.rssi,-64)
        self.assertTrue(r.connectable)
        for flags in (0x21,0x41,0x61):
            self.assertEqual(parse_event(extended(raw,flags=flags)),[])
        self.assertEqual(parse_event(extended(raw,atype=0xff)),[])
        self.assertEqual(parse_event(extended(raw,atype=2))[0].address_type,'public')

    def test_eir_and_inquiry_without_eir(self):
        raw=ad(9,'TELLURIDE Digital Key')
        r=parse_event(inquiry(raw))[0]
        self.assertEqual((r.transport,r.address_type,r.rssi),('BTC','public',-64))
        self.assertEqual(r.frames,((9,b'TELLURIDE Digital Key'),))
        for code in (2,0x22):
            body=b'\x01'+ADDR+bytes(7)+b'\xc0'
            r=parse_event(event(code,body))[0]
            self.assertEqual(r.frames,())
            self.assertEqual(r.transport,'BTC')

    def test_all_truncations_rejected(self):
        for packet in (legacy(ad(9,'Android-1234')),extended(ad(9,'Bose')),inquiry(ad(9,'Key'))):
            for end in range(len(packet)):
                self.assertEqual(parse_event(packet[:end]),[])
            # A consistent HCI length cannot hide an invalid internal report length.
            short=packet[:-1]
            self.assertEqual(parse_event(short[:1]+bytes([len(short)-2])+short[2:]),[])

    def test_multiple_legacy_reports(self):
        first=legacy(ad(9,'First'))[4:]
        second=legacy(ad(9,'Second'))[4:]
        packet=event(0x3e,b'\x02\x02'+first+second)
        self.assertEqual([r.frames for r in parse_event(packet)],[((9,b'First'),),((9,b'Second'),)])

    def test_monitor_filters_controller_and_packet_direction(self):
        packet=monitor(legacy(ad(9,'AirPods')))
        self.assertEqual(len(parse_monitor(packet,1)),1)
        self.assertEqual(parse_monitor(packet,2),[])
        self.assertEqual(parse_monitor(monitor(legacy(b''),opcode=2),1),[])
        self.assertEqual(parse_monitor(packet[:-1],1),[])
        self.assertEqual(parse_monitor(packet+b'\0',1),[])

    def test_connected_name_and_acl_never_become_advertising_evidence(self):
        remote_name=event(7,b'\0'+ADDR+b'LE-WH-CH720N'.ljust(248,b'\0'))
        self.assertEqual(parse_event(remote_name),[])
        self.assertEqual(parse_monitor(monitor(b'GATT Android-1234',opcode=5),1),[])



class SocketTests(unittest.TestCase):
    def test_native_bind_uses_monitor_channel_without_python_tuple_support(self):
        import ctypes
        from unittest.mock import MagicMock, patch
        from novelty import discovery
        monitor=MagicMock();monitor.fileno.return_value=7
        libc=MagicMock()
        def bind(fd,buffer,size):
            self.assertEqual(fd,7)
            self.assertEqual(size,6)
            self.assertEqual(struct.unpack('@HHH',ctypes.string_at(buffer,size)),(31,0xffff,2))
            return 0
        libc.bind.side_effect=bind
        with patch.object(discovery.ctypes,'CDLL',return_value=libc), patch.object(discovery.socket,'AF_BLUETOOTH',31,create=True):
            discovery._bind_monitor(monitor)
        monitor.bind.assert_not_called()

    def test_failed_bind_closes_socket_and_propagates(self):
        from unittest.mock import MagicMock, patch
        from novelty import discovery
        monitor=MagicMock()
        with patch.object(discovery.socket,'socket',return_value=monitor), \
             patch.object(discovery.socket,'AF_BLUETOOTH',31,create=True), \
             patch.object(discovery.socket,'BTPROTO_HCI',1,create=True), \
             patch.object(discovery,'_bind_monitor',side_effect=OSError('bind failure')):
            with self.assertRaisesRegex(OSError,'bind failure'): discovery.open_monitor()
        monitor.close.assert_called_once()


if __name__=='__main__': unittest.main()
