## main.py
import os
import sys
import re # ドキュメントIDをパースするために正規表現モジュールをインポート
from fastapi import FastAPI, Request, HTTPException
# from dotenv import load_dotenv

# LINE Bot SDK v3 のインポート
from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import MessagingApi, Configuration, ApiClient
from linebot.v3.messaging import MessagingApiBlob
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from linebot.v3.messaging.models import ReplyMessageRequest, TextMessage

# Google Docs/Drive連携用のモジュール
from google_docs_util import send_google_doc
from google_drive_util import upload_image_to_drive

# データベースモジュールのインポートとテーブル作成
from database import SessionLocal, UserDocMapping, create_tables

# # .env ファイルから環境変数を読み込む - 削除
# load_dotenv()

# .envから直接設定 (Renderの環境変数で上書きされるのが推奨)
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'e9566f259a649348142753e116dedd10')
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'bykF+pK9K7UOIs+EkZ1EzkzuTlt9allQisNFAwwA2wyvgwaMr+0PD2bQ4KGQf7nhE5Hxj8nwLBEY6AgDhPciHr3P6rIiMr13Dr9aXU32DO5aLV1G0GQ8PMdH+ofbgs+dO8KQhfyYfu2bd9Opo49v2wdB04t89/1O/w1cDnyilFU=')


# 環境変数の存在チェック
if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    print("Error: LINE_CHANNEL_SECRET or LINE_CHANNEL_ACCESS_TOKEN is not set.", file=sys.stderr)
    sys.exit(1)

# データベーステーブルの作成をアプリケーション起動前に行う
# RenderのEntrypointやBuild Commandで実行する方が確実な場合もありますが、
# ここでは簡易的に起動時にチェック＆作成を行います。
try:
    create_tables()
except Exception as e:
    print(f"Failed to create database tables on startup: {e}", file=sys.stderr)
    # テーブル作成に失敗した場合、DBへのアクセスが必要な機能は動作しません。
    # アプリケーションを続行するか、エラーとして終了するかは設計によります。
    # 今回は続行しますが、DBアクセス失敗時のエラーハンドリングは必要です。


# FastAPI アプリケーションの初期化
app = FastAPI()
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

# ドキュメントIDを設定するコマンドのプレフィックス
SET_DOC_COMMAND_PREFIX = "!setdoc "

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode('utf-8'), signature)
    except Exception as e:
        print(f"Webhook handling failed: {e}", file=sys.stderr)
        # LINEへの応答ができない場合でも、Webhookとしてはエラーコードを返す
        # e.g., linebot.v3.exceptions.InvalidSignatureError, HTTPException from handlers
        raise HTTPException(status_code=400, detail=f"Webhook handling failed: {e}")
    return "OK" # 正常に処理を受け付けたらOKを返す


# メッセージハンドラ内でデータベースセッションを使用するためのヘルパー関数
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ユーザーIDに紐づくGoogleドキュメントIDを取得
def get_user_doc_id(user_id: str, db) -> str | None:
    mapping = db.query(UserDocMapping).filter(UserDocMapping.user_id == user_id).first()
    return mapping.doc_id if mapping else None

# ユーザーIDにGoogleドキュメントIDを設定
def set_user_doc_id(user_id: str, doc_id: str, db):
    # 既存のマッピングがあれば更新、なければ新規作成
    mapping = db.query(UserDocMapping).filter(UserDocMapping.user_id == user_id).first()
    if mapping:
        mapping.doc_id = doc_id
    else:
        mapping = UserDocMapping(user_id=user_id, doc_id=doc_id)
        db.add(mapping)
    db.commit()

