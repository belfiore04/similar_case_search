import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base, SessionLocal
from models import User, LegalCase
from auth import get_password_hash
from routers.auth_router import router as auth_router
from routers.case_router import router as case_router
from routers.search_router import router as search_router
from services.embedding import load_faiss_index, rebuild_index
import json

app = FastAPI(title="类案检索系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(case_router)
app.include_router(search_router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 初始化默认用户
        if not db.query(User).first():
            admin = User(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                full_name="管理员",
                role="admin",
            )
            demo = User(
                username="demo",
                hashed_password=get_password_hash("demo123"),
                full_name="演示用户",
                role="user",
            )
            db.add_all([admin, demo])
            db.commit()

        # 加载mock案例数据
        if db.query(LegalCase).count() == 0:
            mock_path = os.path.join(os.path.dirname(__file__), "mock_data", "cases.json")
            with open(mock_path, "r", encoding="utf-8") as f:
                cases_data = json.load(f)
            for data in cases_data:
                case = LegalCase(**data)
                db.add(case)
            db.commit()
            print(f"已加载 {len(cases_data)} 条mock案例数据")

        # 构建/加载 FAISS 索引
        load_faiss_index()
        from services.embedding import _faiss_index
        if _faiss_index.ntotal == 0:
            cases = db.query(LegalCase).all()
            if cases:
                rebuild_index(cases)
                print(f"已构建 FAISS 索引，共 {len(cases)} 条")
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "类案检索系统运行中"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
