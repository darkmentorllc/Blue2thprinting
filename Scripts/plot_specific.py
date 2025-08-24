##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

import csv
from gmplot import gmplot

# Place map
# @39.05348,-77.0350704,13z
gmap = gmplot.GoogleMapPlotter(39.0372586,-97.6343117,5)

# Add Markers
print ("Adding markers\n")
with open('/tmp/specific.csv', newline='\n') as csvfile:
	devreader = csv.reader(csvfile, delimiter=',', quotechar='"')
	for row in devreader:
		if(len(row) >= 5): # Skip it if it doesn't have enough rows
#			print(', '.join(row))
			compound_title = "DeviceName: %s, BDADDR: %s, RSSI: %s" % (row[0], row[1], row[2])
			lat = row[3]
			lon = row[4]
#			print (compound_title + " " + lat + ", " + lon)
			gmap.marker(float(lat), float(lon), 'cornflowerblue', title=compound_title)

# Draw
gmap.draw("bt_map.html")
print ("Done\n")
