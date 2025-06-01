# Python 3.11をベースにする（他のバージョンでもOK）
FROM python:3.11-slim

# 作業ディレクトリを作る
WORKDIR /app

# 必要ファイルをコピー
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# アプリケーションの起動（Flaskの場合の例）
CMD ["python", "main.py"]
