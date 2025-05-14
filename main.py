## main.py
import os
import sys  # エラーメッセージ表示用
from fastapi import FastAPI, Request, HTTPException
# from dotenv import load_dotenv # .envのロードを削除

# LINE Bot SDK v3 のインポート
from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import MessagingApi, Configuration, ApiClient
from linebot.v3.messaging import MessagingApiBlob  # 画像コンテンツ取得用
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from linebot.v3.messaging.models import ReplyMessageRequest, TextMessage

# Google Docs/Drive連携用のモジュール
from google_docs_util import send_google_doc
from google_drive_util import upload_image_to_drive

# # .env ファイルから環境変数を読み込む - 削除
# load_dotenv()

# .envから直接設定
LINE_CHANNEL_SECRET = 'e9566f259a649348142753e116dedd10' # LINE_CHANNEL_SECRETを直接設定
LINE_CHANNEL_ACCESS_TOKEN = 'bykF+pK9K7UOIs+EkZ1EzkzuTlt9allQisNFAwwA2wyvgwaMr+0PD2bQ4KGQf7nhE5Hxj8nwLBEY6AgDhPciHr3P6rIiMr13Dr9aXU32DO5aLV1G0GQ8PMdH+ofbgs+dO8KQhfyYfu2bd9Opo49v2wdB04t89/1O/w1cDnyilFU=' # LINE_CHANNEL_ACCESS_TOKENを直接設定

# 環境変数の存在チェック - 不要になるが、念のため残しても良い
if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    # このエラーメッセージは表示されなくなる
    # print("Error: LINE_CHANNEL_SECRET or LINE_CHANNEL_ACCESS_TOKEN is not set.", file=sys.stderr)
    # sys.exit(1)
    pass # ハードコードされたため常に存在する

# FastAPI アプリケーションの初期化
app = FastAPI()
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode('utf-8'), signature)
    except Exception as e:
        print(f"Webhook Error: {e}", file=sys.stderr)
        raise HTTPException(status_code=400, detail="Webhook handling failed")
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event: MessageEvent):
    user_text = event.message.text
    try:
        doc_url = send_google_doc(text=user_text)
        reply = f"メッセージをドキュメントに追記しました！\n編集: {doc_url}"
    except Exception as e:
        print(f"Docs Text Error: {e}", file=sys.stderr)
        reply = "テキストの書き込みに失敗しました。"
    _reply_line(event.reply_token, reply)

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event: MessageEvent):
    image_id = event.message.id
    try:
        # 画像取得
        with ApiClient(configuration) as api_client:
            blob_api = MessagingApiBlob(api_client)
            image_data = blob_api.get_message_content(message_id=image_id)

        # Driveへアップロード
        timestamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f"line_{timestamp}_{image_id}.jpg"
        file_id, direct_link = upload_image_to_drive(image_data, fname)
        if not direct_link:
            raise Exception("Drive direct link missing")

        # Docsへ埋め込み
        doc_url = send_google_doc(image_uri=direct_link)
        reply = f"画像をドキュメントに貼り付けました！\n編集: {doc_url}\n画像: {direct_link}"
    except Exception as e:
        print(f"Image Handling Error: {e}", file=sys.stderr)
        reply = "画像の処理に失敗しました。"
    _reply_line(event.reply_token, reply)

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
        print(f"Reply Error: {e}", file=sys.stderr)

if __name__ == '__main__':
    import uvicorn
    # .envから直接設定
    port = 8000 # PORTを直接設定
    uvicorn.run('main:app', host='0.0.0.0', port=port, reload=True)