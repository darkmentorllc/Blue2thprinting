import json
import http.server
import ssl
import socketserver
import urllib.parse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pathlib import Path

def load_oauth_secrets():
    secrets_path = Path(__file__).parent / 'google_oauth_client_secret.json'
    try:
        with open(secrets_path) as f:
            secrets = json.load(f)
        return secrets['client_id'], secrets['client_secret']
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to load OAuth secrets: {e}")

try:
    CLIENT_ID, CLIENT_SECRET = load_oauth_secrets()
except RuntimeError as e:
    print(f"Error: {e}")
    exit(1)

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
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
                    scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email'],
                    redirect_uri='https://btidalpool.ddns.net/oauth2callback'
                )
                flow.fetch_token(code=query_components['code'][0])
                credentials = flow.credentials

                # token_data = {
                #     'token': credentials.token,
                #     'refresh_token': credentials.refresh_token,
                #     'token_uri': credentials.token_uri,
                #     'client_id': CLIENT_ID,
                #     'scopes': credentials.scopes
                # }
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
                    <p>Please copy the entire token including the curly brackets and paste it into the CLI application.</p>
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

def run_server():
    PORT = 443
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
