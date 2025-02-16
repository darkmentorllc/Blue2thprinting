########################################
# Created by Xeno Kovah
# Copyright(c) Dark Mentor LLC 2023-2025
########################################

# Activate venv before any other imports
import os
import sys
from pathlib import Path
from handle_venv import activate_venv
activate_venv()

import requests
import urllib3
import ssl
import argparse
import json
import datetime
import hashlib
import re
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import create_urllib3_context
from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
from oauth_helper import AuthClient

g_local_testing = False

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
def retrieve_btides_from_btidalpool(email, query_object, token, refresh_token):

    # Load the self-signed certificate and key
    cert_path = "BTIDALPOOL-client.crt"
    key_path = "BTIDALPOOL-client.key"

    # Create a session and mount the SSL adapter
    session = requests.Session()
    session.mount('https://', SSLAdapter(certfile=cert_path, keyfile=key_path))

    # Prepare the data to send
    data = {
        "command": 'query',
        "query": query_object,
        "token": token,
        "refresh_token": refresh_token
    }

    # Make a request to the server
    try:
        if(g_local_testing):
            # Suppress the InsecureRequestWarning
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = session.post("https://localhost:3567", json=data, verify=False) # for local testing
        else:
            response = session.post("https://btidalpool.ddns.net:3567", json=data, verify='./btidalpool.ddns.net.crt')
        if response.headers.get('Content-Type') == 'application/json':
            json_content = response.json()
            # Load the schemas and create a registry
            registry = load_schemas()

            # Validate the JSON content
            if not validate_json_content(json_content, registry):
                print("Invalid JSON data according to schema")
                return (None, None)
        elif response.headers.get('Content-Type') == 'text/plain':
            print(response.text)
            return (None, None)
        else:
            print("Response content is not JSON.")
            return (None, None)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 or e.response.status_code == 429:
            #print("Expected HTTP error code received")
            print(response.text)
            pass
        else:
            print(f"Unexpected HTTP error occurred: {e}")
            return (None, None)
    except requests.exceptions.ChunkedEncodingError as e:
        print("The connection was most likely reset due to exceeding rate limits.")
        # Due to optimization on the server side this is the exception case that will occur.
        # Making it a nice mesaage for the user, rather than making the server do more work than necessary.
        #print(f"Chunked encoding error occurred: {e}")
        return (None, None)
    except requests.exceptions.ConnectionError as e:
        print(f"Unexpected connection error occurred (Server may not be running?): {e}")
        return (None, None)
    except requests.exceptions.RequestException as e:
        print(f"An unexpected error occurred: {e}")
        return (None, None)

    # Write the JSON content to a file
    current_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    json_content_str = json.dumps(json_content, sort_keys=True)
    sha1_hash = hashlib.sha1(json_content_str.encode('utf-8')).hexdigest()
    # Create the pool_files directory if it doesn't exist
    os.makedirs('./pool_files', exist_ok=True)
    output_filename = f'./pool_files/{sha1_hash}-{email}-{current_time}.json'

    try:
        # Save the JSON content to the file
        with open(output_filename, 'w') as f:
            json.dump(json_content, f)
    except Exception as e:
        print(f"Error writing JSON file: {e}")
        sys.exit(1)

    return (len(json_content), output_filename)


def validate_bdaddr(value):
    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', value):
        raise argparse.ArgumentTypeError("bdaddr must be in the form of a Bluetooth Device Address (e.g., AA:BB:CC:11:22:33).")
    return value


