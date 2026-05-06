import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from models import LegalCase, User
from schemas import CaseCreate, CaseOut, CsvImportResult
from auth import get_current_user
from services.embedding import add_batch_to_index, add_to_index, rebuild_index, _build_case_text

router = APIRouter(prefix="/api/cases", tags=["案例管理"])

CSV_COLUMN_MAP = {
    "原始链接": "source_url",
    "source_url": "source_url",
    "案号": "case_number",
    "case_number": "case_number",
    "案件名称": "case_name",
    "case_name": "case_name",
    "法院": "court",
    "court": "court",
    "所属地区": "region",
    "region": "region",
    "案件类型": "case_type",
    "case_type": "case_type",
    "审理程序": "procedure",
    "procedure": "procedure",
    "裁判日期": "judge_date",
    "judge_date": "judge_date",
    "公开日期": "publish_date",
    "publish_date": "publish_date",
    "当事人": "parties",
    "parties": "parties",
    "案由": "cause_of_action",
    "cause_of_action": "cause_of_action",
    "法律依据": "related_laws",
    "related_laws": "related_laws",
    "全文": "full_text",
    "full_text": "full_text",
    "原告": "plaintiff",
    "plaintiff": "plaintiff",
    "被告": "defendant",
    "defendant": "defendant",
    "基本案情": "case_summary",
    "case_summary": "case_summary",
    "争议焦点": "dispute_focus",
    "dispute_focus": "dispute_focus",
    "裁判结果": "judgment_result",
    "judgment_result": "judgment_result",
    "裁判理由": "judgment_reason",
    "judgment_reason": "judgment_reason",
    "裁判要点": "judgment_points",
    "judgment_points": "judgment_points",
    "关键词": "keywords",
    "keywords": "keywords",
}

KEEP_CASE_TYPES = {"民事", "刑事", "行政", "民事案件", "刑事案件", "行政案件"}


def require_admin(current_user: User):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行该操作")


def rebuild_index_from_db(db: Session):
    cases = db.query(LegalCase).order_by(LegalCase.id.asc()).all()
    rebuild_index(cases)


def decode_csv_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="无法识别 CSV 编码，请使用 UTF-8 或 GBK 编码")


def normalize_case_type_for_import(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if "民事" in text:
        return "民事"
    if "刑事" in text:
        return "刑事"
    if "行政" in text:
        return "行政"
    return text or None


def should_keep_case_type(value: Optional[str]) -> bool:
    if not value:
        return True
    text = str(value).strip()
    return text in KEEP_CASE_TYPES or normalize_case_type_for_import(text) in {"民事", "刑事", "行政"}


def parse_parties(parties_str: Optional[str]) -> tuple[str, str]:
    if not parties_str:
        return "", ""
    parts = [p.strip() for p in parties_str.replace("；", ";").split(";") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def clean_value(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def row_to_case_record(row: dict) -> dict:
    record = {}
    for source_col, db_col in CSV_COLUMN_MAP.items():
        if source_col in row:
            record[db_col] = clean_value(row.get(source_col))

    if not record.get("case_name"):
        record["case_name"] = (
            record.get("case_number")
            or record.get("cause_of_action")
            or (record.get("full_text") or "")[:80]
            or "未命名案例"
        )

    record["case_type"] = normalize_case_type_for_import(record.get("case_type"))

    plaintiff, defendant = parse_parties(record.get("parties"))
    record["plaintiff"] = record.get("plaintiff") or plaintiff or None
    record["defendant"] = record.get("defendant") or defendant or None
    return record


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
    require_admin(current_user)
    case = LegalCase(**data.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    # 添加到向量索引
    text = _build_case_text(case)
    add_to_index(case.id, text)
    return case


@router.post("/import-csv", response_model=CsvImportResult)
async def import_cases_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 格式文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="CSV 文件为空")

    csv_text = decode_csv_content(content)
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 缺少表头")

    existing_numbers = {
        item[0]
        for item in db.query(LegalCase.case_number).filter(LegalCase.case_number.isnot(None)).all()
        if item[0]
    }
    total_rows = 0
    skipped = 0
    new_cases = []

    for row in reader:
        total_rows += 1
        record = row_to_case_record(row)
        if not should_keep_case_type(record.get("case_type")):
            skipped += 1
            continue

        case_number = record.get("case_number")
        if case_number and case_number in existing_numbers:
            skipped += 1
            continue

        case = LegalCase(**record)
        db.add(case)
        new_cases.append(case)
        if case_number:
            existing_numbers.add(case_number)

    if not new_cases:
        return CsvImportResult(
            imported=0,
            skipped=skipped,
            total_rows=total_rows,
            index_updated=False,
            message="没有可导入的新案例",
        )

    db.flush()
    case_ids = [case.id for case in new_cases]
    texts = [_build_case_text(case) for case in new_cases]
    db.commit()

    try:
        add_batch_to_index(case_ids, texts)
    except Exception as exc:
        return CsvImportResult(
            imported=len(new_cases),
            skipped=skipped,
            total_rows=total_rows,
            index_updated=False,
            message=f"案例已入库，但索引更新失败：{exc}",
        )

    return CsvImportResult(
        imported=len(new_cases),
        skipped=skipped,
        total_rows=total_rows,
        index_updated=True,
        message=f"已导入 {len(new_cases)} 条案例",
    )


@router.put("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    data: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    case = db.query(LegalCase).filter(LegalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    for key, value in data.model_dump().items():
        setattr(case, key, value)
    db.commit()
    db.refresh(case)
    rebuild_index_from_db(db)
    return case


@router.delete("/{case_id}")
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    case = db.query(LegalCase).filter(LegalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    db.delete(case)
    db.commit()
    rebuild_index_from_db(db)
    return {"message": "删除成功"}
