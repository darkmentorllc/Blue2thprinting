# Notes on what was needed to set up on Ubuntu AWS server:
1) sudo apt update
2) sudo apt install python3-pip
3) pip3 install jsonschema --break-system-packages
4) pip3 install referencing --break-system-packages

# Copy files onto AWS server
1) scp the Server-BTIDALPOOL.py
scp -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem Server-BTIDALPOOL.py ubuntu@btidalpool.ddns.net:~/
2) scp the public/private key
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem BTIDALPOOL-loca* ubuntu@btidalpool.ddns.net:~/
3) scp the BTIDES_Schema folder
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem BTIDES_Schema ubuntu@btidalpool.ddns.net:~/

# Modify files:
Modify client and server to use 'btidalpool.ddns.net' instead of 'localhost'

# Then it can just be run with
python3 Server-BTIDALPOOL.py

---

# Setting up further MySQL infrastructure
sudo apt install python3-mysql.connector mariadb-server
git clone https://github.com/darkmentorllc/Blue2thprinting
cd ~/Blue2thprinting
sudo ./Analysis/one_time_initialization/initialize_test_database.sh
sudo ./Analysis/one_time_initialization/initialize_test_database.sh

# Copy over BTIDES_to_SQL.py
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem BTIDES_to_SQL.py ubuntu@btidalpool.ddns.net:~/
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem TME ubuntu@btidalpool.ddns.net:~/
