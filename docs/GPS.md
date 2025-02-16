Created by Xeno Kovah  
Copyright(c) © Dark Mentor LLC 2023-2024

## GPS coordinate logging

### Test GPS module:

If you type "gpsmon" at this point, you will not get any coordinates. The presence of coordinates will be our determination of correctness of operation.

*With all devices unplugged from the system*, run: `ls -la /dev/ttyACM*`  
 - There should be no such file present. If there is something present, unplug all peripheral devices until you detect which device was causing that. Do not plug that device in again while operating this system.  
 - Plug in your USB GPS antenna, run `ls -la /dev/ttyACM*`  
 - The GPS device should now be visible as /dev/ttyACM0. ***The below will assume that /dev/ttyACM0 is the GPS device.***  

Change two lines from:

```
ListenStream=[::1]:2947
ListenStream=127.0.0.1:2947
```

to

```
#ListenStream=[::1]:2947
ListenStream=0.0.0.0:2947
```
Save the file and exit. (Note: this commented out the IPv6 address.)

```
gpsd /dev/ttyACM0 -F /var/run/gpsd.socket
systemctl daemon-reload
systemctl restart gpsd.socket
systemctl restart gpsd
```
You should now see GPS coordinates (assuming you're somewhere with visibility of the sky or otherwise in GPS range.) If you don't, reboot, and then run "sudo gpsmon" and confirm if you can then. (If you still can't, you're SOL, because Linux GPS has caused me enough trouble, and I'm not debugging yours `¯\_(ツ)_/¯`.)

Ctrl-c to exit gpsmon.

`gpspipe -V`
Confirm you are running version 3.17 (newer versions like 3.22 which is bundled with newer Raspbian OSes have known issues that prevent capturing the coordinates in our usage, with the GPS hardware recommended on the main page.)

### Re-enable gpspipe in misc scripts

1. Edit ~/Blue2thprinting/Scripts/runall.sh and un-comment the line that includes `gpspipe`, and fix up the username if needed.
2. Edit ~/Blue2thprinting/Scripts/check.sh and un-comment the line that includes `gpspipe`.
3. Edit ~/Blue2thprinting/Scripts/killall.sh and un-comment the line that includes `gpspipe`.

# Analysis Scripts Usage

After you have sniffed some traffic, you will have files in ~/Blue2thprinting/Logs/btmon/ and ~/Blue2thprinting/Logs/gpspipe/, that should be named the same as each other (timestamp followed by hostname) except that GPS files end in .txt and btmon in .bin.

**Note:** Because data parsing and database lookups can be CPU/IO intensive, it is generally recommended to *not* perform data import or analysis on the capture device (the UP^2 in this case.) Rather, it is recommended to copy all data off to a separate, faster, analysis system, and perform the subsequent steps there.

### delete\_gps\_files\_lacking\_lat\_long.py

Often the GPS log will be continuing to log metadata even when it can't get a GPS coordinate fix. You should periodically deliminate any useless files that have no lat/long coordinates by running the following:

```
python3 delete_gps_files_lacking_lat_long.py ~/Blue2thprinting/Logs/gpspipe/
```

Any files that are deleted will be printed out. No output means no files were deleted.

### map\_specific.sh

Assume we have the following files:

```
user@VM:~/Blue2thprinting/$ ls Logs/gpspipe/
2023-08-24-01-04-59_pi0-2.txt  2023-08-24-01-11-38_pi0-2.txt
```

If you have a file like `~/Blue2thprinting/Logs/gpspipe/2023-08-24-01-11-38_pi0-2.txt` for instance, you can map the instances of *named* bluetooth devices. 

```
user@VM:/home/user/Blue2thprinting/Scripts: ./map_specific.sh 2023-08-24-01-04-59_pi0-2 2023-08-24-01-11-38_pi0-2
passed in 
Processing 2023-08-24-01-04-59_pi0-2
Processing 2023-08-24-01-11-38_pi0-2
Adding markers

Done

user@VM:/home/user/Blue2thprinting/Scripts: ls -la bt_map.html 
-rw-r--r-- 1 user user 9012 Aug 24 01:31 bt_map.html
```

The file bt_map.html can be opened in a browser to see the GPS locations of named devices.

*Note:* The accepted name format is just the filename, not the full path. You must remove the filetype suffix like ".txt" or ".bin".
