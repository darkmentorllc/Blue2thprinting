# Notes on what was needed to set up on Ubuntu AWS server:
1) sudo apt update
2) sudo apt install python3-pip
3) pip3 install jsonschema --break-system-packages
4) pip3 install referencing --break-system-packages

# Copy files onto AWS server
1) scp the Server-BTIDALPOOL.py
scp -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem Server-BTIDALPOOL.py ubuntu@3.145.185.23:~/ 
2) scp the public/private key
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem BTIDALPOOL-loca* ubuntu@3.145.185.23:~/
3) scp the BTIDES_Schema folder
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem BTIDES_Schema ubuntu@3.145.185.23:~/

# Modify files:
Modify client and server to use '3.145.185.23' instead of 'localhost'

# Then it can just be run with 
python3 Server-BTIDALPOOL.py

---

# Setting up further MySQL infrastructure
sudo apt install python3-mysql.connector mariadb-server
git clone https://github.com/darkmentorllc/Blue2thprinting
cd ~/Blue2thprinting
sudo ./Analysis/one_time_initialization/initialize_test_database.sh
sudo ./Analysis/one_time_initialization/initialize_test_database.sh

# Copy over BTIDES_to_MySQL.py
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem BTIDES_to_MySQL.py ubuntu@3.145.185.23:~/
scp -r -i /Users/xeno/Blue2thprinting/Analysis/jakerue.pem TME ubuntu@3.145.185.23:~/
