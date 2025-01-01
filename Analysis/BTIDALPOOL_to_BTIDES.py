import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import create_urllib3_context
from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
import ssl
import argparse
import json
import sys
import datetime
import hashlib
import re

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

def load_schemas():
    # Load all the local BTIDES json schema files.
    BTIDES_files = [
        "BTIDES_base.json",
        "BTIDES_AdvData.json",
        "BTIDES_LL.json",
        "BTIDES_HCI.json",
        "BTIDES_L2CAP.json",
        "BTIDES_SMP.json",
        "BTIDES_ATT.json",
        "BTIDES_GATT.json",
        "BTIDES_EIR.json",
        "BTIDES_LMP.json",
        "BTIDES_SDP.json",
        "BTIDES_GPS.json"
    ]
    all_schemas = []
    for file in BTIDES_files:
        with open(f"./BTIDES_Schema/{file}", 'r') as f:
            s = json.load(f)
            schema = Resource.from_contents(s)
            all_schemas.append((s["$id"], schema))
    return Registry().with_resources(all_schemas)

def validate_json_content(json_content, registry):
    # Validate the json_content against the BTIDES_base.json schema.
    try:
        Draft202012Validator(
            {"$ref": "https://darkmentor.com/BTIDES_Schema/BTIDES_base.json"},
            registry=registry,
        ).validate(instance=json_content)
        return True
    except ValidationError as e:
        print(f"JSON data is invalid per BTIDES Schema. Error: {e.message}")
        return False

# Import this function to call from external code without invoking via the CLI
def retrieve_btides_from_btidalpool(username, query_object):

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
        "username": username,
        "query": query_object
    }

    # Make a request to the server
    try:
        #response = session.post("https://localhost:4443", json=data, verify=False) # for local testing
        response = session.post("https://btidalpool.ddns.net:4443", json=data, verify=False)
        if response.headers.get('Content-Type') == 'application/json':
            json_content = response.json()
            # Load the schemas and create a registry
            registry = load_schemas()

            # Validate the JSON content
            if not validate_json_content(json_content, registry):
                print("Invalid JSON data according to schema")
                sys.exit(1)
        elif response.headers.get('Content-Type') == 'text/plain':
            print(response.text)
            sys.exit(1)
        else:
            print("Response content is not JSON.")
            sys.exit(1)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 or e.response.status_code == 429:
            #print("Expected HTTP error code received")
            print(response.text)
            pass
        else:
            print(f"Unexpected HTTP error occurred: {e}")
            sys.exit(1)
    except requests.exceptions.ChunkedEncodingError as e:
        print("The connection was most likely reset due to exceeding rate limits.")
        # Due to optimization on the server side this is the exception case that will occur.
        # Making it a nice mesaage for the user, rather than making the server do more work than necessary.
        #print(f"Chunked encoding error occurred: {e}")
        sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        print(f"Unexpected connection error occurred (Server may not be running?): {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

    # Write the JSON content to a file
    current_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    json_content_str = json.dumps(json_content, sort_keys=True)
    sha1_hash = hashlib.sha1(json_content_str.encode('utf-8')).hexdigest()
    output_filename = f'./pool_files/{sha1_hash}-{username}-{current_time}.json'

    try:
        # Save the JSON content to the file
        with open(output_filename, 'w') as f:
            json.dump(json_content, f)
    except Exception as e:
        print(f"Error writing JSON file: {e}")
        sys.exit(1)

    return output_filename

def validate_username(value):
    if len(value) > 255:
        raise argparse.ArgumentTypeError("Username must be 255 characters or less.")
    return value

def validate_bdaddr(value):
    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', value):
        raise argparse.ArgumentTypeError("bdaddr must be in the form of a Bluetooth Device Address (e.g., AA:BB:CC:11:22:33).")
    return value

def main():
    parser = argparse.ArgumentParser(description='Send BTIDES data to BTIDALPOOL server.')

    parser.add_argument('--username', type=validate_username, required=True, help='Username to attribute the upload to.')
    parser.add_argument('--bdaddr', type=validate_bdaddr, required=False, help='Device bdaddr value.')
    parser.add_argument('--nameregex', type=str, default='', required=False, help='Value for REGEXP match against device_name.')

    args = parser.parse_args()

    query_object = {}
    if args.bdaddr:
        query_object["bdaddr"] = args.bdaddr
    if args.nameregex:
        query_object["nameregex"] = args.nameregex

    output_filename = retrieve_btides_from_btidalpool(
        username=args.username,
        query_object=query_object
    )
    print(f"BTIDES data retrieved from BTIDALPOOL and saved to {output_filename}")

if __name__ == "__main__":
    main()