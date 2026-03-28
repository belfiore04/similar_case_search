from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from models import LegalCase, User
from schemas import CaseCreate, CaseOut
from auth import get_current_user
from services.embedding import add_to_index, _build_case_text

router = APIRouter(prefix="/api/cases", tags=["案例管理"])


@router.get("", response_model=List[CaseOut])
def list_cases(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    case_type: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(LegalCase)
    if case_type:
        query = query.filter(LegalCase.case_type == case_type)
    if keyword:
        query = query.filter(
            LegalCase.case_name.contains(keyword)
            | LegalCase.keywords.contains(keyword)
            | LegalCase.case_summary.contains(keyword)
        )
    cases = query.order_by(LegalCase.id.desc()).offset((page - 1) * size).limit(size).all()
    return cases


@router.get("/count")
def count_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(LegalCase).count()
    return {"total": total}


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = db.query(LegalCase).filter(LegalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    return case


@router.post("", response_model=CaseOut)
def create_case(
    data: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = LegalCase(**data.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    # 添加到向量索引
    text = _build_case_text(case)
    add_to_index(case.id, text)
    return case


@router.put("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    data: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = db.query(LegalCase).filter(LegalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    for key, value in data.model_dump().items():
        setattr(case, key, value)
    db.commit()
    db.refresh(case)
    return case


@router.delete("/{case_id}")
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = db.query(LegalCase).filter(LegalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    db.delete(case)
    db.commit()
    return {"message": "删除成功"}
