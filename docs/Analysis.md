# [BTIDALPOOL](./BTIDALPOOL.md) QUICKSTART!

Thanks to [BTIDALPOOL](./BTIDALPOOL.md), the crowdsourcing server, you no longer have to collect your own data before you can get started! You can just pull some data from the server and start looking around immediately! (The sample data is stuff that Xeno collected at hacking conferences like DEF CON, Hardwear.io USA/NL, RingZer0, H2HC, Hack.lu, NoHat, SecTor, CanSecWest, etc.!)

```
cd ~
sudo apt install -y git
git clone https://github.com/darkmentorllc/Blue2thprinting
cd Blue2thprinting
sudo ./setup_analysis_helper_debian-based.sh
```

That script will perform required software installation and some one-time database initialization. You can then proceed to run a test query against BTIDALPOOL:

```
cd Analysis
python3 ./Tell_Me_Everything.py --query-BTIDALPOOL --name-regex "Samsung" 
```

The first time you use an argument like `--query-BTIDALPOOL` or `--to-BTIDALPOOL`, you will be prompted for a Google OAuth single-sign-on login, like the following:

```
Please visit this URL to authenticate:
https://accounts.google.com/o/oauth2/auth?response_type=code&client_id=934838710114-hrn5hafisthr3eqh7gnr1jka5c5hmjli.apps.googleusercontent.com&redirect_uri=https%3A%2F%2Fbtidalpool.ddns.net%3A7653%2Foauth2callback&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.email+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.profile&state=k8nDQob2xEqPngwj3GrpZPWLMU5Xzu&prompt=consent&access_type=offline

After authentication, copy the entire JSON token from the browser:
Token: 
```

 Navigate to the printed out SSO URL and use any throwaway Google account. You will receive a JSON authentication token like the following from the web page:

`{"token": "ya29.a0AXeO80T7U4kRn46t37622aicxfPcDzecZtarP3p5nPurIRbsAX33I_Rbfas23pM-EQM4Lsn39287flybxRCFEErsuM37_ymU-7i-Y8EX56xxekSl5F5Rq4Bbbsn1ktvvPTXY3rVuT_UXQFGS9vQjeAdowNgKsDqdr387LaShel0T561aCgYKAYESARASFQChangMiaVpYH3EQo8nnYFrbD5racw0175", "refresh_token": "1//04AGf0b8ENKDCgYIARAAGAQSNwF-L9IrEHgZ1sn4rkE9cuz121bx8M3KUCCEBIEzoabroBj4ChUpuMo6Y9yMtx83wmHKlcU"}`

Paste that token into the command where asked. But also store it into a file named `./tf` so you can pass `--token-file ./tf` in the future and skip navigating to the website again.

For the above query, you will likely see output like the following (though it will change over time as more data is added.)

# Analysis Scripts Usage

After you have sniffed some traffic, you will have files in ~/Blue2thprinting/Logs/btmon/ and ~/Blue2thprinting/Logs/gpspipe/, that should be named the same as each other (timestamp followed by hostname) except that GPS files end in .txt and btmon in .bin.

**Note:** Because data parsing and database lookups can be CPU/IO intensive, it is generally recommended to *not* perform data import or analysis on the capture device (the UP^2 in this case.) Rather, it is recommended to copy all data off to a separate, faster, analysis system, and perform the subsequent steps there.

### dump\_names\_specific.sh

Assume we have the following files:

```
user@VM:/home/user/Blue2thprinting/# ls Logs/btmon/
2023-08-24-01-04-59_pi0-2.bin  2023-08-24-01-11-38_pi0-2.bin
```

The named bluetooth devices found in multiple files can be dumped to stdout as follows:

```
./dump_names_specific.sh 2023-08-24-01-04-59_pi0-2.bin 2023-08-24-01-11-38_pi0-2.bin
Processing  /home/user/Blue2thprinting/Logs/btmon/2023-08-24-01-04-59_pi0-2.bin
btmon -T -r /home/user/Blue2thprinting/Logs/btmon/2023-08-24-01-04-59_pi0-2.bin.bin | grep -e "Name (.*):" | sort | uniq
Processing  /home/user/Blue2thprinting/Logs/btmon/2023-08-24-01-11-38_pi0-2.bin
btmon -T -r /home/user/Blue2thprinting/Logs/btmon/2023-08-24-01-11-38_pi0-2.bin.bin | grep -e "Name (.*):" | sort | uniq
All found names:
        Name (complete): This_is-not_real
        Name (complete): Neither is this😎
        Name (complete): BecauseWiGLEWouldTellYouWhereILive:P
```
from within the Scripts folder.

*Note:* The accepted name format is just the filename, not the full path.

## Import data into MySQL

**Note:** Because data parsing and database lookups can be CPU/IO intensive, it is generally recommended to *not* perform data import or analysis on the capture device (the UP^2 in this case.) Rather, it is recommended to copy all data off to a separate, faster, analysis system, and perform the subsequent steps there.

### One time setup

**Linux Software Setup**: You should already have the necessary MySQL (MariaDB) database and tshark tools installed from the above apt-get commands.

```
cd ~/Blue2thprinting
sudo ./setup_analysis_helper_debian-based.sh
```

