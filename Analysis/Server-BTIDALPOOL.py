import http.server
import ssl
import os
import json
import datetime
import hashlib
import threading
import subprocess
from jsonschema import validate, ValidationError
from referencing import Registry, Resource
from jsonschema import Draft202012Validator
from socketserver import ThreadingMixIn
from collections import defaultdict, deque
import time

g_max_connections_per_day = 10
g_max_simultaneous_connections = 10

# Global dictionary to store unique file hashes
g_unique_files = {}

# Global dictionary to store connection data for rate limiting
connection_data = defaultdict(lambda: {"count": 0, "timestamps": deque()})

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

def run_btides_to_mysql(filename):
    # Run the BTIDES_to_MySQL.py script in a new thread.
    def target():
        subprocess.run(["python3", "BTIDES_to_MySQL.py", "--input", filename, "--use-test-db"])
    thread = threading.Thread(target=target)
    thread.start()

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

def handle_btides_data(self, username, json_content):
    # Parse the JSON data
    try:
        # Convert the data to a string to check the total data size
        json_content_str = json.dumps(json_content, sort_keys=True)

        # Check the size of the JSON content
        if len(json_content_str.encode('utf-8')) > 10 * 1024 * 1024:  # 10 megabytes
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'File size too big.')
            return

        # Validate the JSON content
        if not validate_json_content(json_content, registry):
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Invalid JSON data according to schema. Rejected.')
            return

        # Create the directory if it doesn't exist
        os.makedirs('./pool_files', exist_ok=True)

        # Generate the SHA1 hash of the json_content
        sha1_hash = hashlib.sha1(json_content_str.encode('utf-8')).hexdigest()

        # Check if the file already exists
        if sha1_hash in g_unique_files:
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'A file with this exact content already exists on the server.')
            return

        # Generate the filename
        current_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        filename = f'./pool_files/{sha1_hash}-{username}-{current_time}.json'

        # Save the JSON content to the file
        with open(filename, 'w') as f:
            json.dump(json_content, f)

        # Update the global dictionary
        g_unique_files[sha1_hash] = True

        # Spawn a new thread to run the BTIDES_to_MySQL.py script
        run_btides_to_mysql(filename)

        # Send a success response
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'File saved successfully.')

    except json.JSONDecodeError:
        self.send_response(400)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Invalid JSON data could not be decoded.')

g_sample_BTIDES = [
    {
        "bdaddr": "00:03:ea:0c:18:cd",
        "bdaddr_rand": 0,
        "LLArray": [
            {
                "direction": 1,
                "opcode": 12,
                "version": 8,
                "company_id": 96,
                "subversion": 782,
                "opcode_str": "LL_VERSION_IND"
            },
            {
                "direction": 1,
                "opcode": 9,
                "le_features_hex_str": "00000000000000ff",
                "opcode_str": "LL_FEATURE_RSP"
            },
            {
                "direction": 1,
                "opcode": 20,
                "max_rx_octets": 251,
                "max_rx_time": 2120,
                "max_tx_octets": 251,
                "max_tx_time": 2120,
                "opcode_str": "LL_LENGTH_REQ"
            },
            {
                "direction": 1,
                "opcode": 21,
                "max_rx_octets": 251,
                "max_rx_time": 2120,
                "max_tx_octets": 251,
                "max_tx_time": 2120,
                "opcode_str": "LL_LENGTH_RSP"
            },
            {
                "direction": 1,
                "opcode": 19,
                "opcode_str": "LL_PING_RSP"
            }
        ]
    }
]

def handle_query(self, username, query_object):
    print(query_object)

    # Send back the g_sample_BTIDES to the client
    self.send_response(200)
    self.send_header('Content-Type', 'application/json')
    self.end_headers()
    self.wfile.write(json.dumps(g_sample_BTIDES).encode('utf-8'))

class ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    """Handle requests in a separate thread."""

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        client_ip = self.client_address[0]

        # Check rate limits before reading the request body
        if not rate_limit_checks(client_ip):
            self.send_response(429)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Too many requests')
            self.wfile.flush()  # Ensure the response is sent
            # Returning before the self.rfile.read() below will lead to the client perceiving it as a connection reset
            # However this just saves the server from processing an unnecessary request that it knows it will reject
            return

        # Get the content length
        content_length = int(self.headers['Content-Length'])

        # Read the POST data
        post_data = self.rfile.read(content_length)

        # Extract fields to determine whether this is a send of BTIDES data, or a query requesting BTIDES data
        data = json.loads(post_data)

        if 'username' not in data:
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Missing username.')
            return
        username = data.get('username')

        if 'btides_content' in data and 'query' not in data:
            json_content = data.get('btides_content')
            handle_btides_data(self, username, json_content)
        elif 'query' in data and 'btides_content' not in data:
            query_object = data.get('query')
            handle_query(self, username, query_object)
        else:
            self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Invalid input. Either both or neither of json_content and query_object are present.')
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
hostname = 'localhost' # For local testing only
#hostname = '0.0.0.0'
httpd = ThreadingHTTPServer((hostname, 4443), handler)

# Create an SSL context
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile="BTIDALPOOL-local-cert.pem", keyfile="BTIDALPOOL-local-key.pem")

# Wrap the server socket with SSL
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"Serving on https://{hostname}:4443")
httpd.serve_forever()