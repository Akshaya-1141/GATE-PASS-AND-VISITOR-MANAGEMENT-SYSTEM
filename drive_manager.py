# drive_manager.py
import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

def upload_photo_to_drive(image_bytes, filename, folder_id):
    """
    Uploads a photo byte stream to a specified Google Drive folder
    and returns a viewable webViewLink.
    """
    creds = None
    if os.getenv('GOOGLE_TOKEN'):
        token_info = json.loads(os.getenv('GOOGLE_TOKEN'))
        creds = Credentials.from_authorized_user_info(
            token_info, 
            ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        )
    elif os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file(
            'token.json', 
            ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        )
    
    if not creds:
        raise Exception("No valid credentials or token.json found. Please run setup_drive.py first.")
    
    service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaInMemoryUpload(image_bytes, mimetype='image/jpeg', resumable=True)
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    file_id = file.get('id')
    
    # Make file viewable by anyone with link
    try:
        permission = {'type': 'anyone', 'role': 'reader'}
        service.permissions().create(fileId=file_id, body=permission).execute()
    except Exception as perm_err:
        print(f"⚠️ Warning setting photo permission: {perm_err}")

    return file.get('webViewLink', f"https://drive.google.com/file/d/{file_id}/view")
