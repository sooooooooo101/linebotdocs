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

SCOPES = ['https://www.googleapis.com/auth/drive.file']


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


def upload_image_to_drive(image_data: bytes, file_name: str):
    if not image_data:
        # image_dataがNoneまたは空の場合はアップロードしない
        return None, None

    service = get_drive_service()
    metadata = {'name': file_name, 'mimeType': 'image/jpeg'}

    # GOOGLE_DRIVE_FOLDER_ID が設定されていれば、そのフォルダにアップロード
    if GOOGLE_DRIVE_FOLDER_ID:
        # フォルダが存在するかどうかのチェックはここでは行っていません
        metadata['parents'] = [GOOGLE_DRIVE_FOLDER_ID]
        print(f"Uploading to Drive folder: {GOOGLE_DRIVE_FOLDER_ID}", file=sys.stderr) # デバッグログ

    media = MediaIoBaseUpload(io.BytesIO(image_data), mimetype='image/jpeg', resumable=True)
    try:
        # Drive APIでファイルをアップロード
        print(f"Attempting to upload file: {file_name}", file=sys.stderr) # デバッグログ
        file = service.files().create(
            body=metadata,
            media_body=media,
            fields='id,webContentLink' # アップロード後にIDとwebContentLinkを取得
        ).execute()

        file_id = file.get('id')
        direct_link = file.get('webContentLink')

        print(f"Upload successful. Raw file_id: {file_id}, webContentLink: {direct_link}", file=sys.stderr) # デバッグログ


        # --- ここから修正 ---
        # permissions().create に渡す前に、file_idが文字列であり、余計なパラメータが付いていないか確認・修正
        cleaned_file_id = file_id
        if isinstance(file_id, str):
             # ファイルID文字列に'?'が含まれている場合、それ以降を切り捨てる
             cleaned_file_id = file_id.split('?')[0]

        # 念のため、 cleaned_file_id が空になっていないか、Noneでないかを確認
        if not cleaned_file_id:
            raise Exception(f"Cleaned file ID is invalid or empty: {cleaned_file_id}")

        print(f"DEBUG: Cleaned file_id before permissions call: {cleaned_file_id}", file=sys.stderr) # デバッグログ
        # --- ここまで修正 ---


        # webContentLink が取得できない場合（Google側の仕様変更などで）の代替手段
        if not direct_link and cleaned_file_id: # 代替リンク生成にも cleaned_file_id を使用
             direct_link = f"https://drive.google.com/uc?export=view&id={cleaned_file_id}"
             print(f"Warning: webContentLink not available, using fallback direct link: {direct_link}", file=sys.stderr)
        elif not direct_link and not cleaned_file_id:
             # IDもリンクも取得できない場合はエラー
             raise Exception("File ID and webContentLink not returned after Drive upload.")

        # アップロードしたファイルを「リンクを知っている全員が閲覧可能」に設定
        # 修正した cleaned_file_id を使用
        if cleaned_file_id:
            try:
                print(f"Attempting to set permissions for file ID: {cleaned_file_id}", file=sys.stderr) # デバッグログ
                service.permissions().create(
                    fileId=cleaned_file_id, # **修正箇所: cleaned_file_id を渡す**
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


        return cleaned_file_id, direct_link # 戻り値のファイルIDも cleaned なものにする

    except HttpError as e:
        print(f"Drive API Error during upload or permission setting: {e}", file=sys.stderr)
        raise # APIエラーが発生した場合は呼び出し元に伝える
    except Exception as e:
        print(f"An unexpected error occurred during Drive upload: {e}", file=sys.stderr)
        raise # その他の予期しないエラーも呼び出し元に伝える
