import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Scopes for both Sheets and Drive
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

def main():
    creds = None
    
    # 1. DELETE OLD TOKEN IF IT EXISTS TO FORCE NEW LOGIN
    if os.path.exists('token.json'):
        os.remove('token.json')
        print("🗑️ Old token removed to ensure fresh login.")

    # 2. Start Login Flow
    print("🌐 Opening browser for login...")
    if not os.path.exists('credentials.json'):
        print("❌ Error: 'credentials.json' is missing! Please put it in this folder.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES)
    
    # ⚠️ CHANGE: port=0 allows the OS to pick ANY free port (Fixes WinError 10013)
    creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    
    # 3. Save the PERMANENT token
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
        print("✅ Success! 'token.json' saved. This token is valid 24/7.")

if __name__ == '__main__':
    main()