def main():
    parser = argparse.ArgumentParser(description='Send BTIDES data to BTIDALPOOL server.')

    # Requirement arguments
    auth_group = parser.add_argument_group('Arguments for authentication to BTIDALPOOL server.')
    auth_group.add_argument('--token-file', type=str, required=False, help='Path to file containing JSON with the \"token\" and \"refresh_token\" fields, as obtained from Google SSO. If not provided, you will be prompted to perform Google SSO, after which you can save the token to a file and pass this argument.')

    device_group = parser.add_argument_group('Database search arguments')
    device_group.add_argument('--bdaddr', type=validate_bdaddr, required=False, help='Device bdaddr value.')
    device_group.add_argument('--bdaddr-regex', type=str, default='', required=False, help='Regex to match a bdaddr value.')
    device_group.add_argument('--bdaddr-type', type=int, default=0, help='BDADDR type (0 = LE Public (default), 1 = LE Random, 2 = Classic, 3 = Any).')
    device_group.add_argument('--name-regex', type=str, default='', help='Value for REGEXP match against device_name.')
    device_group.add_argument('--NOT-name-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --name-regex, and then remove them from the final results.')
    device_group.add_argument('--company-regex', type=str, default='', help='Value for REGEXP match against company name, in IEEE OUIs, or BT Company IDs, or BT Company UUID16s.')
    device_group.add_argument('--NOT-company-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --company-regex, and then remove them from the final results.')
    device_group.add_argument('--UUID128-regex', type=str, default='', help='Value for REGEXP match against UUID128, in advertised UUID128s.')
    device_group.add_argument('--NOT-UUID128-regex', type=str, default='', help='Find the bdaddrs corresponding to the regexp, the same as with --UUID128-regex, and then remove them from the final results.')
    device_group.add_argument('--UUID16-regex', type=str, default='', help='Value for REGEXP match against UUID16, in advertised UUID16s.')
    device_group.add_argument('--MSD-regex', type=str, default='', help='Value for REGEXP match against Manufacturer-Specific Data (MSD).')

    # Requirement arguments
    requirement_group = parser.add_argument_group('Arguments which specify that a particular type of data is required in the printed out / exported data.')
    requirement_group.add_argument('--require-GATT-any', action='store_true', help='Pass this argument to only print out information for devices which have *some* GATT info.')
    requirement_group.add_argument('--require-GATT-values', action='store_true', help='Pass this argument to only print out information for devices which successfully read some GATT values.')
    requirement_group.add_argument('--require-LL_VERSION_IND', action='store_true', help='Pass this argument to only print out information for devices which have LL_VERSION_IND data.')
    requirement_group.add_argument('--require-LMP_VERSION_RES', action='store_true', help='Pass this argument to only print out information for devices which have LMP_VERSION_RES data.')

    args = parser.parse_args()

    query_object = {}
    if args.bdaddr:
        query_object["bdaddr"] = args.bdaddr
    if args.bdaddr_regex:
        query_object["bdaddr_regex"] = args.bdaddr_regex
    if args.name_regex:
        query_object["name_regex"] = args.name_regex
    if args.NOT_name_regex:
        query_object["NOT_name_regex"] = args.NOT_name_regex
    if args.company_regex:
        query_object["company_regex"] = args.company_regex
    if args.NOT_company_regex:
        query_object["NOT_company_regex"] = args.NOT_company_regex
    if args.UUID_regex:
        query_object["UUID_regex"] = args.UUID_regex
    if args.NOT_UUID_regex:
        query_object["NOT_UUID_regex"] = args.NOT_UUID_regex
    if args.UUID16_regex:
        query_object["UUID16_regex"] = args.UUID16_regex
    if args.MSD_regex:
        query_object["MSD_regex"] = args.MSD_regex
    if args.require_GATT_any:
        query_object["require_GATT_any"] = True
    if args.require_GATT_values:
        query_object["require_GATT_values"] = True
    if args.require_LL_VERSION_IND:
        query_object["require_LL_VERSION_IND"] = True
    if args.require_LMP_VERSION_RES:
        query_object["require_LMP_VERSION_RES"] = True

    # If the token isn't given on the CLI, then redirect them to go login and get one
    client = AuthClient()
    if args.token_file:
        with open(args.token_file, 'r') as f:
            token_data = json.load(f)
        client.set_credentials(token_data['token'], token_data['refresh_token'], token_file=args.token_file)
        if(not client.validate_credentials()):
            print("Authentication failed.")
            exit(1)
    else:
        try:
            if(not client.google_SSO_authenticate() or not client.validate_credentials()):
                print("Authentication failed.")
                exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            exit(1)

    # Using the presence of the email address as proof of successful authentication
    # Use the copy of token/refresh_token in client.credentials, because it could have been refreshed inside validate_credentials()
    if(client.user_info and client.user_info.get('email')):
        (num_records, output_filename) = retrieve_btides_from_btidalpool(
            email=client.user_info.get('email'),
            query_object=query_object,
            token=client.credentials.token,
            refresh_token=client.credentials.refresh_token
        )
        if(num_records and output_filename):
            print(f"{num_records} BTIDES data records retrieved from BTIDALPOOL and saved to {output_filename}")
        else:
            sys.exit(1)

if __name__ == "__main__":
    main()