from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# 支持通过环境变量切换数据库：PostgreSQL（生产）或 SQLite（开发）
# PostgreSQL 示例: postgresql://user:password@host:5432/similar_case_search
# SQLite 示例:    sqlite:///app.db
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    # PostgreSQL 模式：启用连接池
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,
        max_overflow=30,
        pool_pre_ping=True,
    )
else:
    # SQLite 开发模式（向后兼容）
    DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
