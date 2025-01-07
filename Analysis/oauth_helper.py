import json
import os
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class AuthClient:
    def __init__(self):
        self.credentials_path = './credentials.json'
        self.scopes = ['openid', 'https://www.googleapis.com/auth/userinfo.email']
        self.auth_uri = "https://accounts.google.com/o/oauth2/auth"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.redirect_uri = 'https://btidalpool.ddns.net/oauth2callback'

        # Load client secrets
        secrets_path = './google_oauth_client_secret.json'
        try:
            with open(secrets_path) as f:
                secrets = json.load(f)
            self.client_id = secrets['client_id'] # FIXME: Not sure this is secret anymore. Can probably hardcode it in?
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to load OAuth secrets: {e}")


    # Used by clients and server
    def set_credentials(self, token, refresh_token):
        # Create credentials
        self.credentials = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            scopes=self.scopes
        )
        return self.credentials


    # Returns credentials if authentication is successful, and None if it fails
    # Only used by clients
    def google_SSO_authenticate(self):
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "auth_uri": self.auth_uri,
                    "token_uri": self.token_uri,
                }
            },
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )

        auth_url, _ = flow.authorization_url(prompt='consent')

        print("\nPlease visit this URL to authenticate:")
        print(auth_url)
        print("\nAfter authentication, copy the entire JSON token from the browser:")

        token_data = json.loads(input("Token: ").strip())

        if 'token' not in token_data or 'refresh_token' not in token_data:
            print("Invalid token data. Missing 'token' or 'refresh_token'.")
            return None

        return self.set_credentials(token_data['token'], token_data['refresh_token'])


    # Sets self.user_info to the user's information if authentication is successful, and None if it fails
    # Used by clients and server
    def return_user_info(self):
        # Verify credentials by making a test API call
        service = build('oauth2', 'v2', credentials=self.credentials)
        try:
            self.user_info = service.userinfo().get().execute()
        except Exception as e:
            print(f"Failed to get user info: {e}")
            self.user_info = None


    # Checks if we can get the email address given the credentials. If so, the credentials are considered valid
    # Used by clients and server
    def validate_credentials(self):
        # Verify credentials by making a test API call
        try:
            self.return_user_info()
            if self.user_info and self.user_info.get('email'):
                print(f"Authentication successful for user {self.user_info.get('email')}!")
                return True
            else:
                print("Authentication failed. Unable to retrieve user information.")
                return False
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False

