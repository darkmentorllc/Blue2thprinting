#!/usr/bin/env python3
"""Read-only live QA: compare on/off eligibility on the same real HCI stream.

Run as root on Linux while the existing BlueZ scan is active. Does not start or
stop scanning, open BLE/BTC links, or modify the running launcher's settings.

Uses the same rules as the launcher, including the private name rules in
Analysis/metadata/private when they are installed. --show-names lists the
advertised names it saw, split by verdict, to make misses easy to spot.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import select
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novelty.discovery import open_monitor, parse_monitor
from novelty.rules import AdvertisementEvidence, NoveltyRules

REPO_ROOT = Path(__file__).resolve().parents[2]


def _names(frames):
    return [data.decode('utf-8', errors='replace').strip('\x00 \t\r\n')
            for kind, data in frames if kind in (8, 9) and data]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index',type=int,required=True)
    parser.add_argument('--seconds',type=float,default=30)
    parser.add_argument('--private-dir',default=str(REPO_ROOT/'Analysis/metadata/private'))
    parser.add_argument('--show-names',action='store_true')
    args=parser.parse_args()
    rules=NoveltyRules(args.private_dir)
    evidence=AdvertisementEvidence(rules)
    counts=Counter()
    identities={False:set(),True:set()}
    names={}
    busy=0.0
    start=time.monotonic()
    with open_monitor() as monitor:
        while time.monotonic()-start < args.seconds:
            if not select.select([monitor],[],[],max(0,min(1,args.seconds-(time.monotonic()-start))))[0]:
                continue
            packet=monitor.recv(65541)
            began=time.perf_counter()
            for report in parse_monitor(packet,args.index):
                reasons=evidence.observe(report.address,report.address_type,report.transport,report.frames)
                counts[report.transport+'_reports']+=1
                for reason in reasons: counts['category_'+reason]+=1
                for name in _names(report.frames):
                    names[(report.transport,name)]=sorted(reasons)
                if report.connectable:
                    identity=(report.transport,report.address,report.address_type)
                    identities[False].add(identity)
                    if not reasons: identities[True].add(identity)
                    counts['off_eligible_reports']+=1
                    counts['on_eligible_reports']+=not bool(reasons)
            busy+=time.perf_counter()-began
    duration=time.monotonic()-start
    reports=counts['BLE_reports']+counts['BTC_reports']
    result={'duration_seconds':round(duration,2),'controller_index':args.index,
            'rules':rules.describe(),
            'counts':dict(counts),'off_eligible_identities':len(identities[False]),
            'on_eligible_identities':len(identities[True]),'connection_attempts':0,
            'cpu_ms_per_report':round(1000*busy/reports,3) if reports else None,
            'cpu_share_of_one_core':round(busy/duration,4)}
    if args.show_names:
        result['skipped_names']={f'{kind} {name}':why for (kind,name),why in sorted(names.items()) if why}
        result['eligible_names']=[f'{kind} {name}' for (kind,name),why in sorted(names.items()) if not why]
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if not reports: raise SystemExit('No discovery reports observed: live QA inconclusive')


if __name__=='__main__': main()
