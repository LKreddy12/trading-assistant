from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}
