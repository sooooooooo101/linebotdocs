import os
import io
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
# from dotenv import load_dotenv # .envのロードを削除

# load_dotenv() # .envのロードを削除
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
# .envから直接設定
GOOGLE_DRIVE_FOLDER_ID = None # GOOGLE_DRIVE_FOLDER_IDを直接設定 (元の.envにはなかったのでNoneのまま)
SCOPES = ['https://www.googleapis.com/auth/drive.file']


def get_drive_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)


def upload_image_to_drive(image_data: bytes, file_name: str):
    if not image_data:
        return None, None
    service = get_drive_service()
    metadata = {'name': file_name, 'mimeType': 'image/jpeg'}
    # GOOGLE_DRIVE_FOLDER_IDがハードコードされた値を使う
    if GOOGLE_DRIVE_FOLDER_ID:
        metadata['parents'] = [GOOGLE_DRIVE_FOLDER_ID]
    media = MediaIoBaseUpload(io.BytesIO(image_data), mimetype='image/jpeg', resumable=True)
    try:
        file = service.files().create(
            body=metadata,
            media_body=media,
            fields='id,webContentLink'
        ).execute()
        file_id = file.get('id')
        # webContentLink はダイレクトアクセス用
        direct_link = file.get('webContentLink') or f"https://drive.google.com/uc?export=view&id={file_id}"
        # 共有設定
        if file_id:
            service.permissions().create(
                fileId=file_id,
                body={'type':'anyone','role':'reader'},
                fields='id'
            ).execute()
        return file_id, direct_link
    except HttpError as e:
        print(f"Drive API Error: {e}", file=sys.stderr)
        raise