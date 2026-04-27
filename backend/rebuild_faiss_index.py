"""
Rebuild FAISS index from the current database.

Run:
  DASHSCOPE_API_KEY=... python rebuild_faiss_index.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal  # noqa: E402
from models import LegalCase  # noqa: E402
from services.embedding import rebuild_index  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        cases = db.query(LegalCase).order_by(LegalCase.id.asc()).all()
        rebuild_index(cases)
        print(f"Rebuilt FAISS index for {len(cases)} cases")
        print(f"Embedding mode: {'dashscope' if os.getenv('DASHSCOPE_API_KEY') else 'mock'}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
