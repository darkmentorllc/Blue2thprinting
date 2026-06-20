import json
import http.server
import socket
import ssl
import socketserver
import urllib.parse
import urllib.request
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import os
import pwd
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler

def load_oauth_secrets():
#    secrets_path = Path(__file__).parent / 'google_oauth_client_secret.json'
    # We can access this path before we drop privileges
    secrets_path = '/etc/SSO/google_oauth_client_secret.json'
    try:
        with open(secrets_path) as f:
            secrets = json.load(f)
        return secrets['client_secret'], '6849068466-1sone95u0ihio99646tn60s234d88hge.apps.googleusercontent.com'
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to load OAuth secrets: {e}")

try:
    CLIENT_SECRET, CLIENT_ID = load_oauth_secrets()
except RuntimeError as e:
    print(f"Error: {e}")
    exit(1)

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/tos':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f"""
                <html><body>
                <h1>BTIDALPOOL Terms of Service</h1>
                <p>This is the BTIDALPOOL server. It is <b><i>researchware</i></b>. Therefore there are no guarantees about uptime, performance, etc.</p>
                <p>The following limitations currently apply to uploads/downloads:
                    <ul>
                        <li>Maximum connections per user per day: 100</li>
                        <li>Maximum BTIDES objects per download: 100</li>
                        <li>Maximum BTIDES file upload size: 20MB</li>
                    </ul>
                </p>
                <p>Researchers and top contributors can request Trusted Contributor status, which will not be subject to these limitations.</p>
                <p>Users who routinely exceed the limits will have their access revoked.</p>
                </body></html>
            """.encode())
            return

        elif self.path == '/privacy':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f"""
                <html><body>
                <h1>BTIDALPOOL Privacy Policy</h1>
                <p>You agree that all data you upload shall be considered in the public domain thereafter.</p>
                <p>You agree to the use of Google Single-Sign-On for purposes of user account access control. This will grant access to the account's email and public profile information (if any. i.e. name for account). The email will be used as the primary user ID.</p>
                </body></html>
            """.encode())
            return

        elif self.path == '/oauth2callback':
            query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

            if 'code' in query_components:
                try:
                    flow = Flow.from_client_config(
                        {
                            "web": {
                                "client_id": CLIENT_ID,
                                "client_secret": CLIENT_SECRET,
                                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                                "token_uri": "https://oauth2.googleapis.com/token",
                            }
                        },
                        scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile'],
                        redirect_uri='https://btidalpool.ddns.net:7653/oauth2callback'
                    )
                    flow.fetch_token(code=query_components['code'][0])
                    credentials = flow.credentials

                    token_data = {
                        'token': credentials.token,
                        'refresh_token': credentials.refresh_token,
                    }

                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(f"""
                        <html><body>
                        <h1>Authentication Successful!</h1>
                        <p>Your token:</p>
                        <p>{json.dumps(token_data)}</p>
                        <p>Please copy the entire token including the curly brackets and paste it into the CLI application and/or store it into a file and pass it with --token-file.</p>
                        </body></html>
                    """.encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(str(e).encode())
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
            return


    def do_POST(self):
        if self.path == '/refresh':
            content_length = int(self.headers['Content-Length'])
            post_data = json.loads(self.rfile.read(content_length))

            try:
                credentials = Credentials(
                    token=None,
                    refresh_token=post_data['refresh_token'],
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email',
                           'https://www.googleapis.com/auth/userinfo.profile']
                )

                # Refresh the credentials
                credentials.refresh(Request())

                token_data = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token
                }

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(token_data).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(str(e).encode())

        # PHONE-APP INTERFACE (distinct from the CLI copy-paste GET /oauth2callback above).
        # The DM BT Android app does a fully-native Google sign-in (Google Identity Services
        # AuthorizationClient.requestOfflineAccess) and obtains a one-time *serverAuthCode* for
        # this web client. It POSTs {"auth_code": "..."} here; we exchange that code for the
        # access + refresh tokens (we hold the client secret) and hand them straight back over
        # TLS — no token ever transits a browser URL or a copy-paste step.
        elif self.path == '/exchange_app':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = json.loads(self.rfile.read(content_length))
                auth_code = post_data.get('auth_code')
                if not auth_code:
                    self.send_response(400)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Missing auth_code')
                    return

                # Exchange the Android serverAuthCode. Per Google's "Enabling Server-Side Access"
                # guidance the redirect_uri for a native serverAuthCode exchange is the empty
                # string. (If Google ever returns redirect_uri_mismatch here, drop the field.)
                exchange_body = urllib.parse.urlencode({
                    'code': auth_code,
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'redirect_uri': '',
                    'grant_type': 'authorization_code',
                }).encode('utf-8')
                req = urllib.request.Request(
                    'https://oauth2.googleapis.com/token',
                    data=exchange_body,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    method='POST',
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    google_tokens = json.loads(resp.read().decode('utf-8'))

                token_data = {
                    'token': google_tokens.get('access_token'),
                    'refresh_token': google_tokens.get('refresh_token'),
                }
                # A missing refresh_token usually means consent wasn't forced — the app must
                # request offline access with forceCodeForRefreshToken=true.
                if not token_data['token'] or not token_data['refresh_token']:
                    self.send_response(502)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Token endpoint did not return both token and refresh_token')
                    return

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(token_data).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(str(e).encode())

# Drop root privileges after reading the privileged files
def drop_privileges(uid_name='ubuntu'):
    if os.getuid() != 0:
        return

    # Get the uid/gid from the name
    pw_record = pwd.getpwnam(uid_name)
    uid = pw_record.pw_uid
    gid = pw_record.pw_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(gid)
    os.setuid(uid)

    # Ensure a very conservative umask
    os.umask(0o077)

def run_server():
    PORT = 7653 # = 0x1de5 - Beware the Ides of BTIDES ;)
    certfile = "/etc/letsencrypt/live/btidalpool.ddns.net/fullchain.pem"
    keyfile = "/etc/letsencrypt/live/btidalpool.ddns.net/privkey.pem"

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    drop_privileges()

    class RateLimitingHandler(OAuthHandler):
        connections = defaultdict(list)
        RATE_LIMIT = 10  # Max 10 connections per minute per IP
        TIME_WINDOW = 60  # Time window in seconds

        def handle_one_request(self):
            client_ip = self.client_address[0]
            current_time = time.time()

            # Clean up old connections
            self.connections[client_ip] = [t for t in self.connections[client_ip] if current_time - t < self.TIME_WINDOW]

            if len(self.connections[client_ip]) >= self.RATE_LIMIT:
                self.send_error(429, "Too Many Requests")
                self.close_connection = True
                return

            self.connections[client_ip].append(current_time)
            super().handle_one_request()

    class TimeoutHandler(RateLimitingHandler):
        def handle_one_request(self):
            self.timeout = 5  # Set a timeout for receiving the request
            self.connection.settimeout(self.timeout)
            try:
                super().handle_one_request()
            except socket.timeout:
                self.send_error(408, "Request Timeout")
                self.close_connection = True

    handler = TimeoutHandler
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("", PORT), handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    httpd.socket.settimeout(10)  # 10 second timeout
    httpd.request_queue_size = 10  # Limit concurrent connections

    print(f"Server running on port {PORT}")
    httpd.serve_forever()

if __name__ == '__main__':
    try:
        run_server()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
