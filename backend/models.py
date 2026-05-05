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
    case_number = Column(String(100), index=True)  # 案号
    case_type = Column(String(50), index=True)  # 民事案件/刑事案件/行政案件
    cause_of_action = Column(String(200))  # 案由
    court = Column(String(100))  # 审理法院
    region = Column(String(100))  # 所属地区
    procedure = Column(String(50))  # 审理程序（一审/二审/再审）
    judge_date = Column(String(50))  # 裁判日期
    publish_date = Column(String(50))  # 公开日期
    parties = Column(Text)  # 当事人（原始字符串，分号分隔）
    plaintiff = Column(String(200))  # 原告（从当事人解析）
    defendant = Column(String(200))  # 被告（从当事人解析）
    case_summary = Column(Text)  # 基本案情
    dispute_focus = Column(Text)  # 争议焦点
    judgment_result = Column(Text)  # 裁判结果
    judgment_reason = Column(Text)  # 裁判理由
    judgment_points = Column(Text)  # 裁判要点
    related_laws = Column(Text)  # 相关法条/法律依据
    keywords = Column(String(500))  # 关键词
    full_text = Column(Text)  # 全文
    source_url = Column(String(500))  # 原始链接
    created_at = Column(DateTime, server_default=func.now())

    @staticmethod
    def _compact_text(text, max_len=1000):
        if not text:
            return None
        compacted = " ".join(str(text).split())
        if len(compacted) <= max_len:
            return compacted
        return compacted[:max_len] + "..."

    @staticmethod
    def _slice_between(text, start_markers, end_markers, max_len=1000):
        if not text:
            return None
        start = -1
        for marker in start_markers:
            start = text.find(marker)
            if start >= 0:
                break
        if start < 0:
            return None
        end_candidates = [text.find(marker, start + 1) for marker in end_markers]
        end_candidates = [idx for idx in end_candidates if idx > start]
        end = min(end_candidates) if end_candidates else start + max_len
        return LegalCase._compact_text(text[start:end], max_len=max_len)

    @property
    def full_text_preview(self):
        return self._compact_text(self.full_text, max_len=1200)

    @property
    def case_summary_display(self):
        return self.case_summary or self.full_text_preview

    @property
    def judgment_reason_display(self):
        return self.judgment_reason or self._slice_between(
            self.full_text,
            ["本院认为", "本院经审理认为"],
            ["综上", "判决如下", "裁定如下", "依照"],
            max_len=1200,
        )

    @property
    def judgment_result_display(self):
        return self.judgment_result or self._slice_between(
            self.full_text,
            ["判决如下", "裁定如下"],
            ["如不服本判决", "本判决为终审判决", "审判长", "审 判 长"],
            max_len=800,
        )


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
