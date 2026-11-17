#!/usr/bin/env python3
"""Refresh reviewed identifiers from a local DM BT checkout; never queries a DB.

Usage: python3 Scripts/novelty/import_dm_bt_rules.py /path/to/XenoMetaRadar
Review the diff and run Scripts/tests before accepting a refreshed snapshot.

DM BT's reviewed name manifest mixes rules derived from the public NamePrints,
generic name families, and rules derived from the *private* NamePrints. This
repository is public and Analysis/metadata/private is not part of it, so the
manifest is split on the way in:

  Scripts/novelty/data/names.json               public rules, committed here
  Analysis/metadata/private/novelty_names.json  private rules, never committed
                                                here; scp it to a capture node

A rule is private when its pattern or description is a row of a private
NamePrint file and is not also a row of a public one.
"""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
METADATA = REPO_ROOT / 'Analysis/metadata'
PRIVATE_DIR = METADATA / 'private'
PRIVATE_NAMES_FILE = 'novelty_names.json'


def parse_sets(text):
    identifiers = {}
    for name, values in re.findall(r'val (\w+)(?:: Set<\w+>)? = setOf\((.*?)\)', text, re.S):
        strings = re.findall(r'"([^"\n]+)"', values)
        identifiers[name] = strings if strings else [int(n, 16) for n in re.findall(r'0x([0-9a-fA-F]+)', values)]
    return identifiers


def _normalize(pattern):
    # The manifest normalized legacy SQL backslash runs; compare on equal terms.
    return re.sub(r'\\+', r'\\', pattern)


def nameprint_rows(paths):
    """(descriptions, normalized patterns) of every NamePrint row in paths."""
    descriptions, patterns = set(), set()
    for path in paths:
        with open(path, newline='', encoding='utf-8') as handle:
            for row in csv.reader(handle):
                if len(row) >= 2:
                    descriptions.add(row[0])
                    patterns.add(_normalize(row[1]))
    return descriptions, patterns


def split_names(manifest, public, private):
    """Split a DM BT manifest into (public manifest, private manifest)."""
    public_descriptions, public_patterns = public
    private_descriptions, private_patterns = private

    def known(row, descriptions, patterns):
        return row['source'] in descriptions or _normalize(row['pattern']) in patterns

    shared = {key: manifest[key] for key in ('research_date', 'source', 'notes') if key in manifest}
    public_out = dict(shared, categories={})
    private_out = dict(shared, categories={})
    for category, rows in manifest['categories'].items():
        is_private = [known(row, private_descriptions, private_patterns) and
                      not known(row, public_descriptions, public_patterns) for row in rows]
        public_out['categories'][category] = [row for row, hidden in zip(rows, is_private) if not hidden]
        private_out['categories'][category] = [row for row, hidden in zip(rows, is_private) if hidden]
    return public_out, private_out


def export(source, destination, metadata=METADATA, private_dir=PRIVATE_DIR):
    source, destination = Path(source), Path(destination)
    metadata, private_dir = Path(metadata), Path(private_dir)
    private_csvs = sorted(private_dir.glob('NAMEPRINT_*.csv'))
    if not private_csvs:
        # Without the private NamePrints nothing can be recognized as private, and
        # every private rule would be written into the committed public file.
        raise SystemExit(f'No private NamePrint files in {private_dir}; refusing to import, '
                         'because private rules could not be kept out of the public snapshot.')
    kt = source / 'app/src/main/java/com/darkmentor/domain/interactor'
    category = (kt / 'AdvertisementCategorySkips.kt').read_text()
    vendor = (kt / 'VendorRegistry.kt').read_text()
    identifiers = {}
    for text in (category, vendor):
        identifiers.update(parse_sets(text))
    for name in ('RETAINED_VEHICLE', 'NON_AUDIO'):
        identifiers[name] = re.search(r'val ' + name + r' = Regex\(\s*"""(.*?)"""', category, re.S)[1]
    files = ['tools/skip-filters/reviewed_names.json'] + [str((kt / n).relative_to(source)) for n in
              ('VendorRegistry.kt', 'VendorIdentifier.kt', 'AdvertisementCategorySkips.kt', 'AdvertisementAudioSignatures.kt')]
    provenance = {'commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
                  'sha256': {f: hashlib.sha256((source/f).read_bytes()).hexdigest() for f in files}}
    public_names, private_names = split_names(
        json.loads((source / files[0]).read_text()),
        nameprint_rows(sorted(metadata.glob('NAMEPRINT_*.csv'))),
        nameprint_rows(private_csvs))
    destination.mkdir(parents=True, exist_ok=True)
    (destination/'identifiers.json').write_text(json.dumps(identifiers, indent=2, ensure_ascii=False)+'\n')
    (destination/'names.json').write_text(json.dumps(public_names, indent=2, ensure_ascii=False)+'\n')
    (destination/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    (private_dir/PRIVATE_NAMES_FILE).write_text(json.dumps(private_names, indent=2, ensure_ascii=False)+'\n')
    return ({key: len(rows) for key, rows in public_names['categories'].items()},
            {key: len(rows) for key, rows in private_names['categories'].items()})


if __name__ == '__main__':
    counts = export(sys.argv[1], Path(__file__).parent / 'data')
    print(f'public  {counts[0]} -> {Path(__file__).parent / "data/names.json"}')
    print(f'private {counts[1]} -> {PRIVATE_DIR / PRIVATE_NAMES_FILE}')
