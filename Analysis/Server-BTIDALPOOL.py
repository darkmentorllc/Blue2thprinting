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

import http.server
import ssl
import json
import datetime
import hashlib
import threading
import subprocess
import time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import GoogleAuthError
from googleapiclient.discovery import build
from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
from socketserver import ThreadingMixIn
from collections import defaultdict, deque
from pathlib import Path
from oauth_helper import AuthClient
from BTIDES_to_SQL import btides_to_sql_args, btides_to_sql

g_local_testing = False

# Global variables used for rate limiting
g_max_connections_per_day = 100
g_max_simultaneous_connections = 10
g_max_returned_records_per_query = 100

# Global dictionary to store unique file hashes for avoiding duplicate uploads
g_unique_files = {}

# Global dictionary to store connection data for rate limiting
connection_data = defaultdict(lambda: {"count": 0, "timestamps": deque()})

# Returns's email of authenticated user if successful, None otherwise
def validate_oauth_token(token_str, refresh_token_str):
    """Validate Google OAuth token."""
    try:
        client = AuthClient()
        client.set_credentials(token_str, refresh_token_str)
        if client.validate_credentials():
            # If validate_credentials() returns true, the credentials are valid,
            # and client.user_info will contain the user's information
            email = client.user_info.get('email')
            print(f"Authentication successful for user {email}!")
            return email
        else:
            print("Authentication failed. Unable to retrieve user information.")
            return None
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None


def initialize_unique_files(directory):
    """Initialize the g_unique_files dictionary with SHA1 hashes from existing files."""
    if not os.path.exists(directory):
        os.makedirs(directory)
    for filename in os.listdir(directory):
        if filename.endswith(".json"):
            sha1_hash = filename.split('-')[0]
            g_unique_files[sha1_hash] = True


def load_schemas():
    """Load all the local BTIDES json schema files."""
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


def run_btides_to_sql(filename):
    # Run the primary code from BTIDES_to_SQL.py script
    # TODO: make this run in a separate thread? (Need to check if it's already running in its own thread vs. other queries)
    b2s_args = btides_to_sql_args(input=filename, use_test_db=True)
    if(btides_to_sql(b2s_args)):
        os.rename(filename, filename + ".processed")

# args_array should be individual arguments to pass to the script
def run_TellMeEverything(self, username, args_array, output_filename):
    # Run the TellMeEverything.py script in a new thread.
    def target():
        # FIXME: update to refactor to not require subprocess.run (or to use a separate script)
        args_list = ["python3", "TellMeEverything.py"] + args_array + ["--output", output_filename]
        subprocess.run(args_list)
    thread = threading.Thread(target=target)
    thread.start()
    thread.join()

    try:
        with open(output_filename, 'r') as f:
            json_content = json.load(f)

            if len(json_content) == 0:  # Content is just []
                send_back_response(self, username, 400, 'text/plain', b'Query yielded empty result.')
                return 1

            # Validate the JSON content
            if not validate_json_content(json_content, registry):
                send_back_response(self, username, 400, 'text/plain', b'Query yielded invalid JSON data according to schema. Rejected.')
                return 1

    except FileNotFoundError:
        # This will happen if there's a bug that causes TellMeEverything to not write the output file
        send_back_response(self, username, 500, 'text/plain', b'Output file not found.')
        return 1

    return json_content


def rate_limit_checks(client_ip):
    """Check rate limits for the given IP address."""
    current_time = time.time()
    data = connection_data[client_ip]

    # Remove timestamps older than one day
    while data["timestamps"] and current_time - data["timestamps"][0] > 60 * 60 * 24:
        data["timestamps"].popleft()

    # Check the number of connections in the last hour
    if len(data["timestamps"]) >= g_max_connections_per_day:
        return False

    # Check the number of simultaneous connections
    if data["count"] >= g_max_simultaneous_connections:
        return False

    # Update connection data
    data["count"] += 1
    data["timestamps"].append(current_time)
    return True


