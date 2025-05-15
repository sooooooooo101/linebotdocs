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


# DOCUMENT_ID は呼び出し元から受け取るように変更
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
    # --- 末尾追記のための変更 ---
    # ドキュメントの末尾位置を取得
    try:
        # fields='body(content)' ではなく fields='body' に変更し、document['body']['endIndex'] を参照
        document = service.documents().get(documentId=document_id, fields='body').execute()

        # ドキュメントボディ全体の endIndex を取得
        # document['body'] が存在しない場合や endIndex がない場合はデフォルトで1（先頭）
        end_index = document.get('body', {}).get('endIndex', 1)

        # 安全のため、取得した endIndex が 1 より小さい場合は 1 とする
        end_index = max(1, end_index)

        print(f"DEBUG: Documentボディ全体の endIndex を取得しました: {end_index}", file=sys.stderr)

        loc = {'index': end_index} # 末尾のインデックスを挿入位置に設定

    except HttpError as e:
        print(f"Docs API Error while getting document end index: {e}", file=sys.stderr)
        # 末尾追記位置の取得に失敗した場合、エラーとして扱い、呼び出し元に伝える
        raise ValueError(f"Failed to get document end index: {e}")
    except Exception as e:
         print(f"An unexpected error occurred while getting document end index: {e}", file=sys.stderr)
         raise ValueError(f"Failed to get document end index: {e}")
    # --- 末尾追記のための変更 ここまで ---


    if text:
        # テキストの後に改行を自動的に追加（末尾追記なので新しい行として追記されるのが自然）
        text_to_insert = text + '\n'
        requests.append({
            'insertText': {'location': loc, 'text': text_to_insert}
        })
    else:
        # 画像埋め込みの場合も末尾に挿入されるようになる
        # 画像の後にも改行を追加したい場合は、別途 insertText リクエストを追加する必要がありますが、
        # ここでは画像単体を末尾に貼り付けます。
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
            documentId=document_id,
            body={'requests': requests}
        ).execute()
        return f"https://docs.google.com/document/d/{document_id}/edit"
    except HttpError as e:
        print(f"Docs API Error during batchUpdate: {e}", file=sys.stderr)
        raise # APIエラーは呼び出し元に伝える
