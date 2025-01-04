import json
from itertools import groupby

def merge_entries(entry1, entry2):
    merged_entry = {}
    for key in entry1:
        if isinstance(entry1[key], list) and isinstance(entry2[key], list):
            # Merge and deduplicate arrays
            merged_entry[key] = list({json.dumps(item) for item in entry1[key] + entry2[key]})
            merged_entry[key] = [json.loads(item) for item in merged_entry[key]]
        elif isinstance(entry1[key], str) and isinstance(entry2[key], str):
            if entry1[key] == entry2[key]:
                merged_entry[key] = entry1[key]
            else:
                merged_entry[key] = f"MERGED: ({entry1[key]}), ({entry2[key]})"
        else:
            merged_entry[key] = entry1[key] if entry1[key] is not None else entry2[key]
    return merged_entry

def entries_are_equal(entry1, entry2):
    if not entry1 or not entry2:
        return False
    return all(entry1.get(key) == entry2.get(key) for key in entry1)

def sort_custom_uuids(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    def sort_key(entry):
        company = entry['company'] if entry['company'] is not None else ''
        return company, entry['UUID_purpose'], entry['UUID']

    # Group entries by UUID
    uuid_groups = {}
    for entry in data:
        uuid = entry['UUID']
        if uuid not in uuid_groups:
            uuid_groups[uuid] = []
        uuid_groups[uuid].append(entry)

    # Merge entries within each UUID group
    merged_entries = {}
    for uuid, entries in uuid_groups.items():
        if len(entries) == 1:
            merged_entries[uuid] = entries[0]
        else:
            # Start with the first entry
            merged = entries[0]
            # Compare and merge with subsequent entries
            for entry in entries[1:]:
                if not entries_are_equal(merged, entry):
                    print(f"Merging entries for UUID: {uuid}")
                    merged = merge_entries(merged, entry)
            merged_entries[uuid] = merged

    sorted_data = sorted(merged_entries.values(), key=sort_key)

    # Track which UUIDs we've already added to the result
    seen_uuids = set()
    result = []

    for company, group in groupby(sorted_data, key=lambda x: x['company'] if x['company'] is not None else ''):
        group = list(group)
        services = [entry for entry in group if "GATT Service" in entry['UUID_usage_array']]
        characteristics = [entry for entry in group if "GATT Characteristic" in entry['UUID_usage_array']]

        for service in services:
            if service['UUID'] not in seen_uuids:
                result.append(service)
                seen_uuids.add(service['UUID'])

            related_characteristics = [
                char for char in characteristics
                if service['UUID_purpose'] in char['UUID_purpose']
                and char['UUID'] not in seen_uuids
            ]
            for char in related_characteristics:
                result.append(char)
                seen_uuids.add(char['UUID'])

        unrelated_characteristics = [
            char for char in characteristics
            if all(service['UUID_purpose'] not in char['UUID_purpose'] for service in services)
            and char['UUID'] not in seen_uuids
        ]
        for char in unrelated_characteristics:
            result.append(char)
            seen_uuids.add(char['UUID'])

    with open(file_path, 'w') as f:
        json.dump(result, f, indent=2)

if __name__ == "__main__":
    sort_custom_uuids('Custom_UUIDs.json')
