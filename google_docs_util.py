import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# from dotenv import load_dotenv # .envのロードを削除

# load_dotenv() # .envのロードを削除
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
# .envから直接設定
DOCUMENT_ID = '1IcPkgUA8irbYxuoi2efP47hLMmkrLuTsaGqS37MXpqU' # GOOGLE_DOC_IDを直接設定
SCOPES = ['https://www.googleapis.com/auth/documents']


def send_google_doc(text=None, image_uri=None):
    if not DOCUMENT_ID:
        # このチェックは不要になるが、念のため残しても良い
        # raise ValueError("GOOGLE_DOC_ID is not set.")
        pass # DOCUMENT_IDはハードコードされたため常に存在する
    if (text and image_uri) or (not text and not image_uri):
        raise ValueError("Specify exactly one of text or image_uri.")
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build('docs', 'v1', credentials=creds)
    requests = []
    loc = {'index': 1}
    if text:
        requests.append({
            'insertText': {'location': loc, 'text': text + '\n'}
        })
    else:
        requests.append({
            'insertInlineImage': {
                'location': loc,
                'uri': image_uri,
                'objectSize': {
                    'height': {'magnitude': 200, 'unit': 'PT'},
                    'width' : {'magnitude': 200, 'unit': 'PT'}
                }
            }
        })
    try:
        service.documents().batchUpdate(
            documentId=DOCUMENT_ID,
            body={'requests': requests}
        ).execute()
        return f"https://docs.google.com/document/d/{DOCUMENT_ID}/edit"
    except HttpError as e:
        print(f"Docs API Error: {e}", file=sys.stderr)
        raise