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

import ssl
import argparse
import json
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from urllib3.util.ssl_ import create_urllib3_context
from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
from oauth_helper import AuthClient
from TME.TME_helpers import vprint
import TME.TME_glob

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
def send_btides_to_btidalpool(input_file, token, refresh_token):
    vprint(f"Sending BTIDES file {input_file}")
    # Load the JSON content from the file
    try:
        with open(input_file, 'r') as f:
            json_content = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    # Load the schemas and create a registry
    registry = load_schemas()

    # Validate the JSON content
    vprint("Validating BTIDES Schema on input file...")
    if not validate_json_content(json_content, registry):
        print("Invalid JSON data according to schema")
        sys.exit(1)
    vprint("Validating passed!")

    # Load the self-signed certificate and key
    cert_path = "BTIDALPOOL-client.crt"
    key_path = "BTIDALPOOL-client.key"

    # Create a session and mount the SSL adapter
    session = requests.Session()
    session.mount('https://', SSLAdapter(certfile=cert_path, keyfile=key_path))

    # Prepare the data to send
    data = {
        "command": 'upload',
        "btides_content": json_content,
        "token": token,
        "refresh_token": refresh_token
    }

    # Make a request to the server
    try:
        if(g_local_testing):
            # Suppress the InsecureRequestWarning
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = session.post("https://localhost:3567", json=data, verify=False)
        else:
            response = session.post("https://btidalpool.ddns.net:3567", json=data, verify='./btidalpool.ddns.net.crt')
        if response.headers.get('Content-Type') == 'text/plain':
            print(response.text)
        else:
            print("Response content is not plain text")
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 or e.response.status_code == 429:
            #print("Expected HTTP error code received")
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

def main():
    parser = argparse.ArgumentParser(description='Send BTIDES data to BTIDALPOOL server.')
    parser.add_argument('--input', type=str, required=True, help='Input file name for BTIDES JSON file.')
    parser.add_argument('--verbose-print', action='store_true', required=False, help='Print verbose output.')

    auth_group = parser.add_argument_group('Arguments for authentication to BTIDALPOOL server.')
    auth_group.add_argument('--token-file', type=str, required=False, help='Path to file containing JSON with the \"token\" and \"refresh_token\" fields, as obtained from Google SSO. If not provided, you will be prompted to perform Google SSO, after which you can save the token to a file and pass this argument.')
    args = parser.parse_args()

    TME.TME_glob.verbose_print = args.verbose_print

    # If the token isn't given on the CLI, then redirect them to go login and get one
    client = AuthClient()
    if args.token_file:
        with open(args.token_file, 'r') as f:
            token_data = json.load(f)
        token = token_data['token']
        refresh_token = token_data['refresh_token']
        client.set_credentials(token, refresh_token, token_file=args.token_file)
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

    # Use the copy of token/refresh_token in client.credentials, because it could have been refreshed inside validate_credentials()
    send_btides_to_btidalpool(
        input_file=args.input,
        token=client.credentials.token,
        refresh_token=client.credentials.refresh_token
    )

if __name__ == "__main__":
    main()