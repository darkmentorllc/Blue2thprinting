from oauth_helper import AuthClient

if __name__ == '__main__':
    try:
        client = AuthClient()
        credentials = client.authenticate()
        if(not credentials):
            print("Authentication failed.")
            exit(1)
        if(client.validate_credentials(credentials)):
            token = credentials.token
            refresh_token = credentials.refresh_token
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)
