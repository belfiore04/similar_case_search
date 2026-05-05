from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import LegalCase, SearchHistory, User
from schemas import SearchRequest, SearchResult, SimilarCase, CaseOut, ReportRequest
from auth import get_current_user
from services.embedding import search_similar_chunked
from services.query_parser import normalize_case_type, normalize_date, parse_query_filters
from services.report import generate_comparison_report

router = APIRouter(prefix="/api/search", tags=["类案检索"])

MIN_DETAIL_CHARS = 6
EXECUTION_MARKERS = ("刑罚与执行变更", "减刑", "假释", "暂予监外执行", "执行变更")
GENERIC_KEYWORDS = {"刑事", "民事", "行政", "案件", "纠纷", "犯罪", "公诉"}
CAUSE_SYNONYMS = {
    "杀人": ["杀人", "故意杀人", "故意杀人罪"],
    "故意杀人": ["杀人", "故意杀人", "故意杀人罪"],
    "盗窃": ["盗窃", "盗窃罪"],
    "诈骗": ["诈骗", "诈骗罪"],
    "抢劫": ["抢劫", "抢劫罪"],
    "强奸": ["强奸", "强奸罪"],
    "故意伤害": ["故意伤害", "故意伤害罪"],
    "危险驾驶": ["危险驾驶", "危险驾驶罪"],
    "交通肇事": ["交通肇事", "交通肇事罪"],
    "失火": ["失火", "失火罪"],
    "买卖合同": ["买卖合同", "买卖合同纠纷"],
    "劳动合同": ["劳动合同", "劳动争议", "劳动合同纠纷"],
    "民间借贷": ["民间借贷", "民间借贷纠纷"],
    "房屋租赁": ["房屋租赁", "租赁合同纠纷", "房屋租赁合同纠纷"],
    "离婚": ["离婚", "离婚纠纷", "离婚后财产纠纷"],
    "交通事故": ["交通事故", "机动车交通事故责任纠纷"],
}


def _compact(text: str) -> str:
    return "".join((text or "").split())


def _has_execution_intent(text: str) -> bool:
    return any(marker in (text or "") for marker in EXECUTION_MARKERS)


def _is_execution_case(case: LegalCase) -> bool:
    text = " ".join([
        case.case_name or "",
        case.cause_of_action or "",
        case.procedure or "",
        case.case_type or "",
    ])
    return any(marker in text for marker in EXECUTION_MARKERS)


def _keyword_hints(text: str, extracted_filters: dict = None) -> list[str]:
    raw = []
    if extracted_filters:
        raw.extend(extracted_filters.get("cause_keywords") or [])
    for keyword in CAUSE_SYNONYMS:
        if keyword in (text or ""):
            raw.append(keyword)

    hints = []
    for keyword in raw:
        keyword = str(keyword).strip()
        if not keyword or keyword in GENERIC_KEYWORDS:
            continue
        expanded = CAUSE_SYNONYMS.get(keyword, [keyword])
        for item in expanded:
            if item not in hints:
                hints.append(item)
    return hints[:10]


def _case_text_for_match(case: LegalCase) -> str:
    return " ".join([
        case.case_name or "",
        case.cause_of_action or "",
        case.keywords or "",
        case.full_text[:1200] if case.full_text else "",
    ])


def _case_matches_keywords(case: LegalCase, keyword_hints: list[str]) -> bool:
    if not keyword_hints:
        return True
    text = _case_text_for_match(case)
    return any(keyword in text for keyword in keyword_hints)


def _dedupe_key(case: LegalCase) -> tuple:
    if case.case_number:
        return ("case_number", case.case_number)
    return ("case_identity", case.case_name or "", case.court or "", case.judge_date or "")


def _validate_query_detail(text: str, keyword_hints: list[str]):
    if len(_compact(text)) < MIN_DETAIL_CHARS and not keyword_hints:
        raise HTTPException(
            status_code=400,
            detail="案情描述过短，请补充案件事实、案由或关键争议点后再检索。",
        )


