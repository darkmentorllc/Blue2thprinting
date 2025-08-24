##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

# Takes in an argv[1] of a file path like /home/user/gpspipe/2020-05-10-18-21-23_pi4.txt
# Outputs "hosttime","gpstime","lat","lon"
# hosttime is from the front of the lines, and is the time according to the rpi's clock (which was typically wrong)
# gpstime is what time gpspipe thinks it is (which is typically right AFAIK)
# lat and lon are the latitude and longitude reported for any times where they are available

import sys
import json

filepath = sys.argv[1]
#sys.stderr.write(filepath + "\n")
with open(filepath) as fp:
   line = fp.readline()
   while line:
       line = fp.readline()
       # only parse lines that look like they'll have a latitude in them
       if ("lat" not in line):
           continue
       stuff = line.split(': ')
       # Get the timestamp as seen by the host, and remove the leading '+' character
       hosttime = stuff[0][1:]
       # Convert the JSON string into something that can be parsed with json.load()
       jsonpart = stuff[1]
#       jsonpart = '{"class":"TPV","device":"/dev/ttyACM0","status":2,"mode":3,"time":"2020-05-16T19:33:39.000Z","ept":0.005,"lat":39.060452386,"lon":-76.913321552,"alt":65.875,"epx":3.640,"epy":5.078,"epv":12.650,"track":74.1122,"speed":0.075,"climb":-0.041,"eps":0.71,"epc":25.30}'
#       print jsonpart
       data = json.loads(jsonpart)
       #format the gps time like mysql prefers
       gpstime = data["time"]
       gpstime = gpstime.replace("T"," ")
       gpstime = gpstime[:-5] #remove last 5 characters (the '.000Z')
       lat = data["lat"]
       lon = data["lon"]

       print("\"%s\",\"%s\",\"%s\",\"%s\"" % (hosttime, gpstime, lat, lon))
