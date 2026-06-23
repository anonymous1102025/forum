"""
auth_setup.py
=============
One-time OAuth setup. Run this once to authenticate your Google account
and save a token that ga4_explorer.py and the pipeline can reuse.

Prerequisites:
  1. Create an OAuth 2.0 Client ID (Desktop app) in GCP Console
  2. Download the client secrets JSON → save as keys/oauth_client.json
  3. Run: python auth_setup.py

The token is saved to keys/user_token.json and refreshes automatically.
"""
import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
CLIENT_SECRET_FILE = "keys/oauth_client.json"
TOKEN_FILE = "keys/user_token.json"


def main():
    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"ERROR: {CLIENT_SECRET_FILE} not found.")
        print()
        print("Steps to create it:")
        print("  1. Go to https://console.cloud.google.com")
        print("  2. APIs & Services → Credentials")
        print("  3. Create Credentials → OAuth 2.0 Client ID → Desktop app")
        print(f"  4. Download JSON → save as {CLIENT_SECRET_FILE}")
        sys.exit(1)

    creds = None

    # Reuse saved token if valid
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token…")
            creds.refresh(Request())
        else:
            print("Opening browser for Google login…")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs("keys", exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    print()
    print(f"✓ Authenticated successfully!")
    print(f"✓ Token saved to {TOKEN_FILE}")
    print()
    print("Now run the explorer:")
    print(f"  python ga4_explorer.py --property 490276257 --days 30")


if __name__ == "__main__":
    main()
