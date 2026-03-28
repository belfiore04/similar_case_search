from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import LegalCase, SearchHistory, User
from schemas import SearchRequest, SearchResult, SimilarCase, CaseOut, ReportRequest, CaseReport
from auth import get_current_user
from services.embedding import search_similar
from services.report import generate_comparison_report

router = APIRouter(prefix="/api/search", tags=["类案检索"])


@router.post("/similar", response_model=SearchResult)
def search_similar_cases(
    req: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 构建查询文本
    query_text = f"【案件名称】{req.case_name}\n【案情描述】{req.case_description}"

    # 向量检索
    results = search_similar(query_text, top_k=req.top_k or 5)

    if not results:
        # 保存搜索记录
        history = SearchHistory(
            user_id=current_user.id,
            case_name=req.case_name,
            case_description=req.case_description,
            time_range_start=req.time_range_start,
            time_range_end=req.time_range_end,
            result_count=0,
        )
        db.add(history)
        db.commit()
        return SearchResult(query_summary=req.case_description[:100], similar_cases=[], total_found=0)

    # 获取案例详情
    case_ids = [r[0] for r in results]
    cases = db.query(LegalCase).filter(LegalCase.id.in_(case_ids)).all()
    case_map = {c.id: c for c in cases}

    # 时间过滤
    similar_cases = []
    for case_id, score in results:
        case = case_map.get(case_id)
        if not case:
            continue
        # 时间范围过滤
        if req.time_range_start and case.judge_date and case.judge_date < req.time_range_start:
            continue
        if req.time_range_end and case.judge_date and case.judge_date > req.time_range_end:
            continue
        similar_cases.append(SimilarCase(
            case=CaseOut.model_validate(case),
            similarity_score=round(score, 4),
            match_highlights=case.keywords,
        ))

    # 保存搜索记录
    history = SearchHistory(
        user_id=current_user.id,
        case_name=req.case_name,
        case_description=req.case_description,
        time_range_start=req.time_range_start,
        time_range_end=req.time_range_end,
        result_count=len(similar_cases),
    )
    db.add(history)
    db.commit()

    return SearchResult(
        query_summary=req.case_description[:100],
        similar_cases=similar_cases,
        total_found=len(similar_cases),
    )


@router.post("/report")
def generate_report(
    req: ReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cases = db.query(LegalCase).filter(LegalCase.id.in_(req.similar_case_ids)).all()
    if not cases:
        raise HTTPException(status_code=404, detail="未找到指定案例")

    report = generate_comparison_report(
        user_case_name=req.case_name,
        user_case_description=req.case_description,
        similar_cases=cases,
    )
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