**macOS Software Setup**: macOS cannot be used for collection, but it can be used for analysis of files collected on other platforms. You must first [install HomeBrew](https://brew.sh/), and then run `brew install mysql` and `brew install wireshark` (for the `tshark` CLI version). (If for some reason neither tshark nor wireshark are found in your PATH, look in / add from /usr/local/Cellar/wireshark/). Then also edit `/usr/local/etc/my.cnf` and add `secure_file_priv = /tmp` at the end of the file, and then start the mysql server with `/usr/local/opt/mysql/bin/mysqld_safe --datadir=/usr/local/var/mysql`.

Then run

```
cd ~/Blue2thprinting
sudo ./setup_analysis_helper_macOS.sh
```

The above `setup_analysis_helper*.sh` scripts should be re-run if you ever do a "git pull" in the `Blue2thprinting/public` directory, which contains the Bluetooth Assigned Numbers information, to get updated assigned vendor UUID16s.

### Importing data from btmon .bin HCI log files

**Import ExampleData:**

```
cd ~/Blue2thprinting/Analysis
./parse_HCI_2db.sh ../ExampleData/2023-10-06-08-52-20_up-apl01.bin
```

You should see a variety of outputs such as "tsharking", and "mysql import". You can safely ignore any tshark warnings about the file being "cut short in the middle of a packet".

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt -e "SELECT * FROM LE_bdaddr_to_name LIMIT 10;"
```

This should show some of the same sort of device name data that you could see by the above `./dump_names_specific.sh` command.

**Import your own data:**

Eventually once you have many files from your own collection that you want to process in bulk, you will want to pass each file to `parse_HCI_2db.sh` sequentially. For that you can issue a command like:

`time find ~/Blue2thprinting/Logs/btmon/2024-06* -type f -name "*.bin" | xargs -n 1 -I {} bash -c " ./parse_HCI_2db.sh {}"`

### Importing GATT data from GATTprint.log

Both `central_app_launcher2.py` and `gatttool` log information about attempted and successful GATTprinting to the file `/home/user/Blue2thprinting/Logs/GATTprint.log` (or alt user home directory if you reconfigured it). To import this data into the database, run the following:

```
cd ~/Blue2thprinting/Analysis/
cat ~/Blue2thprinting/Logs/GATTprint*.log | sort | uniq > GATTprint_dedup.log
python3 ./parse_GATTPRINT_2db.py
```

The above `cat` step is useful both to speed up the parsing of a single host's data (if it queried the same host multiple times), but also to combine data from multiple hosts, and avoid unnecessary duplicative mysql imports.

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt -e "SELECT * FROM GATT_characteristics LIMIT 10;"
```

### Importing BLE LL data from BLE_2THPRINT.log

Both `central_all_launcher2.py` and my `LL2thprint.py` Sweyntooth module log information about attempted and successful LL2thprint to the file `/home/user/Blue2thprinting/Logs/BLE_2THPRINT.log` (or alt user home directory if you reconfigured it). To import this data into the database, run the following:

```
cd ~/Blue2thprinting/Analysis/
cat ~/Blue2thprinting/Logs/BLE_2THPRINT*.log | sort | uniq > BLE_2THPRINT_dedup.log
python3 ./parse_BLE_2THPRINT_2db.py
```

The above `cat` step is useful both to speed up the parsing of a single host's data (if it queried the same host multiple times), but also to combine data from multiple hosts, and avoid unnecessary duplicative mysql imports.

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt -e "SELECT * FROM LL_VERSION_IND LIMIT 10;"
```

### Importing BTC LMP data from BTC_2THPRINT.log

Both `central_all_launcher2.py` and my `LMP2thprint.cpp` Braktooth module log information about attempted and successful LL2thprint to the file `/home/user/Blue2thprinting/Logs/BTC_2THPRINT.log` (or alt user home directory if you reconfigured it). To import this data into the database, run the following:

```

cd ~/Blue2thprinting/Analysis/
python3 ./parse_BTC_2THPRINT_2db.py
```

Unfortunately no deduplication of data is possible currently due to the fact that I don't know how to obtain the BDADDR from within Braktooth and add it to every log line. If you know how, LMK! Because currently this is dependent on `central_all_launcher2.py` prepending log entries to let the parsing know what BDADDR the subsequent data is for.

**To confirm that some data was successfully imported, you can issue:**

```
mysql -u user -pa -D bt -e "SELECT * FROM LMP_VERSION_RES LIMIT 10;"
```

## Inspecting data with TellMeEverything.py

`cd ~/Blue2thprinting/Analysis`

You will need Python3 installed, and you may need to change the path to the python3 interpreter at the beginning of the file. You will also need to do `pip3 install mysql-connector-python`, `pip3 install pyyaml` if you have not already.

Issue `python3 ./TellMeEverything.py --help` for the latest usage.

**If you get an error like "public/path/something can't be found"**, make sure your `~/Blue2thprinting/Analysis/public` folder is not empty. If it is empty, that implies you didn't check out the Bluetooth assigned numbers sub-module at git repository clone time. This can be corrected by issuing `git submodule update --init --recursive`.

**Printing information for a specific BDADDR**:

`python3 ./TellMeEverything.py --bdaddr 4c:e6:c0:21:39:a6`

**Printing information for BDADDRs that have a name that matches a given regex**:

`python3 ./TellMeEverything.py --nameregex "^Flipper"`

The regex is used as a MySQL "REGEXP" statement, and thus must be valid MySQL regex syntax.

**Printing information for BDADDRs that have some data element that is associated with a company name that matches a given regex**:

`python3 ./TellMeEverything.py --companyregex "^Qualcomm"`

The regex is checked against associations with the BDADDR IEEE OUI, UUID16s, and BT/BLE CompanyID fields from link layer version information.

**Printing information for BDADDRs that have a UUID128 that matches a given regex**:

`python3 ./TellMeEverything.py --UUID128regex "02030302"`

**Printing information for BDADDRs that have Manufacturer Specific Data that matches a given regex**:

`python3 ./TellMeEverything.py --MSDregex "008fc3d5"`

Copyright(c) © Dark Mentor LLC 2023-2025