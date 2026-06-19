"""FastAPI 진입점. 운세는 배치로 미리 생성되며, 앱은 캐시를 읽어 보여준다(실시간 생성 X)."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException

from .config import settings
from .models import GenerateRequest, GroupFortune
from .store import store, Group
from .scheduler import BatchConfig, tick
from . import fortune

KST = timezone(timedelta(hours=9))
app = FastAPI(title="오행운 API", version="0.1.0")
_cfg = BatchConfig()


def _today_kst() -> date:
    return datetime.now(KST).date()


@app.get("/health")
def health():
    return {"ok": True, "model": settings.model, "max_group_size": settings.max_group_size}


@app.get("/groups/{group_id}/fortune", response_model=GroupFortune)
def get_fortune(group_id: str, d: date | None = None):
    """앱 화면용: 배치로 미리 생성·캐시된 그룹 운세를 읽는다."""
    target = d or _today_kst()
    gf = store.get_fortune(group_id, target)
    if gf is None:
        raise HTTPException(404, "아직 생성되지 않았습니다(배치 대기 또는 비활성 그룹).")
    return gf


@app.post("/admin/generate", response_model=GroupFortune)
def admin_generate(req: GenerateRequest):
    """관리/테스트용 단발 생성. 캐시에 저장 후 반환."""
    target = req.target_date or _today_kst()
    cached = store.get_fortune(req.group_id, target)
    if cached:
        return cached
    if len(req.members) > settings.max_group_size:
        raise HTTPException(400, f"그룹 최대 인원 {settings.max_group_size}명 초과")
    gf = fortune.generate(req.group_id, req.members, target)
    store.save_fortune(gf)
    return gf


@app.post("/admin/run-batch")
async def admin_run_batch():
    """관리/테스트용: 지금 이 분에 due 인 그룹 배치를 즉시 1회 실행."""
    return await tick(store, _cfg, datetime.now(KST))