def send_back_response(self, username, type, header, text):
    if(header == 'text/plain'):
        log_user_result(username, self.client_address[0], f"{type}: {text}")
    self.send_response(type)
    self.send_header('Content-Type', header)
    self.end_headers()
    self.wfile.write(text)
    self.wfile.flush()  # Ensure the response is sent


def handle_btides_data(self, username, json_content):
    # Parse the JSON data
    try:
        # Convert the data to a string to check the total data size
        json_content_str = json.dumps(json_content, sort_keys=True)

        # Check the size of the JSON content
        if len(json_content_str.encode('utf-8')) > 10 * 1024 * 1024:  # 10 megabytes
            send_back_response(self, username, 400, 'text/plain', b'File size too big.')
            return

        # Validate the JSON content
        if not validate_json_content(json_content, registry):
            send_back_response(self, username, 400, 'text/plain', b'Invalid JSON data according to schema. Rejected.')
            return

        # Create the directory if it doesn't exist
        os.makedirs('./pool_files', exist_ok=True)

        # Generate the SHA1 hash of the json_content
        sha1_hash = hashlib.sha1(json_content_str.encode('utf-8')).hexdigest()

        # Check if the file already exists
        if sha1_hash in g_unique_files:
            send_back_response(self, username, 400, 'text/plain', b'A file with this exact content already exists on the server.')
            return

        # Generate the filename
        current_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        filename = f'./pool_files/{sha1_hash}-{username}-{current_time}.json'

        # Save the JSON content to the file
        with open(filename, 'w') as f:
            json.dump(json_content, f)

        # Update the global dictionary
        g_unique_files[sha1_hash] = True

        # Spawn a new thread to run the BTIDES_to_SQL.py script
        run_btides_to_sql(filename)

        # Send a success response
        send_back_response(self, username, 200, 'text/plain', b'File saved successfully.')

    except json.JSONDecodeError:
        send_back_response(self, username, 400, 'text/plain', b'Invalid JSON data could not be decoded.')

def handle_query(self, username, query_object):
    print(query_object)

    # Arguments we always want to pass to TellMeEverything.py
    args_array = ["--use-test-db", "--max-records-output", str(g_max_returned_records_per_query), "--quiet-print"]

    # Can't just loop through and use everything we're handed in query_object,
    # only use arguments which we are expecting, and ignore everything else
    if("bdaddr" in query_object):
        args_array.append(f"--bdaddr")
        args_array.append(f"{query_object['bdaddr']}")
    if("bdaddr_regex" in query_object):
        args_array.append(f"--bdaddr-regex")
        args_array.append(f"{query_object['bdaddr_regex']}")
    if("name_regex" in query_object):
        args_array.append(f"--name-regex")
        args_array.append(f"{query_object['name_regex']}")
    if("NOT_name_regex" in query_object):
        args_array.append(f"--NOT-name-regex")
        args_array.append(f"{query_object['NOT_name_regex']}")
    if("company_regex" in query_object):
        args_array.append(f"--company-regex")
        args_array.append(f"{query_object['company_regex']}")
    if("NOT_company_regex" in query_object):
        args_array.append(f"--NOT-company-regex")
        args_array.append(f"{query_object['NOT_company_regex']}")
    if("UUID128_regex" in query_object):
        args_array.append(f"--UUID128-regex")
        args_array.append(f"{query_object['UUID128_regex']}")
    if("NOT_UUID128_regex" in query_object):
        args_array.append(f"--NOT-UUID128-regex")
        args_array.append(f"{query_object['NOT_UUID128_regex']}")
    if("UUID16_regex" in query_object):
        args_array.append(f"--UUID16-regex")
        args_array.append(f"{query_object['UUID16_regex']}")
    if("MSD_regex" in query_object):
        args_array.append(f"--MSD-regex")
        args_array.append(f"{query_object['MSD_regex']}")
    if("require_GATT" in query_object):
        args_array.append(f"--require-GATT")
    if("require_LL_VERSION_IND" in query_object):
        args_array.append(f"--require-LL_VERSION_IND")
    if("require_LMP_VERSION_RES" in query_object):
        args_array.append(f"--require-LMP_VERSION_RES")

    current_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    random = os.urandom(4).hex()
    output_filename = f"/tmp/{username}-{current_time}-{random}.json"

    json_content = run_TellMeEverything(self, username, args_array, output_filename)
    if(json_content == 1): # Error
        # Error message should have already been sent to the client in run_TellMeEverything
        return
    else:
        send_back_response(self, username, 200, 'application/json', json.dumps(json_content).encode('utf-8'))
        log_user_result(username, self.client_address[0], f"{len(json_content)} records returned.")

    # Delete the output file after sending the response
    if os.path.exists(output_filename):
        os.remove(output_filename)


