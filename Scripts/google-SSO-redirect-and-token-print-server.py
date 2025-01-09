import json
import http.server
import ssl
import socketserver
import urllib.parse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pathlib import Path
from google.auth.transport.requests import Request

def load_oauth_secrets():
    secrets_path = Path(__file__).parent / 'google_oauth_client_secret.json'
    try:
        with open(secrets_path) as f:
            secrets = json.load(f)
        return secrets['client_secret'], '6849068466-3rhiutmh069m2tpg9a2o4m26qnomaqse.apps.googleusercontent.com'
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to load OAuth secrets: {e}")

try:
    CLIENT_SECRET, CLIENT_ID = load_oauth_secrets()
except RuntimeError as e:
    print(f"Error: {e}")
    exit(1)

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/tos'):
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

        if self.path.startswith('/privacy'):
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

        if not self.path.startswith('/oauth2callback'):
            self.send_response(404)
            self.end_headers()
            return

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

def run_server():
    PORT = 7653 # = 0x1de5 - Beware the Ides of BTIDES ;)
    certfile = "/etc/letsencrypt/live/btidalpool.ddns.net/fullchain.pem"
    keyfile = "/etc/letsencrypt/live/btidalpool.ddns.net/privkey.pem"

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    handler = OAuthHandler
    httpd = socketserver.TCPServer(("", PORT), handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    print(f"Server running on port {PORT}")
    httpd.serve_forever()

if __name__ == '__main__':
    try:
        run_server()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
