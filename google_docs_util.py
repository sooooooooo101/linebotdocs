import os
import sys
import json  # jsonモジュールを追加
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# from dotenv import load_dotenv # .envのロードは引き続き削除

# load_dotenv() # .envのロードは引き続き削除
# SERVICE_ACCOUNT_FILE は環境変数から読み込むため削除またはコメントアウト
# SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')

# 環境変数からJSON文字列として資格情報を取得
CREDENTIALS_JSON_STRING = os.environ.get('CREDENTIALS_JSON')

if not CREDENTIALS_JSON_STRING:
    # 環境変数が設定されていない場合はエラーを発生させる
    # 開発環境などでファイルを使う場合はこのチェックを調整してください
    raise ValueError("CREDENTIALS_JSON environment variable is not set.")

# JSON文字列をPython辞書にパースする
try:
    CREDENTIALS_INFO = json.loads(CREDENTIALS_JSON_STRING)
except json.JSONDecodeError:
    raise ValueError("Failed to decode CREDENTIALS_JSON. Ensure it is valid JSON.")


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

    # ファイル存在チェックは不要になるため削除またはコメントアウト
    # if not os.path.exists(SERVICE_ACCOUNT_FILE):
    #     raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")

    # 環境変数からパースした情報を使って資格情報を作成
    try:
        creds = service_account.Credentials.from_service_account_info(
            CREDENTIALS_INFO, scopes=SCOPES
        )
        service = build('docs', 'v1', credentials=creds)
    except Exception as e:
        print(f"Failed to obtain Google Docs credentials or build service: {e}", file=sys.stderr)
        raise # 資格情報取得やサービスビルドに失敗した場合は処理を中断

    requests = []
    # NOTE: index=1 はドキュメントの先頭に挿入します。末尾に追記したい場合は別の方法が必要です。
    # 例えば、まずドキュメントのコンテンツを取得して最後に挿入位置を計算するなど。
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
                    'height': {'magnitude': 200, 'unit': 'PT'}, # 適宜調整してください
                    'width' : {'magnitude': 200, 'unit': 'PT'}  # 適宜調整してください
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