log_file = open('./user_access.log', 'a')
log_mutex = threading.Lock()

# Append a log line to the user_access.log file.
def log_user_access(username, client_ip, post_json_data):
    # We don't want to save any of these fields in the log
    log_data = post_json_data.copy()
    log_data.pop('btides_content', None)
    log_data.pop('token', None)
    log_data.pop('refresh_token', None)
    log_line = f"{datetime.datetime.now().isoformat()} - {username},{client_ip},json data: {log_data}\n"
    with log_mutex:
        log_file.write(log_line)
        log_file.flush()

# Append a log line to the user_access.log file.
def log_user_result(username, client_ip, result_str):
    log_line = f"{datetime.datetime.now().isoformat()} - {username},{client_ip},result: {result_str}\n"
    with log_mutex:
        log_file.write(log_line)
        log_file.flush()



class ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    """Handle requests in a separate thread."""

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        client_ip = self.client_address[0]

        # Check rate limits before reading the request body
        if not rate_limit_checks(client_ip):
            send_back_response(self, username, 429, 'text/plain', b'Too many requests')
            # Returning before the self.rfile.read() below will lead to the client perceiving it as a connection reset
            # However this just saves the server from processing an unnecessary request that it knows it will reject
            return

        # Get the content length
        content_length = int(self.headers['Content-Length'])

        # Read the POST data
        post_raw_data = self.rfile.read(content_length)

        # Extract fields to determine whether this is a send of BTIDES data, or a query requesting BTIDES data
        post_json_data = json.loads(post_raw_data)

        # Initial sanity checks
        if 'token' not in post_json_data or 'refresh_token' not in post_json_data:
            send_back_response(self, username, 400, 'text/plain', b'Missing Google OAuth SSO token.')
            return
        if 'command' not in post_json_data:
            send_back_response(self, username, 400, 'text/plain', b'Missing command.')
            return

        # Validate OAuth token
        username = validate_oauth_token(post_json_data['token'], post_json_data['refresh_token'])
        if not username:
            send_back_response(self, username, 400, 'text/plain', b'Invalid OAuth token.')
            return

        # Log request
        log_user_access(username, client_ip, post_json_data)

        if post_json_data['command'] == "upload" and 'btides_content' in post_json_data and 'query' not in post_json_data:
            json_content = post_json_data.get('btides_content')
            handle_btides_data(self, username, json_content)
        elif post_json_data['command'] == "query" and 'query' in post_json_data and 'btides_content' not in post_json_data:
            query_object = post_json_data.get('query')
            handle_query(self, username, query_object)
        else:
            send_back_response(self, username, 400, 'text/plain', b'Invalid input. Either both or neither of json_content and query_object are present.')
            return

        # Decrement the connection count
        connection_data[client_ip]["count"] -= 1

# Initialize the unique files dictionary
initialize_unique_files('./pool_files')

# Load the schemas and create a registry
registry = load_schemas()

# Define the handler to use for the server
handler = CustomHandler

# Create the server
if(g_local_testing):
    hostname = 'localhost'
else:
    hostname = '0.0.0.0'
httpd = ThreadingHTTPServer((hostname, 3567), handler)

# Create an SSL context
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile="./btidalpool.ddns.net.crt", keyfile="./btidalpool.ddns.net.key")

# Wrap the server socket with SSL
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"Serving on https://{hostname}:3567")
httpd.serve_forever()