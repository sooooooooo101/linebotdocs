# database.py

import os
import sys
import logging
from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# --- ロギング設定（デバッグ用） ---
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 1. 環境変数から DATABASE_URL を取得
#    - Koyeb に設定された DATABASE_URL は通常 "postgres://..." 形式の場合がある
#    - SQLAlchemy 2.0 以降では "postgresql://..." を期待するため、
#      必要に応じて文字列置換を行う
#    - ローカル開発時は環境変数が未設定の可能性があるため、
#      その場合は SQLite のファイルをフォールバックで利用する
# ------------------------------------------------------------
raw_url = os.environ.get("DATABASE_URL")
if raw_url:
    # Koyeb や一部プロバイダでは "postgres://" を渡してくる場合があるので置換
    if raw_url.startswith("postgres://"):
        corrected = raw_url.replace("postgres://", "postgresql://", 1)
        logger.debug(f"`postgres://` を検知したため自動で `postgresql://` に置換しました: {corrected}")
        DATABASE_URL = corrected
    else:
        DATABASE_URL = raw_url
    logger.debug(f"使用する DATABASE_URL: {DATABASE_URL}")
else:
    # 環境変数が設定されていない場合はローカル開発用に SQLite を使用
    DATABASE_URL = "sqlite:///./app.db"
    logger.warning("DATABASE_URL が環境変数に設定されていません。ローカル開発用に SQLite を使用します。")
    logger.debug(f"フォールバックの DATABASE_URL: {DATABASE_URL}")

# ------------------------------------------------------------
# 2. SQLAlchemy エンジンを作成
#    - SQLite の場合は connect_args={"check_same_thread": False} を付与
# ------------------------------------------------------------
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite はマルチスレッドで使うとエラーになる場合があるのでチェックをオフにする
    engine_kwargs["connect_args"] = {"check_same_thread": False}

try:
    engine = create_engine(DATABASE_URL, echo=False, **engine_kwargs)
except SQLAlchemyError as e:
    logger.error(f"SQLAlchemy エンジンの作成に失敗しました。URL={DATABASE_URL} エラー: {e}")
    sys.exit(1)

# ------------------------------------------------------------
# 3. ORM 用のベースクラスとセッション設定
# ------------------------------------------------------------
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ------------------------------------------------------------
# 4. テーブル定義（UserDocMapping）
# ------------------------------------------------------------
class UserDocMapping(Base):
    __tablename__ = 'user_doc_mappings'

    # LINE User ID を主キーとして使用
    user_id = Column(String, primary_key=True, index=True)
    # GoogleドキュメントIDを保存
    doc_id = Column(String, nullable=False)

    def __repr__(self):
        return f"<UserDocMapping(user_id='{self.user_id}', doc_id='{self.doc_id}')>"

# ------------------------------------------------------------
# 5. テーブル作成関数
#    - create_tables() を呼ぶと、まだテーブルが存在しなければ作成する
#    - エラー発生時はプロセスを終了
# ------------------------------------------------------------
def create_tables():
    try:
        Base.metadata.create_all(engine)
        logger.info("Database tables created successfully (or already exist).")
    except SQLAlchemyError as e:
        logger.error(f"Error creating database tables: {e}")
        sys.exit(1)
