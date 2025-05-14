import os
import io
import sys
import json  # jsonモジュールを追加
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
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
# GOOGLE_DRIVE_FOLDER_ID = None # GOOGLE_DRIVE_FOLDER_IDを直接設定 (元の.envにはなかったのでNoneのまま)
# Folder IDを環境変数から読み込む方が柔軟性が高いです
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID') # 環境変数から取得

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def get_drive_service():
    # ファイル存在チェックは不要になるため削除またはコメントアウト
    # if not os.path.exists(SERVICE_ACCOUNT_FILE):
    #     raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")

    # 環境変数からパースした情報を使って資格情報を作成
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

    # GOOGLE_DRIVE_FOLDER_IDが設定されていれば、そのフォルダにアップロード
    if GOOGLE_DRIVE_FOLDER_ID:
        # フォルダが存在するかどうかのチェックはここでは行っていません
        metadata['parents'] = [GOOGLE_DRIVE_FOLDER_ID]

    media = MediaIoBaseUpload(io.BytesIO(image_data), mimetype='image/jpeg', resumable=True)
    try:
        # Drive APIでファイルをアップロード
        file = service.files().create(
            body=metadata,
            media_body=media,
            fields='id,webContentLink' # アップロード後にIDとwebContentLinkを取得
        ).execute()

        file_id = file.get('id')
        # webContentLink はダイレクトアクセス用リンクであることが多い
        # webViewLink はGoogle Driveの画面で開くリンクです。Docsに埋め込むにはwebContentLinkが適しています。
        direct_link = file.get('webContentLink')

        # webContentLink が取得できない場合（Google側の仕様変更などで）の代替手段
        if not direct_link and file_id:
             # ファイルIDがあれば、uc?export=view 形式のリンクを生成
             direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"
             print(f"Warning: webContentLink not available, using fallback direct link: {direct_link}", file=sys.stderr)
        elif not direct_link and not file_id:
             # IDもリンクも取得できない場合はエラー
             raise Exception("File ID and webContentLink not returned after Drive upload.")


        # アップロードしたファイルを「リンクを知っている全員が閲覧可能」に設定
        if file_id:
            try:
                service.permissions().create(
                    fileId=file_id,
                    body={'type':'anyone','role':'reader'},
                    fields='id' # 作成されたpermissionのIDを取得（必須ではない）
                ).execute()
                print(f"Successfully set permissions for file ID: {file_id}", file=sys.stderr)
            except HttpError as perm_error:
                 print(f"Failed to set permissions for file ID {file_id}: {perm_error}", file=sys.stderr)
                 # 共有設定に失敗してもアップロード自体は成功しているので、処理は続行可能だがログを出す

        return file_id, direct_link

    except HttpError as e:
        print(f"Drive API Error during upload or permission setting: {e}", file=sys.stderr)
        raise # APIエラーが発生した場合は呼び出し元に伝える
    except Exception as e:
        print(f"An unexpected error occurred during Drive upload: {e}", file=sys.stderr)
        raise # その他の予期しないエラーも呼び出し元に伝える
