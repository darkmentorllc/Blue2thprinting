import json
import requests
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class AuthClient:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile']
        self.auth_uri = "https://accounts.google.com/o/oauth2/auth"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.redirect_uri = 'https://btidalpool.ddns.net:7653/oauth2callback'
        self.token_file = None

        # BTIDALPOOL server's Google OAuth2 client ID
        self.client_id = '934838710114-hrn5hafisthr3eqh7gnr1jka5c5hmjli.apps.googleusercontent.com'

    # This is just a common flow that was seen repeatedly by the client users, where they had to
    # use an existing token, and possibly refresh it, or maybe just show the SSO login prompt.
    # So it was pulled into its own helper function.
    def token_helper(self, token_file=None):
        if token_file:
            with open(token_file, 'r') as f:
                token_data = json.load(f)
            token = token_data['token']
            refresh_token = token_data['refresh_token']
            self.set_credentials(token, refresh_token, token_file=token_file)
            if(not self.validate_credentials()):
                print("Authentication failed.")
                exit(1)
        else:
            try:
                if(not self.google_SSO_authenticate() or not self.validate_credentials()):
                    print("Authentication failed.")
                    exit(1)
            except ValueError as e:
                print(f"Error: {e}")
                exit(1)

    # Used by clients and server
    def set_credentials(self, token, refresh_token, token_file=None):
        # Store the token file name if it's given to us,
        # so we can save any refreshed tokens back to the same file
        self.token_file = token_file
        # Create credentials with all required fields for refresh
        self.credentials = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            scopes=self.scopes
        )
        return self.credentials

    def refresh_access_token(self):
        try:
            # Instead of refreshing locally, make a request to the token refresh endpoint
            session = requests.Session()
            response = session.post("https://btidalpool.ddns.net:7653/refresh",
                json={
                    "refresh_token": self.credentials.refresh_token,
                    "client_id": self.client_id
                },
                verify='./fullchain-with-root.pem' # LetsEncrypt fullchain.pem w/ root cert manually downloaded and catted on the end
            )
            if response.status_code == 200:
                token_data = response.json()
                return self.set_credentials(token_data['token'], token_data['refresh_token'], self.token_file)
            return None
        except Exception as e:
            print(f"Failed to refresh token: {e}")
            return None

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
            print(f"Failed to get user info (this is usually due to an expired token): {e}")
            print(f"Attempting token refresh...")
            self.user_info = None
            # Try refreshing the token
            try:
                credentials = self.refresh_access_token()
                # If we got here it succeeded! Retry the request with the new creds
                service = build('oauth2', 'v2', credentials=credentials)
                self.user_info = service.userinfo().get().execute()
                print("Successfully refreshed token!")
                # If the credentials came in through a token file, write the creds back out to the token file,
                # so that they don't need to go through this flow again next time
                if(self.token_file):
                    with open(self.token_file, 'w') as f:
                        f.write(json.dumps({
                            'token': credentials.token,
                            'refresh_token': credentials.refresh_token}))
            except Exception as e:
                print(f"Failed to refresh token: {e}")



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

