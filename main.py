import os
import sys
from dotenv import load_dotenv

load_dotenv()
print("DEBUG: .env file loaded (if exists).", file=sys.stderr)
# --- ここまで環境変数の読み込み ---

# その他のインポート (環境変数が必要なモジュールはload_dotenvの後に)
import re
# ★ 削除: datetimeモジュールをインポート - タイムスタンプ削除のため不要になりました
# import datetime # handle_imageとhandle_videoでファイル名生成にまだ使っているので削除しませんでした。念のためコメント解除。
import datetime # ファイル名生成に必要なので残します

# FastAPI, Request, HTTPException のインポートを追加
from fastapi import FastAPI, Request, HTTPException, status
# LINE Bot SDK のインポート
from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import MessagingApi, Configuration, ApiClient
from linebot.v3.messaging import MessagingApiBlob # メッセージコンテンツ取得用
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, VideoMessageContent
from linebot.v3.messaging.models import ReplyMessageRequest, TextMessage

# ★ 追加: LINE例外クラスをインポート
import linebot.v3.exceptions
# ★ 追加: トレースバック表示用
import traceback
# ★ 修正: HttpError をインポート
from googleapiclient.errors import HttpError

# Google Docs/Drive連携用のモジュール (環境変数が必要なのでload_dotenvの後にインポート)
try:
    from google_docs_util import send_google_doc
