from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# === Auth ===
class UserRegister(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    role: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut


# === Cases ===
class CaseCreate(BaseModel):
    case_name: str
    case_number: Optional[str] = None
    case_type: Optional[str] = None
    cause_of_action: Optional[str] = None
    court: Optional[str] = None
    judge_date: Optional[str] = None
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    case_summary: Optional[str] = None
    dispute_focus: Optional[str] = None
    judgment_result: Optional[str] = None
    judgment_reason: Optional[str] = None
    judgment_points: Optional[str] = None
    related_laws: Optional[str] = None
    keywords: Optional[str] = None
    full_text: Optional[str] = None


class CaseOut(BaseModel):
    id: int
    case_name: str
    case_number: Optional[str]
    case_type: Optional[str]
    cause_of_action: Optional[str]
    court: Optional[str]
    judge_date: Optional[str]
    plaintiff: Optional[str]
    defendant: Optional[str]
    case_summary: Optional[str]
    dispute_focus: Optional[str]
    judgment_result: Optional[str]
    judgment_reason: Optional[str]
    judgment_points: Optional[str]
    related_laws: Optional[str]
    keywords: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# === Search ===
class SearchRequest(BaseModel):
    case_name: str
    case_description: str
    time_range_start: Optional[str] = None
    time_range_end: Optional[str] = None
    top_k: Optional[int] = 5


class SimilarCase(BaseModel):
    case: CaseOut
    similarity_score: float
    match_highlights: Optional[str] = None


class SearchResult(BaseModel):
    query_summary: str
    similar_cases: List[SimilarCase]
    total_found: int


# === Report ===
class ReportRequest(BaseModel):
    case_name: str
    case_description: str
    similar_case_ids: List[int]


class ComparisonItem(BaseModel):
    aspect: str  # 对比维度
    user_case: str  # 用户案情
    similar_case: str  # 类案内容
    analysis: str  # 分析


class CaseReport(BaseModel):
    title: str
    summary: str
    comparisons: List[ComparisonItem]
    legal_references: List[str]
    conclusion: str
