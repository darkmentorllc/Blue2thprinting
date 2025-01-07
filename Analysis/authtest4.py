from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import json
import os
from pathlib import Path
from googleapiclient.discovery import build

class AuthClient:
    def __init__(self):
        self.credentials_path = Path.home() / 'credentials.json'
        self.credentials_path.parent.mkdir(exist_ok=True)

        # Load client secrets
        secrets_path = Path(__file__).parent / 'google_oauth_client_secret.json'
        try:
            with open(secrets_path) as f:
                secrets = json.load(f)
            self.client_id = secrets['client_id']
            self.client_secret = secrets['client_secret']
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to load OAuth secrets: {e}")

    def authenticate(self):
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email'],
            redirect_uri='https://btidalpool.ddns.net/oauth2callback'
        )

        auth_url, _ = flow.authorization_url(prompt='consent')

        print("\nPlease visit this URL to authenticate:")
        print(auth_url)
        print("\nAfter authentication, copy the entire JSON token from the browser:")

        token_data = json.loads(input("Token: ").strip())

        # Create and save credentials
        credentials = Credentials(
            token=token_data['token'],
            refresh_token=token_data['refresh_token'],
            token_uri=token_data['token_uri'],
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=token_data['scopes']
        )

        # Save credentials securely
        self.credentials_path.write_text(
            json.dumps({
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': self.client_id,
                'scopes': credentials.scopes
            })
        )
        self.credentials_path.chmod(0o600)

        print("Credentials saved.")
        # Verify credentials by making a test API call
        try:
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()

            if user_info and user_info.get('email'):
                print(f"Authentication successful for user {user_info.get('email')}!")
            else:
                print("Authentication failed. Unable to retrieve user information.")
        except Exception as e:
            print(f"Authentication failed: {e}")

if __name__ == '__main__':
    try:
        client = AuthClient()
        client.authenticate()
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)
