
# Import data into MySQL

**Note:** Because data parsing and database lookups can be CPU/IO intensive, it is generally recommended to *not* perform data import or analysis on the capture device (the UP^2 in this case.) Rather, it is recommended to copy all data off to a separate, faster, analysis system, and perform the subsequent steps there.

## One time setup

**Linux Software Setup**: You should already have the necessary MySQL (MariaDB) database and tshark tools installed from the above apt-get commands.

```
cd ~/Blue2thprinting
sudo ./setup_analysis_helper_ubuntu2404.sh
```

**macOS Software Setup**: macOS cannot be used for collection, but it can be used for analysis of files collected on other platforms. You must first [install HomeBrew](https://brew.sh/), and then run `brew install mysql`. Then also edit `/usr/local/etc/my.cnf` and add `secure_file_priv = /tmp` at the end of the file, and then start the mysql server with `/usr/local/opt/mysql/bin/mysqld_safe --datadir=/usr/local/var/mysql`.

Then run

```
cd ~/Blue2thprinting
sudo ./setup_analysis_helper_macOS.sh
```

The above `setup_analysis_helper*.sh` scripts should be re-run if you ever do a "git pull" in the `Blue2thprinting/public` directory, which contains the Bluetooth Assigned Numbers information, to get updated assigned vendor UUID16s.

## Importing data from btmon .bin HCI log files and Sniffle .pcap files

**Import ExampleData:**

```
cd ~/Blue2thprinting/Analysis
./Import_All_HCI_and_PCAP.py --HCI-logs-folder ../ExampleData/ --pcaps-folder ../ExampleData/
```

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt2 -e "SELECT * FROM LE_bdaddr_to_name LIMIT 10;"
```

This should show some of the same sort of device name data that you could see by the above `./dump_names_specific.sh` command.

**Import your own data:**

Eventually once you have many files from your own collection that you want to process in bulk, you will run the below command:

```
cd ~/Blue2thprinting/Analysis
./Import_All_HCI_and_PCAP.py --HCI-logs-folder ../Logs/btmon/ --pcaps-folder ../Logs/sniffle/
```


## Importing SDP data from sdptool XML files

The `central_all_launcher.py` collection script saves `sdptool` output as per-device XML files named `{BDADDR}_sdp.xml` under `Logs/sdptool/`. Use `SDP_to_BTIDES.py` to import these into the database.

**Import a single device's SDP file:**

```
cd ~/Blue2thprinting/Analysis
python3 SDP_to_BTIDES.py --input ../Logs/sdptool/<BDADDR>_sdp.xml \
    --output /tmp/sdp_single.btides --to-SQL
```

**Import all SDP files from the default collection directory:**

```
cd ~/Blue2thprinting/Analysis
python3 SDP_to_BTIDES.py --input ../Logs/sdptool/ \
    --output /tmp/sdp_all.btides --to-SQL
```

The `--output` flag writes a BTIDES JSON file alongside the SQL import, which is useful for inspection. If you only want the SQL import and don't need to keep the intermediate file, you may omit `--output` (though at least one of `--output` or `--to-SQL` must be specified).

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt2 -e "SELECT bdaddr, pdu_id FROM SDP_Common LIMIT 10;"
```

**Additional flags:**

- `--verbose-print` — show per-file progress as files are processed
- `--verbose-BTIDES` — include optional human-readable fields in the BTIDES JSON output
- `--use-test-db` — import into the `bttest` database instead of `bt2`
- `--quiet-print` — suppress all console output


## Importing BTC LMP data from BTC_2THPRINT.log

`central_app_launcher.py` invokes `DarkFirmware_VSC_LMP` (BlueZ + Realtek custom firmware) to capture LMP PDUs from each discovered BR/EDR device, and writes attempt/success markers plus the captured PDU stream into `/home/user/Blue2thprinting/Logs/BTC_2THPRINT.log` (or alt user home directory if you reconfigured it). To import this data into the database, (copy the data from your capture system to your analysis system, if applicable, and then) run the following:

```

cd ~/Blue2thprinting/Analysis/
python3 ./parse_BTC_2THPRINT_2db.py
```

The launcher prepends a per-device log entry before each invocation so the parser can attribute the subsequent PDU stream to the right BDADDR.

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt -e "SELECT * FROM LMP_VERSION_RES LIMIT 10;"
```

Copyright(c) © Dark Mentor LLC 2023-2026
