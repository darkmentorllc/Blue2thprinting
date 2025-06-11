# Analysis best practices

**Note:** Because data parsing and database lookups can be CPU/IO intensive, it is generally recommended to *not* perform data import or analysis on the same device with which you capture traffic, unless theyre both a laptop. Rather, it is recommended to copy all data off to a separate, faster, analysis system, and perform the subsequent steps there.

# [BTIDALPOOL](./BTIDALPOOL.md) QUICKSTART!

Thanks to [BTIDALPOOL](./BTIDALPOOL.md), the crowdsourcing server, you no longer have to collect your own data before you can get started! You can just pull some data from the server and start looking around immediately! (The sample data is stuff that Xeno collected at hacking conferences like DEF CON, Hardwear.io USA/NL, RingZer0, H2HC, Hack.lu, NoHat, Hackvitivy, SecTor, CanSecWest, etc.!)

```
cd ~
sudo apt install -y git
git clone --branch BTIDES https://github.com/darkmentorllc/Blue2thprinting
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

```
	DeviceName: [TV] Samsung AU9000 65 TV
	DeviceNameType: Complete Name
		In BT Classic Data (DB:EIR_bdaddr_to_name)
	DeviceName: [TV] Samsung AU9000 65 TV
	DeviceNameType: Shortened Name
		This was found in an event of type 4 which corresponds to Scan Response (SCAN_RSP)

	UUID16s found:
		UUID16 110a (Service ID: Audio Source)
		UUID16 110b (Service ID: Audio Sink)
		UUID16 110c (Service ID: A/V Remote Control Target)
		UUID16 110e (Service ID: A/V Remote Control)
		UUID16 1200 (Service ID: PnPInformation)
```

If you don't see tht specific entry, you could find it by looking for a specific Bluetooth Device Address (BDADDR) with the following command (augmented with the `./tf` token you saved above.)

`python3 ./Tell_Me_Everything.py --query-BTIDALPOOL --token-file ./tf --bdaddr 04:b9:e3:07:2a:85`

## Inspecting data with `Tell_Me_Everything.py`

`cd ~/Blue2thprinting/Analysis`

Issue `python3 ./Tell_Me_Everything.py --help` for the latest usage.

**If you get an error like "public/path/something can't be found"**, make sure your `~/Blue2thprinting/Analysis/public` folder is not empty. If it is empty, that implies you didn't run `sudo ~/Blue2thprinting/setup_analysis_helper_debian-based.sh`, and you should go do that or other things will break.

**Printing information for a specific BDADDR**:

`python3 ./Tell_Me_Everything.py --bdaddr 4c:e6:c0:21:39:a6`

**Printing information for BDADDRs that have a name that matches a given regex**:

`python3 ./Tell_Me_Everything.py --name-regex "^Flipper"`

The regex is used as a MySQL "REGEXP" statement, and thus must be valid MySQL regex syntax.

**Printing information for BDADDRs that have some data element that is associated with a company name that matches a given regex**:

`python3 ./Tell_Me_Everything.py --company-regex "^Qualcomm"`

The regex is checked against associations with the BDADDR IEEE OUI, UUID16s, and BT/BLE CompanyID fields from link layer version information.

**Printing information for BDADDRs that have a UUID128 that matches a given regex**:

`python3 ./Tell_Me_Everything.py --UUID-regex "02030302"`

**Printing information for BDADDRs that have Manufacturer Specific Data that matches a given regex**:

`python3 ./Tell_Me_Everything.py --MSD-regex "008fc3d5"`

# Analysis Scripts Usage

After you have sniffed some traffic, you will have files in `~/Blue2thprinting/Logs/btmon/`.

**Note:** Because data parsing and database lookups can be CPU/IO intensive, it is generally recommended to *not* perform data import or analysis on the capture device (the UP^2 in this case.) Rather, it is recommended to copy all data off to a separate, faster, analysis system, and perform the subsequent steps there.

### `dump_names_specific.sh`

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

Copyright(c) © Dark Mentor LLC 2023-2025
