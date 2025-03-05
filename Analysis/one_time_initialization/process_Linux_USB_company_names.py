import csv
import re

pattern = re.compile(r'^[0-9A-Fa-f]{4}\b')

input_file = 'usb.ids.txt'
output_file = '/tmp/USB_CID_to_company.csv'

with open(input_file, 'r', encoding='latin-1') as f:
    lines = f.readlines()

data = []
for line in lines:
    if line.startswith('#') or line.startswith('\n'):
        continue
    if line.startswith('\t'):
        continue
    if pattern.match(line):
        line = line.strip()
        print(line)
        vendor_id, vendor_name = line.split(maxsplit=1)
        data.append([vendor_id, vendor_name])

with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
    writer.writerows(data)