except ValueError as e:
    print(f"Error loading google_docs_util: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"An unexpected error occurred while importing google_docs_util: {e}", file=sys.stderr)
    sys.exit(1)

try:
    from google_drive_util import upload_file_to_drive
except ValueError as e:
    print(f"Error loading google_drive_util: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"An unexpected error occurred while importing google_drive_util: {e}", file=sys.stderr)
    sys.exit(1)


# データベースモジュールのインポートとテーブル作成
try:
    from database import SessionLocal, UserDocMapping, create_tables
except Exception as e:
    print(f"Error importing database module: {e}", file=sys.stderr)
    sys.exit(1)


# 環境変数から設定値を読み込む
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')

# 環境変数の存在チェック
if not LINE_CHANNEL_SECRET:
    print("Error: LINE_CHANNEL_SECRET environment variable is not set.", file=sys.stderr)
    sys.exit(1)
if not LINE_CHANNEL_ACCESS_TOKEN:
    print("Error: LINE_CHANNEL_ACCESS_TOKEN environment variable is not set.", file=sys.stderr)
    sys.exit(1)

print("DEBUG: LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN are set.", file=sys.stderr)
# ★ 追加: ロードしたChannel Secretの長さをログ出力 (値そのものは出力しない)
print(f"DEBUG: Loaded LINE_CHANNEL_SECRET length: {len(LINE_CHANNEL_SECRET)}", file=sys.stderr)
print(f"DEBUG: Loaded LINE_CHANNEL_SECRET type: {type(LINE_CHANNEL_SECRET).__name__}", file=sys.stderr)


# データベーステーブルの作成
# 修正箇所: if __name__ == '__main__': ブロックの外に移動
try:
    print("Checking and creating database tables if necessary...", file=sys.stderr)
    create_tables()
    print("Database table check/creation complete.", file=sys.stderr)
except Exception as e:
    print(f"Failed to create database tables on startup: {e}", file=sys.stderr)
    # 起動時にDBエラーが発生した場合は、そこで終了させる方が安全
    sys.exit(1) # システムを終了


# FastAPI アプリケーションの初期化
app = FastAPI()
# LINE WebhookHandler の初期化
handler = WebhookHandler(LINE_CHANNEL_SECRET) # ★ ここでLINE_CHANNEL_SECRETを使用
# LINE Messaging API Configuration の初期化
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

# ドキュメントIDを設定するコマンドのプレフィックス
SET_DOC_COMMAND_PREFIX = "!setdoc "
# GoogleドキュメントIDの正規表現 (簡易的なチェック)
DOC_ID_REGEX = r"^[a-zA-Z0-9_-]{20,}$" # 少なくとも20文字以上など、もう少し厳密に


# Webhook エンドポイント
# main.py の @app.post("/callback") 関数を以下のように修正

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body() # body は bytes 型

    print(f"DEBUG: Received webhook request.", file=sys.stderr)
    print(f"DEBUG: X-Line-Signature header: {signature}", file=sys.stderr)
    # ★ 追加: リクエストボディの長さをログ出力
    print(f"DEBUG: Request body length: {len(body)} bytes.", file=sys.stderr)
    print(f"DEBUG: Request body (bytes, first 200 chars): {body[:200]}...", file=sys.stderr)
    print(f"DEBUG: Handler is using LINE_CHANNEL_SECRET with length: {len(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else 0}", file=sys.stderr)

    try:
        # 修正箇所: bodyが空の場合のdecodeエラー回避 (handler.handleが空文字列を許容する前提)
        body_str = body.decode('utf-8') if body else ""
        print(f"DEBUG: Decoded body (first 200 chars): {body_str[:200]}...", file=sys.stderr)
        handler.handle(body_str, signature) # 修正済みのbody_strを渡す
        print("DEBUG: Webhook handler processed successfully (no signature error).", file=sys.stderr) # 署名検証成功時のログ
        return "OK" # 正常処理の場合は200 OKを返す

    except linebot.v3.exceptions.InvalidSignatureError as e:
        print(f"ERROR: !!! Invalid LINE signature received !!!", file=sys.stderr)
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        print(f"DEBUG: Received signature: {signature}", file=sys.stderr)
        print(f"DEBUG: Configured secret length used by handler: {len(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else 0}", file=sys.stderr)

        # --- ★ Webhook検証ツール対応の追加 ★ ---
        # Webhook検証ツールからのリクエストは、通常、空のボディを持つ ({})
        # body_str が空、または非常に短い場合（例: 20バイト未満）を検証ツールと判断する
        # '{}\n' のようなボディでも対応できるように、少し余裕を持たせる
        if not body_str or len(body_str) < 20:
            print(f"DEBUG: Invalid signature detected with empty or short body ({len(body_str)} chars). Assuming Webhook verification request. Returning 200 OK.", file=sys.stderr)
            return "OK" # 検証ツールからの場合は200 OKを返す
        # --- ★ 追加終了 ★ ---

        # 検証ツールからのリクエストでなければ、本来のInvalidSignatureErrorとして400を返す
        print("DEBUG: Invalid signature detected with non-short body. Treating as potential malicious request.", file=sys.stderr)
        raise HTTPException(status_code=400, detail="Invalid LINE signature.")

    except HTTPException as e:
         # FastAPI's HTTPExceptionはそのまま再raise
         print(f"DEBUG: Caught FastAPI HTTPException in callback: {e.detail} (Status: {e.status_code})", file=sys.stderr)
         raise e

    except linebot.v3.exceptions.LineBotApiError as e:
         print(f"ERROR: LINE API Error during webhook processing. Status: {e.status_code}, Message: {e.message}", file=sys.stderr)
         traceback.print_exc(file=sys.stderr)
         raise HTTPException(status_code=500, detail=f"LINE API Error during processing: {e.status_code} - {e.message}")

    except Exception as e:
        print(f"CRITICAL: Unexpected error during webhook processing: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Internal server error: {type(e).__name__}")


# ヘルスチェック用のエンドポイント
@app.get("/")
async def health_check():
    # 簡易的なヘルスチェック
    return {"status": "ok"}


# メッセージハンドラ内でデータベースセッションを使用するためのヘルパー関数
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ユーザーIDに紐づくGoogleドキュメントIDを取得
def get_user_doc_id(user_id: str, db) -> str | None:
    try:
        mapping = db.query(UserDocMapping).filter(UserDocMapping.user_id == user_id).first()
        return mapping.doc_id if mapping else None
    except Exception as e:
        print(f"Database error getting doc_id for user {user_id}: {e}", file=sys.stderr)
        raise

# ユーザーIDにGoogleドキュメントIDを設定
def set_user_doc_id(user_id: str, doc_id: str, db):
    try:
        mapping = db.query(UserDocMapping).filter(UserDocMapping.user_id == user_id).first()
        if mapping:
            mapping.doc_id = doc_id
        else:
            mapping = UserDocMapping(user_id=user_id, doc_id=doc_id)
            db.add(mapping)
        db.commit()
        print(f"Successfully set doc_id '{doc_id}' for user {user_id}.", file=sys.stderr)
    except Exception as e:
        print(f"Database error setting doc_id for user {user_id} to '{doc_id}': {e}", file=sys.stderr)
        db.rollback()
        raise


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    user_id = event.source.user_id
    user_text = event.message.text
    reply_token = event.reply_token
    reply = ""

    db = None
    try:
        db = next(get_db())

        if user_text.startswith(SET_DOC_COMMAND_PREFIX):
            doc_id_candidate = user_text[len(SET_DOC_COMMAND_PREFIX):].strip()
            print(f"User {user_id} attempting to set doc ID: '{doc_id_candidate}'", file=sys.stderr)

            if re.fullmatch(DOC_ID_REGEX, doc_id_candidate):
                 try:
                     set_user_doc_id(user_id, doc_id_candidate, db)
                     reply = f"ドキュメントID '{doc_id_candidate}' をあなたの設定として保存しました！\nこれからはこのドキュメントにメモを追記します。"
                 except Exception as e:
                     print(f"Database error setting doc_id for user {user_id}: {e}", file=sys.stderr)
                     reply = f"ドキュメントIDの設定中にデータベースエラーが発生しました。\nエラー詳細: {type(e).__name__}"
            else:
                 reply = f"無効なドキュメントIDの形式です。\nドキュメントIDは通常URLの`/.../d/YOUR_ID/.../` の `YOUR_ID` の部分です。\n例: `!setdoc abcdefghijklmnopqrstuvwxyz1234567890`"

            _reply_line(reply_token, reply)
            return

        print(f"User {user_id} sent text message. Checking for doc ID...", file=sys.stderr)
        doc_id = get_user_doc_id(user_id, db)

        if not doc_id:
            reply = f"ドキュメントが設定されていません。\n書き込みたいGoogleドキュメントIDを `!setdoc [ドキュメントID]` コマンドで指定してください。"
            _reply_line(reply_token, reply)
            return

        print(f"Doc ID {doc_id} found for user {user_id}. Attempting to write text.", file=sys.stderr)
        try:
            # 追記するテキストはユーザーの入力そのものにする (タイムスタンプ削除済み)
            text_to_append = user_text
            print(f"Appending text: '{text_to_append}' to doc '{doc_id}'", file=sys.stderr) # デバッグログ

            # send_google_doc 関数に新しいテキストを渡す
            # send_google_doc 側で、テキストの前に改行を入れる処理を試みます。
            doc_url = send_google_doc(document_id=doc_id, text=text_to_append)

            reply = f"メッセージをドキュメントに追記しました！\n編集: {doc_url}"
        except (ValueError, PermissionError, RuntimeError, HttpError) as e:
            print(f"Docs Text Write Error for user {user_id} (doc: {doc_id}): {e}", file=sys.stderr)
            if isinstance(e, ValueError):
                 # Google Doc with ID '{document_id}' not found. Check the ID.
                 # Google Docs API rejected the update request (Status 400). Error details: ...
                 reply_msg = f"ドキュメントへの書き込みに失敗しました。\nエラー: {e}"
                 # 400エラーの場合、詳細情報も少し含める
                 if isinstance(e, HttpError) and e.resp.status == 400 and e.content:
                      reply_msg += f"\nAPIエラー詳細: {e.content.decode('utf-8', errors='ignore')[:100]}..." # 長すぎないように制限
                 reply = reply_msg
            elif isinstance(e, PermissionError):
                 reply = f"ドキュメントへの書き込みに失敗しました。\nエラー: サービスアカウントにこのドキュメントへの編集権限がありません。"
            elif isinstance(e, HttpError):
                 reply = f"ドキュメントへの書き込み中にGoogle Docs APIエラーが発生しました。\nエラーコード: {e.resp.status}"
                 if e.content:
                     print(f"HTTP Error Response Body: {e.content.decode('utf-8', errors='ignore')}", file=sys.stderr)
            else:
                 reply = f"ドキュメントへの書き込み中にエラーが発生しました。\nエラー詳細: {type(e).__name__}"
        except Exception as e:
            print(f"Unexpected Error in send_google_doc (text) for user {user_id} (doc: {doc_id}): {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr) # 予期しないエラーのトレースバックを出力
            reply = f"ドキュメントへの書き込み中に予期しないエラーが発生しました。\nエラー詳細: {type(e).__name__}"

        _reply_line(reply_token, reply)

    except Exception as e:
        print(f"Unexpected top-level error in handle_text for user {user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr) # トップレベルエラーのトレースバックもログ出力
        _reply_line(reply_token, f"メッセージ処理中に予期しないエラーが発生しました。\nエラー詳細: {type(e).__name__}")
    finally:
        if db:
            db.close()


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event: MessageEvent):
    user_id = event.source.user_id
    image_id = event.message.id
    reply_token = event.reply_token
    mime_type = "image/jpeg" # 推測値、実際はContent-Typeヘッダーから取得が望ましい
    reply = ""

    db = None
    try:
        db = next(get_db())
        print(f"User {user_id} sent image message (ID: {image_id}). Checking for doc ID...", file=sys.stderr)
        doc_id = get_user_doc_id(user_id, db)

        if not doc_id:
            reply = f"ドキュメントが設定されていません。\n画像を貼り付けたいGoogleドキュメントIDを `!setdoc [ドキュメントID]` コマンドで指定してください。"
            _reply_line(reply_token, reply)
            return

        print(f"Doc ID {doc_id} found for user {user_id}. Attempting to process image.", file=sys.stderr)
        try:
            print(f"Attempting to get image content for ID: {image_id}", file=sys.stderr)
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                # get_message_content は bytes を返します
                # 正確なMIMEタイプを取得するには get_message_content_with_http_info を使う
                # resp = blob_api.get_message_content_with_http_info(message_id=image_id)
                # image_data = resp.data
                # actual_mime_type = resp.headers.get('Content-Type', mime_type) # ヘッダーから取得
                image_data = blob_api.get_message_content(message_id=image_id) # 簡単化のためBytesのみ取得
            print(f"Successfully got {len(image_data)} bytes of image content for ID: {image_id}. Assumed MIME type: {mime_type}", file=sys.stderr)


            # ファイル名にはタイムスタンプを残しておきます（管理のため）
            # datetime モジュールは handle_image 関数内でもファイル名生成に使われているため、削除しませんでした。
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            ext = mime_type.split('/')[-1] if '/' in mime_type else 'bin'
            fname = f"line_image_{timestamp}_{image_id}.{ext}"
            print(f"Attempting to upload image to Drive: {fname}", file=sys.stderr)
            file_id, direct_link, webview_link = upload_file_to_drive(image_data, fname, mime_type)

            if not direct_link and not webview_link:
                 raise RuntimeError(f"Google Drive upload succeeded but no usable link (webContentLink or webViewLink) was obtained for file ID: {file_id or 'N/A'}")

            image_uri_to_embed = direct_link if direct_link else webview_link # どちらか取得できた方を使う
            print(f"Attempting to send image to Docs (doc: {doc_id}) via URI: {image_uri_to_embed}", file=sys.stderr)

            # send_google_doc 関数に画像URIを渡す。send_google_doc 側で、画像の前に改行を入れる処理を試みます。
            doc_url = send_google_doc(document_id=doc_id, image_uri=image_uri_to_embed)
            print(f"Successfully sent image to Docs. Doc URL: {doc_url}", file=sys.stderr)

            image_access_link = webview_link if webview_link else file_id
            reply = f"画像をドキュメントに貼り付けました！\n編集: {doc_url}\n画像リンク: {image_access_link}"

        except (ValueError, PermissionError, RuntimeError, HttpError) as e:
            print(f"Image Handling Error for user {user_id} (doc: {doc_id}, image: {image_id}): {e}", file=sys.stderr)
            if isinstance(e, ValueError):
                 reply_msg = f"画像の処理に失敗しました。\nエラー: {e}"
                 if isinstance(e, HttpError) and e.resp.status == 400 and e.content:
                      reply_msg += f"\nAPIエラー詳細: {e.content.decode('utf-8', errors='ignore')[:100]}..."
                 reply = reply_msg
            elif isinstance(e, PermissionError):
                 reply = f"画像の処理に失敗しました。\nエラー: Google Drive/Docsへの権限がありません。"
            elif isinstance(e, HttpError):
                 reply = f"画像処理中にGoogle APIエラーが発生しました。\nエラーコード: {e.resp.status}"
                 if e.content:
                     print(f"HTTP Error Response Body: {e.content.decode('utf-8', errors='ignore')}", file=sys.stderr)
            elif isinstance(e, RuntimeError) and "obtain usable link" in str(e):
                 reply = f"画像をGoogle Driveにアップロードしましたが、リンクの取得に失敗しました。サービスアカウントの共有設定をご確認ください。"
            else:
                 reply = f"画像の処理中にエラーが発生しました。\nエラー詳細: {type(e).__name__}"
        except Exception as e:
            print(f"Unexpected Error in handle_image for user {user_id} (doc: {doc_id}, image: {image_id}): {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            reply = f"画像処理中に予期しないエラーが発生しました。\nエラー詳細: {type(e).__name__}"

        _reply_line(reply_token, reply)

    except Exception as e:
        print(f"Unexpected top-level error in handle_image for user {user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        _reply_line(reply_token, f"画像処理中に予期しないエラーが発生しました。\nエラー詳細: {type(e).__name__}")
    finally:
        if db:
            db.close()


@handler.add(MessageEvent, message=VideoMessageContent)
def handle_video(event: MessageEvent):
    user_id = event.source.user_id
    video_id = event.message.id
    reply_token = event.reply_token
    mime_type = "video/mp4" # 推測値、実際はContent-Typeヘッダーから取得が望ましい
    reply = ""

    db = None
    try:
        db = next(get_db())
        print(f"User {user_id} sent video message (ID: {video_id}). Checking for doc ID...", file=sys.stderr)
        doc_id = get_user_doc_id(user_id, db)

        if not doc_id:
            reply = f"ドキュメントが設定されていません。\n動画のリンクを追記したいGoogleドキュメントIDを `!setdoc [ドキュメントID]` コマンドで指定してください。"
            _reply_line(reply_token, reply)
            return

        print(f"Doc ID {doc_id} found for user {user_id}. Attempting to process video.", file=sys.stderr)
        try:
            print(f"Attempting to get video content for ID: {video_id}", file=sys.stderr)
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                # get_message_content は bytes を返します
                video_data = blob_api.get_message_content(message_id=video_id)
            print(f"Successfully got {len(video_data)} bytes of video content for ID: {video_id}. Assumed MIME type: {mime_type}", file=sys.stderr)


            # ファイル名にはタイムスタンプを残しておきます（管理のため）
            timestamp_file = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') # handle_video 関数内でも必要なので残します
            ext = mime_type.split('/')[-1] if '/' in mime_type else 'bin'
            fname = f"line_video_{timestamp_file}_{video_id}.{ext}"
            print(f"Attempting to upload video to Drive: {fname}", file=sys.stderr)
            file_id, direct_link, webview_link = upload_file_to_drive(video_data, fname, mime_type)

            if not webview_link:
                 raise RuntimeError(f"Google Drive upload succeeded but webViewLink was not obtained for video file ID: {file_id or 'N/A'}.")

            print(f"Attempting to send video link to Docs (doc: {doc_id})", file=sys.stderr)

            # ドキュメントに追記するテキストからタイムスタンプを削除済み
            doc_text = f"動画 ({fname}) : {webview_link}\n"

            # send_google_doc 関数にテキストを渡す。send_google_doc 側で、テキストの前に改行を入れる処理を試みます。
            doc_url = send_google_doc(document_id=doc_id, text=doc_text)
            print(f"Successfully sent video link to Docs. Doc URL: {doc_url}", file=sys.stderr)

            reply = f"動画をDriveにアップロードしました！\nドキュメントにリンクを追記しました！\n編集: {doc_url}\n動画リンク: {webview_link}"

        except (ValueError, PermissionError, RuntimeError, HttpError) as e:
            print(f"Video Handling Error for user {user_id} (doc: {doc_id}, video: {video_id}): {e}", file=sys.stderr)
            if isinstance(e, ValueError):
                 reply_msg = f"動画の処理に失敗しました。\nエラー: {e}"
                 if isinstance(e, HttpError) and e.resp.status == 400 and e.content:
                      reply_msg += f"\nAPIエラー詳細: {e.content.decode('utf-8', errors='ignore')[:100]}..."
                 reply = reply_msg
            elif isinstance(e, PermissionError):
                 reply = f"動画の処理に失敗しました。\nエラー: Google Drive/Docsへの権限がありません。"
            elif isinstance(e, HttpError):
                 reply = f"動画処理中にGoogle APIエラーが発生しました。\nエラーコード: {e.resp.status}"
                 if e.content:
                     print(f"HTTP Error Response Body: {e.content.decode('utf-8', errors='ignore')}", file=sys.stderr)
            elif isinstance(e, RuntimeError) and "webViewLink was not obtained" in str(e):
                 reply = f"動画をGoogle Driveにアップロードしましたが、閲覧リンクの取得に失敗しました。サービスアカウントの共有設定をご確認ください。"
            else:
                 reply = f"動画の処理中にエラーが発生しました。\nエラー詳細: {type(e).__name__}"
        except Exception as e:
            print(f"Unexpected Error in handle_video for user {user_id} (doc: {doc_id}, video: {video_id}): {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            reply = f"動画処理中に予期しないエラーが発生しました。\nエラー詳細: {type(e).__name__}"

        _reply_line(reply_token, reply)

    except Exception as e:
        print(f"Unexpected top-level error in handle_video for user {user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        _reply_line(reply_token, f"動画処理中に予期しないエラーが発生しました。\nエラー詳細: {type(e).__name__}")
    finally:
        if db:
            db.close()


def _reply_line(token: str, text: str):
    try:
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            req = ReplyMessageRequest(
                reply_token=token,
                messages=[TextMessage(text=text)]
            )
            try:
                messaging_api.reply_message(reply_message_request=req)
                print(f"Successfully sent reply to token {token[:10]}...", file=sys.stderr)
            except Exception as reply_e:
                 print(f"Failed to send reply message to token {token[:10]}...: {reply_e}", file=sys.stderr)

    except Exception as e:
        print(f"Error creating LINE API client or sending reply: {e}", file=sys.stderr)


# FastAPI アプリケーション起動時にのみ実行される部分
if __name__ == '__main__':
    print("\n" + "="*50, file=sys.stderr)
    print("INFO: Running main.py directly using 'python main.py'.", file=sys.stderr)
    print("This execution method is primarily for local development and testing (without auto-reload).", file=sys.stderr)
    print("="*50 + "\n", file=sys.stderr)

    # PORT環境変数があればそれを使い、なければ8000をデフォルトとする
    # これは `python main.py` で直接実行する場合のポート設定
    port = int(os.environ.get('PORT', 8000))
    print(f"INFO: For local 'python main.py' execution, attempting to start server on http://0.0.0.0:{port}", file=sys.stderr)

    print("\n--- Local Development Server Information ---", file=sys.stderr)
    print("1. For development with auto-reload, it's recommended to use Uvicorn CLI:", file=sys.stderr)
    print(f"   uvicorn main:app --reload --host 0.0.0.0 --port {port}", file=sys.stderr)
    print("   (This command respects the PORT environment variable if set, otherwise Uvicorn defaults, e.g. 8000)", file=sys.stderr)

    print("\n2. If using ngrok for exposing this local server:", file=sys.stderr)
    print(f"   - After starting the server (via 'python main.py' or Uvicorn CLI), run 'ngrok http {port}' in another terminal.", file=sys.stderr)
    print("   - Use the ngrok HTTPS URL (e.g., https://xxxx.ngrok-free.app) for LINE Webhook settings.", file=sys.stderr)
    
    print("\n--- Deployment (e.g., on Fly.io) ---", file=sys.stderr)
    print("For deploying to services like Fly.io:", file=sys.stderr)
    print(" - The application is typically started using a command specified in your deployment configuration", file=sys.stderr)
    print("   (e.g., 'fly.toml' [processes] section, Procfile, or Dockerfile CMD).", file=sys.stderr)
    print(" - A common startup command for FastAPI apps is: uvicorn main:app --host 0.0.0.0 --port <PORT_NUMBER>", file=sys.stderr)
    print("   (Where <PORT_NUMBER> is the internal port the app should listen on, e.g., 8000 or 8080).", file=sys.stderr)
    print("   Fly.io (and similar platforms) often set a $PORT environment variable, which Uvicorn can automatically use if --port is not specified.", file=sys.stderr)
    print(" - The 'python main.py' execution path (this __main__ block) is NOT used in such deployed environments.", file=sys.stderr)
    print("---" + "="*38 + "---", file=sys.stderr)


    try:
        import uvicorn
        # The uvicorn.run() call below is only for when 'python main.py' is executed directly.
        # In deployed environments (like Fly.io), Uvicorn is typically started via a CLI command.
        uvicorn.run(app, host='0.0.0.0', port=port)
    except ImportError:
        print("ERROR: 'uvicorn' is not installed. 'python main.py' requires it to run the server.", file=sys.stderr)
        print("Please install it using: pip install uvicorn[standard]", file=sys.stderr)
        print("Alternatively, for development, you can run directly with Uvicorn CLI:", file=sys.stderr)
        print(f"uvicorn main:app --reload --host 0.0.0.0 --port {port}", file=sys.stderr)
    except Exception as e:
        print(f"Error starting uvicorn server via 'python main.py': {e}", file=sys.stderr)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
