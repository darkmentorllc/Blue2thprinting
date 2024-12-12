import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import create_urllib3_context
import ssl
import argparse
import json
import sys

class SSLAdapter(HTTPAdapter):
    def __init__(self, certfile=None, keyfile=None, password=None, **kwargs):
        self.certfile = certfile
        self.keyfile = keyfile
        self.password = password
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        try:
            context.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile, password=self.password)
            context.check_hostname = False  # Disable hostname checking
            context.verify_mode = ssl.CERT_NONE  # Disable certificate verification
        except ssl.SSLError as e:
            print(f"Error loading cert chain: {e}")
            raise
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Send JSON data to the server.')
    parser.add_argument('username', type=str, help='Username')
    parser.add_argument('json_file', type=str, help='Path to the JSON file')
    args = parser.parse_args()

    # Load the JSON content from the file
    try:
        with open(args.json_file, 'r') as f:
            json_content = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    # Load the self-signed certificate and key
    cert_path = "BTIDALPOOL-local-cert.pem"
    key_path = "BTIDALPOOL-local-key.pem"

    # Create a session and mount the SSL adapter
    session = requests.Session()
    session.mount('https://', SSLAdapter(certfile=cert_path, keyfile=key_path))

    # Suppress the InsecureRequestWarning
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Prepare the data to send
    data = {
        "username": args.username,
        "json_content": json_content
    }

    # Make a request to the server
#    response = session.post("https://localhost:4443", json=data, verify=False)
    response = session.post("https://3.145.185.23:4443", json=data, verify=False)

    # Print the response
    print(response.text)

if __name__ == "__main__":
    main()