@router.post("/similar", response_model=SearchResult)
def search_similar_cases(
    req: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        extracted_filters = parse_query_filters(req.case_description)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    time_range_start = req.time_range_start or extracted_filters.get("time_range_start")
    time_range_end = req.time_range_end or extracted_filters.get("time_range_end")
    case_type = normalize_case_type(req.case_type) or extracted_filters.get("case_type")
    keyword_hints = _keyword_hints(req.case_description, extracted_filters)
    _validate_query_detail(req.case_description, keyword_hints)
    allow_execution_cases = _has_execution_intent(req.case_description)

    # 构建查询文本
    query_text = f"【案件名称】{req.case_name}\n【案情描述】{req.case_description}"

    # 使用查询切分多路检索（自动退化：短查询走单向量，长查询走切分合并）
    top_k = req.top_k or 5
    candidate_k = max(top_k * 10, 50)
    try:
        results = search_similar_chunked(query_text, top_k=candidate_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not results:
        # 保存搜索记录
        history = SearchHistory(
            user_id=current_user.id,
            case_name=req.case_name,
            case_description=req.case_description,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            result_count=0,
        )
        db.add(history)
        db.commit()
        return SearchResult(
            query_summary=req.case_description[:100],
            similar_cases=[],
            total_found=0,
            extracted_filters=extracted_filters,
        )

    # 获取案例详情
    case_ids = [r[0] for r in results]
    cases = db.query(LegalCase).filter(LegalCase.id.in_(case_ids)).all()
    case_map = {c.id: c for c in cases}

    # 元数据后置过滤：DeepSeek 提取的案件类型 / 裁判日期范围
    similar_cases = []
    seen_keys = set()
    for case_id, score in results:
        case = case_map.get(case_id)
        if not case:
            continue

        dedupe_key = _dedupe_key(case)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        if case_type and normalize_case_type(case.case_type) != case_type:
            continue

        if not allow_execution_cases and _is_execution_case(case):
            continue

        if not _case_matches_keywords(case, keyword_hints):
            continue

        judge_date = normalize_date(case.judge_date)
        if time_range_start and (not judge_date or judge_date < time_range_start):
            continue
        if time_range_end and (not judge_date or judge_date > time_range_end):
            continue

        similar_cases.append(SimilarCase(
            case=CaseOut.model_validate(case),
            similarity_score=round(min(100.0, score + (4.0 if keyword_hints else 0.0)), 2),
            match_highlights=case.keywords,
        ))

        if len(similar_cases) >= top_k:
            break

    # 保存搜索记录
    history = SearchHistory(
        user_id=current_user.id,
        case_name=req.case_name,
        case_description=req.case_description,
        time_range_start=time_range_start,
        time_range_end=time_range_end,
        result_count=len(similar_cases),
    )
    db.add(history)
    db.commit()

    return SearchResult(
        query_summary=req.case_description[:100],
        similar_cases=similar_cases,
        total_found=len(similar_cases),
        extracted_filters=extracted_filters,
    )


@router.post("/report")
def generate_report(
    req: ReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    keyword_hints = _keyword_hints(req.case_description)
    _validate_query_detail(req.case_description, keyword_hints)
    allow_execution_cases = _has_execution_intent(req.case_description)

    cases = db.query(LegalCase).filter(LegalCase.id.in_(req.similar_case_ids)).all()
    if not cases:
        raise HTTPException(status_code=404, detail="未找到指定案例")

    if not allow_execution_cases:
        non_execution_cases = [case for case in cases if not _is_execution_case(case)]
        if not non_execution_cases:
            raise HTTPException(
                status_code=422,
                detail="检索结果主要是刑罚与执行变更类案件，和当前案情不匹配，无法生成有效类案报告。",
            )
        cases = non_execution_cases

    if keyword_hints:
        matched_cases = [case for case in cases if _case_matches_keywords(case, keyword_hints)]
        if not matched_cases:
            raise HTTPException(
                status_code=422,
                detail="当前候选案例与案由关键词不匹配，无法生成有效类案报告。请补充案情或扩大数据集后重试。",
            )
        cases = matched_cases

    try:
        report = generate_comparison_report(
            user_case_name=req.case_name,
            user_case_description=req.case_description,
            similar_cases=cases,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return report


@router.get("/history")
def get_search_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.id)
        .order_by(SearchHistory.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id,
            "case_name": r.case_name,
            "case_description": r.case_description[:80] if r.case_description else "",
            "result_count": r.result_count,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in records
    ]
