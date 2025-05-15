import os
import sys
from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# RenderのPostgreSQLアドオンによって設定される環境変数からデータベースURLを取得
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set.", file=sys.stderr)
    # RenderではDATABASE_URLがないとそもそもDBが使えないので、ここでは終了せず、
    # main.py側でDBへのアクセス時にエラーハンドリングすることも可能ですが、
    # 初期設定エラーとしてここで終了させるのも一つの方法です。
    # デプロイが成功しなくなるため、設定ミスに気づきやすくなります。
    sys.exit(1)


# SQLAlchemy設定
# echo=True はSQLの実行ログを表示します（デバッグ用）
engine = create_engine(DATABASE_URL, echo=False) # 本番環境ではFalse推奨

# モデルを定義するためのベースクラス
Base = declarative_base()

# ユーザーIDとGoogleドキュメントIDの紐付けを保存するモデル
class UserDocMapping(Base):
    __tablename__ = 'user_doc_mappings'

    # LINE User ID を主キーとして使用
    user_id = Column(String, primary_key=True)
    # GoogleドキュメントIDを保存
    doc_id = Column(String, nullable=False)

    def __repr__(self):
        return f"<UserDocMapping(user_id='{self.user_id}', doc_id='{self.doc_id}')>"

# データベーステーブルを作成する関数
def create_tables():
    try:
        Base.metadata.create_all(engine)
        print("Database tables created successfully (or already exist).", file=sys.stderr)
    except SQLAlchemyError as e:
        print(f"Error creating database tables: {e}", file=sys.stderr)
        # テーブル作成に失敗した場合は、アプリケーションを続行できない可能性が高い
        sys.exit(1)


# データベースセッションを作成するためのファクトリ関数
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# セッションの依存性注入（FastAPIで使用する場合など）
# 簡単のため、main.pyで手動でセッションを作成・クローズします。
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()
