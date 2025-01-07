import json
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class AuthClient:
    def __init__(self):
        self.credentials_path = './credentials.json'

        # Load client secrets
        secrets_path = './google_oauth_client_secret.json'
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

        # Create credentials
        self.credentials = Credentials(
            token=token_data['token'],
            refresh_token=token_data['refresh_token'],
            token_uri=token_data['token_uri'],
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=token_data['scopes']
        )
        return self.credentials


    # Sets self.user_info to the user's information if authentication is successful, and None if it fails
    def return_user_info(self, credentials):
        # Verify credentials by making a test API call
        service = build('oauth2', 'v2', credentials=credentials)
        try:
            self.user_info = service.userinfo().get().execute()
        except Exception as e:
            self.user_info = None


    # Checks if we can get the email address given the credentials. If so, the credentials are considered valid
    def validate_credentials(self, credentials):
        # Verify credentials by making a test API call
        try:
            self.return_user_info(credentials)
            if self.user_info and self.user_info.get('email'):
                print(f"Authentication successful for user {self.user_info.get('email')}!")
                return True
            else:
                print("Authentication failed. Unable to retrieve user information.")
                return False
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False

