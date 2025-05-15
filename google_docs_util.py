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
    # --- 末尾追記のためのロジック ---
    # ドキュメントの末尾位置を取得
    end_index = 1 # ドキュメントが完全に空の場合のデフォルト位置

    try:
        # ドキュメントのコンテンツボディのみを取得
        document = service.documents().get(documentId=document_id, fields='body(content)').execute()

        # コンテンツリストを取得
        content = document.get('body', {}).get('content')

        # コンテンツが空でなく、最後の要素に endIndex が存在する場合
        # body.content の最後の StructuralElement の endIndex が、ドキュメント全体の末尾のインデックスとなります。
        if content and content[-1] and content[-1].get('endIndex') is not None:
             end_index = content[-1]['endIndex']
             # Docs API のインデックスは 1 から始まるため、endIndex は常に 1 以上です。
             # 念のため最小値を 1 としますが、通常不要です。
             end_index = max(1, end_index)
             print(f"DEBUG: ドキュメント末尾位置 (body.content[-1].endIndex) を取得しました: {end_index}", file=sys.stderr)
        else:
             # ドキュメントが完全に空の場合や、content 構造が想定外の場合
             # この場合、end_index は初期値の 1 のままとなります。
             print("DEBUG: ドキュメントコンテンツが空または構造が想定外のため、末尾位置を 1 に設定しました。", file=sys.stderr)


    except HttpError as e:
        # ドキュメント取得時の API エラー (404 Not Found や 403 Permission Denied など)
        # このエラーが発生した場合、末尾追記はできません。
        print(f"Docs API Error while getting document for end index: {e}", file=sys.stderr)
        # エラーを再度発生させ、呼び出し元に伝える
        raise ValueError(f"Failed to get document body content for end index: {e}")
    except Exception as e:
         # その他の予期しないエラー
         print(f"An unexpected error occurred while getting document end index: {e}", file=sys.stderr)
         raise ValueError(f"Failed to get document end index: {e}")

    # 挿入位置を設定
    loc = {'index': end_index}
    # --- 末尾追記のためのロジック ここまで ---


    # BatchUpdate のリクエストボディを作成
    if text:
        # テキストの後に改行を自動的に追加（末尾追記なので新しい行として追記されるのが自然）
        text_to_insert = text + '\n'
        requests.append({
            'insertText': {'location': loc, 'text': text_to_insert}
        })
    else:
        # 画像埋め込みの場合も末尾に挿入される
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

    # BatchUpdate リクエストを実行
    try:
        service.documents().batchUpdate(
            documentId=document_id,
            body={'requests': requests}
        ).execute()
        # 成功したら編集リンクを返す
        return f"https://docs.google.com/document/d/{document_id}/edit"
    except HttpError as e:
        # batchUpdate 実行時の API エラー
        print(f"Docs API Error during batchUpdate: {e}", file=sys.stderr)
        raise # APIエラーは呼び出し元に伝える
    except Exception as e:
         # その他の予期しないエラー
         print(f"An unexpected error occurred during Docs batchUpdate: {e}", file=sys.stderr)
         raise # その他の予期しないエラーも呼び出し元に伝える
