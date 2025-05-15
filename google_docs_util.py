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
    CREDENTIALS_INFO = json.loads(CREDENTIALS_érés_JSON_STRING)
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
        if content and content[-1] and content[-1].get('endIndex') is not None:
             end_index = content[-1]['endIndex']
             end_index = max(1, end_index) # 念のため最小値を 1 に


        print(f"DEBUG: ドキュメント末尾位置 (body.content[-1].endIndex) を取得しました: {end_index}", file=sys.stderr)

    except HttpError as e:
        # ドキュメント取得時の API エラー (404 Not Found や 403 Permission Denied など)
        print(f"Docs API Error while getting document for end index: {e}", file=sys.stderr)
        raise ValueError(f"Failed to get document body content for end index: {e}")
    except Exception as e:
         print(f"An unexpected error occurred while getting document end index: {e}", file=sys.stderr)
         raise ValueError(f"Failed to get document end index: {e}")

    # --- 末尾追記のための改行挿入とコンテンツ挿入 ---
    # BatchUpdate リクエストリストを構築

    # 1. 現在の末尾位置に改行を挿入するリクエスト
    requests.append({
        'insertText': {
            'location': {'index': end_index},
            'text': '\n' # 改行文字を挿入
        }
    })
    print(f"DEBUG: リクエスト1: 末尾位置 {end_index} に改行を挿入", file=sys.stderr)


    # 2. 改行が挿入された「次の位置」に、目的のコンテンツを挿入するリクエスト
    # 改行を挿入すると、元の end_index の位置に改行が入り、新しい末尾位置は end_index + 1 になります。
    content_insert_index = end_index + 1
    print(f"DEBUG: リクエスト2: 次の位置 {content_insert_index} にコンテンツを挿入", file=sys.stderr)

    loc = {'index': content_insert_index} # 新しい挿入位置は改行の次

    if text:
        # テキストの後に改行を自動的に追加（末尾追記なので新しい行として追記されるのが自然）
        # ただし、直前に改行を挿入したので、ここでさらに改行を付けるかどうかは好みに応じる
        # ここではテキスト自体の末尾には改行を付けず、独立した行として追記されるようにする
        text_to_insert = text # + '\n' # 直前に改行を挿入したのでここでは不要な場合が多い
        requests.append({
            'insertText': {'location': loc, 'text': text_to_insert}
        })
    else:
        # 画像埋め込みの場合も同じく新しい位置に挿入
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
    # --- 末尾追記のための変更 ここまで ---


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
