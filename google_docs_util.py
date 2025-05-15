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
    # --- ここから末尾追記のための変更 ---
    # ドキュメントの末尾位置を取得
    try:
        # fields='body(endIndex)' がエラーの原因なので fields='body(content)' に変更
        document = service.documents().get(documentId=document_id, fields='body(content)').execute()
        # コンテンツが空でない場合、最後の要素の endIndex を取得
        # ドキュメントが空の場合は content が存在しないか空のリストになる
        if document.get('body', {}).get('content'):
             # 最後の SectionBreak または Paragraph などの要素を取得
             # Docs API v1 の構造では、body.content の最後の要素が全体を締めくくる要素です。
             # ただし、末尾が改行で終わるかなどで endIndex の解釈に注意が必要な場合があります。
             # 簡単には、最後の要素の endIndex を使います。
             last_structural_element = document['body']['content'][-1]
             end_index = last_structural_element.get('endIndex', 1) # endIndexがない場合やドキュメントが空の場合は1（先頭）をデフォルトに
             # ただし、もしドキュメントが空で content がない場合は endIndex = 1 としたい
             # 空のドキュメントの body.content は [<paragraph>, <sectionBreak>] のようになっていることが多い
             # 最後の structural element が SectionBreak の場合、endIndex はその SectionBreak の後の位置になる傾向
             # より確実に末尾に追記するには、body.content の長さ（文字数+α）を使う方法もあるが、複雑。
             # ここではシンプルに、最後の要素の endIndex を使用します。
             # ドキュメント全体がテキストのみの場合、endIndex はテキストの長さ+1 になることが多い。
             # 安全のため、取得した endIndex が 1 より小さい場合は 1 とする
             end_index = max(1, end_index)

             print(f"DEBUG: Document末尾 endIndex を取得しました: {end_index}", file=sys.stderr)

        else:
             # ドキュメントが完全に空の場合（初期状態など）
             end_index = 1 # 先頭に挿入

        loc = {'index': end_index} # 末尾のインデックスを挿入位置に設定

    except HttpError as e:
        print(f"Docs API Error while getting document end index: {e}", file=sys.stderr)
        # 末尾追記位置の取得に失敗した場合、先頭に挿入するなどの代替処理も可能だが、
        # ここではエラーとして扱い、呼び出し元に伝える
        raise ValueError(f"Failed to get document end index: {e}")
    except Exception as e:
         print(f"An unexpected error occurred while getting document end index: {e}", file=sys.stderr)
         raise ValueError(f"Failed to get document end index: {e}")
    # --- 末尾追記のための変更 ここまで ---


    if text:
        requests.append({
            'insertText': {'location': loc, 'text': text + '\n'} # 改行はそのまま付ける
        })
    else:
        # 画像埋め込みの場合も末尾に挿入されるようになる
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
