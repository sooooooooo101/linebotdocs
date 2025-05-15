import os
import io
import sys
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
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

# GOOGLE_DRIVE_FOLDER_ID も環境変数から取得
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')

SCOPES = ['https://www.googleapis.com/auth/drive.file'] # drive.file スコープはアップロードと共有設定に必要


def get_drive_service():
    # 資格情報作成とサービスビルド
    try:
        creds = service_account.Credentials.from_service_account_info(
            CREDENTIALS_INFO, scopes=SCOPES
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"Failed to obtain Google Drive credentials or build service: {e}", file=sys.stderr)
        raise # 資格情報取得やサービスビルドに失敗した場合は処理を中断


# 関数名を upload_file_to_drive に変更し、mime_type 引数を追加
def upload_file_to_drive(file_data: bytes, file_name: str, mime_type: str):
    if not file_data:
        # file_data がNoneまたは空の場合はアップロードしない
        return None, None, None # file_id, direct_link, webview_link を返すようにする

    service = get_drive_service()
    metadata = {'name': file_name, 'mimeType': mime_type} # MIME タイプを引数から取得

    # GOOGLE_DRIVE_FOLDER_ID が設定されていれば、そのフォルダにアップロード
    if GOOGLE_DRIVE_FOLDER_ID:
        # フォルダが存在するかどうかのチェックはここでは行っていません
        metadata['parents'] = [GOOGLE_DRIVE_FOLDER_ID]
        print(f"Uploading to Drive folder: {GOOGLE_DRIVE_FOLDER_ID}", file=sys.stderr) # デバッグログ

    media = MediaIoBaseUpload(io.BytesIO(file_data), mimetype=mime_type, resumable=True) # MIME タイプを引数から取得
    try:
        # Drive APIでファイルをアップロード
        print(f"Attempting to upload file: {file_name} with MIME type {mime_type}", file=sys.stderr) # デバッグログ
        # webViewLink も取得する fields='id,webContentLink,webViewLink'
        file = service.files().create(
            body=metadata,
            media_body=media,
            fields='id,webContentLink,webViewLink'
        ).execute()

        file_id = file.get('id')
        direct_link = file.get('webContentLink') # ダイレクトダウンロードリンク (画像などに多い)
        webview_link = file.get('webViewLink') # Google Drive 上でファイルを開くリンク

        print(f"Upload successful. Raw file_id: {file_id}, webContentLink: {direct_link}, webViewLink: {webview_link}", file=sys.stderr) # デバッグログ


        # --- file_id のクリーンアップ処理 (念のため残す) ---
        cleaned_file_id = file_id
        if isinstance(file_id, str):
             # ファイルID文字列に'?'が含まれている場合、それ以降を切り捨てる
             cleaned_file_id = file_id.split('?')[0]

        # 念のため、 cleaned_file_id が空になっていないか、Noneでないかを確認
        if not cleaned_file_id:
            # file_idが取得できない場合は、その後の共有設定もリンク生成もできない
             raise Exception(f"File ID is invalid or empty after upload: {file_id}")

        print(f"DEBUG: Cleaned file_id before permissions call: {cleaned_file_id}", file=sys.stderr) # デバッグログ
        # --- クリーンアップ処理 ここまで ---


        # webContentLink が取得できない場合（動画など）の代替手段
        # 動画の場合は webContentLink がないことが多いので、webViewLink を主に使う
        if not direct_link and cleaned_file_id:
             # ファイルIDがあれば、uc?export=view 形式のリンクを生成 (画像向きだが動画でも試せる)
             direct_link = f"https://drive.google.com/uc?export=view&id={cleaned_file_id}"
             print(f"Warning: webContentLink not available, using fallback direct link: {direct_link}", file=sys.stderr)
        # webViewLink も重要なリンクとして返す
        if not webview_link and cleaned_file_id:
             # webViewLink がない場合の代替
             webview_link = f"https://drive.google.com/open?id={cleaned_file_id}"
             print(f"Warning: webViewLink not available, using fallback webViewLink: {webview_link}", file=sys.stderr)


        # アップロードしたファイルを「リンクを知っている全員が閲覧可能」に設定
        # 修正した cleaned_file_id を使用
        if cleaned_file_id:
            try:
                print(f"Attempting to set permissions for file ID: {cleaned_file_id}", file=sys.stderr) # デバッグログ
                service.permissions().create(
                    fileId=cleaned_file_id, # cleaned_file_id を渡す
                    body={'type':'anyone','role':'reader'},
                    fields='id' # 作成されたpermissionのIDを取得（必須ではない）
                ).execute()
                print(f"Successfully set permissions for file ID: {cleaned_file_id}", file=sys.stderr)
            except HttpError as perm_error:
                 # 共有設定に失敗してもアップロード自体は成功しているので、処理は続行可能だがログを出す
                 print(f"Failed to set permissions for file ID {cleaned_file_id}: {perm_error}", file=sys.stderr)
            except Exception as perm_exception:
                 # 想定外の例外もログに出力
                 print(f"Unexpected error during permission setting for file ID {cleaned_file_id}: {perm_exception}", file=sys.stderr)


        return cleaned_file_id, direct_link, webview_link # file_id, direct_link, webview_link を返す

    except HttpError as e:
        print(f"Drive API Error during upload or permission setting: {e}", file=sys.stderr)
        raise # APIエラーが発生した場合は呼び出し元に伝える
    except Exception as e:
        print(f"An unexpected error occurred during Drive upload: {e}", file=sys.stderr)
        raise # その他の予期しないエラーも呼び出し元に伝える
