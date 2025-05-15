import os
import sys
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# from dotenv import load_dotenv

# load_dotenv()
# サービスアカウントファイルパスは環境変数から読み込む方式に変更するため不要
# SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')

# 環境変数からJSON文字列として資格情報を取得
CREDENTIALS_JSON_STRING = os.environ.get('CREDENTIALS_JSON')

# 環境変数チェック
if not CREDENTIALS_JSON_STRING:
    raise ValueError("CREDENTIALS_JSON environment variable is not set. Please set it in Render.")

# JSON文字列をPython辞書にパースする
try:
    CREDENTIALS_INFO = json.loads(CREDENTIALS_JSON_STRING)
except json.JSONDecodeError:
    raise ValueError("Failed to decode CREDENTIALS_JSON. Ensure it is valid JSON.")


# DOCUMENT_ID は呼び出し元から受け取るように変更するため、ここではハードコードしない
# DOCUMENT_ID = '1IcPkgUA8irbYxuoi2efP47hLMmkrLuTsaGqS37MXpqU'

SCOPES = ['https://www.googleapis.com/auth/documents']


# document_id を引数として受け取るように変更
def send_google_doc(document_id: str, text=None, image_uri=None):
    if not document_id:
         raise ValueError("document_id must be provided.")

    if (text and image_uri) or (not text and not image_uri):
        raise ValueError("Specify exactly one of text or image_uri.")

    # 資格情報作成とサービスビルド
    try:
        creds = service_account.Credentials.from_service_account_info(
            CREDENTIALS_INFO, scopes=SCOPES
        )
        service = build('docs', 'v1', credentials=creds)
    except Exception as e:
        print(f"Failed to obtain Google Docs credentials or build service: {e}", file=sys.stderr)
        raise # 資格情報取得やサービスビルドに失敗した場合は処理を中断

    requests = []
    # NOTE: index=1 はドキュメントの先頭に挿入します。
    # 末尾に追記したい場合は、ドキュメントのコンテンツを取得し、その長さを取得して挿入位置とする必要があります。
    # 例: doc = service.documents().get(documentId=document_id).execute(); index = len(doc.get('body',{}).get('content',[]))
    # 簡単のために現状維持（先頭に挿入）します。
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
                    'height': {'magnitude': 200, 'unit': 'PT'}, # 適宜調整
                    'width' : {'magnitude': 200, 'unit': 'PT'}  # 適宜調整
                }
            }
        })

    try:
        # 引数で受け取った document_id を使用
        service.documents().batchUpdate(
            documentId=document_id,
            body={'requests': requests}
        ).execute()
        return f"https://docs.google.com/document/d/{document_id}/edit"
    except HttpError as e:
        print(f"Docs API Error: {e}", file=sys.stderr)
        raise # APIエラーは呼び出し元に伝える
