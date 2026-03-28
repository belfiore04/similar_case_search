from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default="user")  # user / admin
    created_at = Column(DateTime, server_default=func.now())


class LegalCase(Base):
    __tablename__ = "legal_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_name = Column(String(200), nullable=False)
    case_number = Column(String(100))  # 案号
    case_type = Column(String(50))  # 民事/刑事/行政
    cause_of_action = Column(String(100))  # 案由
    court = Column(String(100))  # 审理法院
    judge_date = Column(String(50))  # 裁判日期
    plaintiff = Column(String(200))  # 原告
    defendant = Column(String(200))  # 被告
    case_summary = Column(Text)  # 基本案情
    dispute_focus = Column(Text)  # 争议焦点
    judgment_result = Column(Text)  # 裁判结果
    judgment_reason = Column(Text)  # 裁判理由
    judgment_points = Column(Text)  # 裁判要点
    related_laws = Column(Text)  # 相关法条
    keywords = Column(String(500))  # 关键词
    full_text = Column(Text)  # 全文
    created_at = Column(DateTime, server_default=func.now())


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    case_name = Column(String(200))
    case_description = Column(Text)
    time_range_start = Column(String(50))
    time_range_end = Column(String(50))
    result_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