# GoogleドキュメントIDの正規表現 (簡易的なチェック)
# ドキュメントIDは通常、大文字・小文字、数字、ハイフン、アンダースコアのみで構成される長い文字列です。
# URL全体の場合もあり得ますが、ここではID部分のみを想定します。
DOC_ID_REGEX = r"^[a-zA-Z0-9_-]+$"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    user_id = event.source.user_id # LINE User ID を取得
    user_text = event.message.text
    reply_token = event.reply_token

    # データベースセッションの開始
    db = None
    try:
        db = next(get_db()) # ヘルパー関数でセッションを取得

        # ドキュメントID設定コマンドの処理
        if user_text.startswith(SET_DOC_COMMAND_PREFIX):
            # コマンド部分を除去し、ドキュメントID候補を取得
            doc_id_candidate = user_text[len(SET_DOC_COMMAND_PREFIX):].strip()

            # ドキュメントIDとして有効か簡易チェック
            if re.fullmatch(DOC_ID_REGEX, doc_id_candidate):
                 set_user_doc_id(user_id, doc_id_candidate, db)
                 reply = f"ドキュメントID '{doc_id_candidate}' をあなたの設定として保存しました！"
            else:
                 reply = f"無効なドキュメントIDの形式です。ドキュメントIDは通常URLの/.../d/YOUR_ID/.../ の YOUR_ID の部分です。\n例: !setdoc abcdefghijklmnopqrstuvwxyz123456"

            _reply_line(reply_token, reply)
            return # コマンド処理が終わったら終了

        # 通常メッセージの処理（ドキュメントへの書き込み）
        doc_id = get_user_doc_id(user_id, db)

        if not doc_id:
            reply = f"ドキュメントが設定されていません。\n書き込みたいGoogleドキュメントIDを '!setdoc [ドキュメントID]' コマンドで指定してください。\n使用したいドキュメントに「google-bot@gen-lang-client-0327920278.iam.gserviceaccount.com」を共有してください。"
            _reply_line(reply_token, reply)
            return # ドキュメントIDが設定されていない場合は書き込み処理をスキップ

        # ドキュメントIDが設定されていれば書き込みを実行
        try:
            # send_google_doc にドキュメントIDを渡す
            doc_url = send_google_doc(document_id=doc_id, text=user_text)
            reply = f"メッセージをドキュメントに追記しました！\n編集: {doc_url}"
        except Exception as e:
            print(f"Docs Text Error for user {user_id} (doc: {doc_id}): {e}", file=sys.stderr)
            reply = f"テキストの書き込みに失敗しました: {e}" # エラーメッセージを返信に含める

        _reply_line(reply_token, reply)

    except Exception as e:
        print(f"Unexpected error in handle_text for user {user_id}: {e}", file=sys.stderr)
        # 予期しないエラーの場合もユーザーに通知
        _reply_line(reply_token, "メッセージ処理中に予期しないエラーが発生しました。")
    finally:
        # データベースセッションをクローズ
        if db:
            db.close()


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event: MessageEvent):
    user_id = event.source.user_id # LINE User ID を取得
    image_id = event.message.id
    reply_token = event.reply_token

    # データベースセッションの開始
    db = None
    try:
        db = next(get_db()) # ヘルパー関数でセッションを取得

        # ユーザーに紐づくドキュメントIDを取得
        doc_id = get_user_doc_id(user_id, db)

        if not doc_id:
            reply = f"ドキュメントが設定されていません。\n画像を貼り付けたいGoogleドキュメントIDを '!setdoc [ドキュメントID]' コマンドで指定してください。"
            _reply_line(reply_token, reply)
            return # ドキュメントIDが設定されていない場合は処理をスキップ

        # ドキュメントIDが設定されていれば画像処理を実行
        try:
            # 画像取得
            print(f"Attempting to get image content for ID: {image_id}", file=sys.stderr) # デバッグログ
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                image_data = blob_api.get_message_content(message_id=image_id)
            print(f"Successfully got image content for ID: {image_id}", file=sys.stderr) # デバッグログ


            # Driveへアップロード
            timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
            fname = f"line_{timestamp}_{image_id}.jpg"
            print(f"Attempting to upload image to Drive: {fname}", file=sys.stderr) # デバッグログ
            file_id, direct_link = upload_image_to_drive(image_data, fname)

            if not direct_link:
                raise Exception("Drive direct link missing after upload.") # より具体的なエラーメッセージ
            print(f"Drive upload successful. File ID: {file_id}, Direct Link: {direct_link}", file=sys.stderr) # デバッグログ


            # Docsへ埋め込み
            print(f"Attempting to send image to Docs (doc: {doc_id}) via URI: {direct_link}", file=sys.stderr) # デバッグログ
            # send_google_doc にドキュメントIDを渡す
            doc_url = send_google_doc(document_id=doc_id, image_uri=direct_link)
            print(f"Successfully sent image to Docs. Doc URL: {doc_url}", file=sys.stderr) # デバッグログ
            reply = f"画像をドキュメントに貼り付けました！\n編集: {doc_url}\n画像: {direct_link}"

        except Exception as e:
            print(f"Image Handling Error for user {user_id} (doc: {doc_id}, image: {image_id}): {e}", file=sys.stderr)
            reply = f"画像の処理に失敗しました: {e}" # エラーメッセージを返信に含める

        _reply_line(reply_token, reply)

    except Exception as e:
        print(f"Unexpected error in handle_image for user {user_id}: {e}", file=sys.stderr)
        # 予期しないエラーの場合もユーザーに通知
        _reply_line(reply_token, "画像処理中に予期しないエラーが発生しました。")
    finally:
        # データベースセッションをクローズ
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
            messaging_api.reply_message(reply_message_request=req)
    except Exception as e:
        # リプライに失敗しても、ログに出力するだけで処理は止めないことが多い
        print(f"Reply Error: {e}", file=sys.stderr)

if __name__ == '__main__':
    import uvicorn
    # RenderではGunicornがポートを割り当てるため、ここではローカル実行用のデフォルトポートを使用
    # PORT環境変数があればそれを使用、なければ8000
    port = int(os.environ.get('PORT', 8000))
    print(f"Starting uvicorn on port {port}", file=sys.stderr) # デバッグログ

    # ローカル実行時は簡易的にデータベーステーブルを作成
    if os.environ.get('RENDER') != 'true': # Render環境でない場合
         try:
             print("Creating database tables for local execution...", file=sys.stderr)
             create_tables()
             print("Database tables created (or already exist).", file=sys.stderr)
         except Exception as e:
             print(f"Error creating tables locally: {e}", file=sys.stderr)


    uvicorn.run('main:app', host='0.0.0.0', port=port, reload=True)
