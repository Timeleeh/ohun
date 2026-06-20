"""FastAPI 진입점. 운세는 배치로 미리 생성되며, 앱은 캐시를 읽어 보여준다(실시간 생성 X)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import settings
from .models import GenerateRequest, GroupFortune
from .store import get_store
from .scheduler import BatchConfig, tick
from .auth import get_auth
from . import fortune

KST = timezone(timedelta(hours=9))
app = FastAPI(title="케미사주 API", version="0.1.0")
_cfg = BatchConfig()
store = get_store()  # Supabase 크리덴셜 있으면 Supabase, 없으면 인메모리
auth = get_auth()    # 토스 크리덴셜 있으면 TossAuth, 없으면 MockAuth


def _invite_code() -> str:
    return uuid.uuid4().hex[:8].upper()


# ===== 온보딩 (FR-01/02/03) =====
class LoginReq(BaseModel):
    authorization_code: str
    referrer: str | None = None


class CreateGroupReq(BaseModel):
    name: str
    owner_id: str
    gen_time: str = "08:00"  # "HH:MM"


class JoinReq(BaseModel):
    user_id: str


@app.post("/auth/login")
def login(req: LoginReq):
    """토스 로그인 → 사용자 upsert(양력 생일). user_id를 이후 그룹 생성/합류에 사용."""
    u = auth.login(req.authorization_code, req.referrer or settings.toss_referrer)
    m = store.upsert_user(u.toss_user_id, u.name, u.birth_date)
    return {"user_id": m.id, "name": m.name, "birth_date": m.birth_date.isoformat()}


@app.post("/groups")
def create_group(req: CreateGroupReq):
    """그룹 생성 + 방장 자동 합류 + 초대코드 발급."""
    hh, mm = (int(x) for x in req.gen_time.split(":"))
    try:
        g = store.create_group(req.name, req.owner_id, _invite_code(), time(hh, mm))
    except Exception as e:
        raise HTTPException(400, f"그룹 생성 실패: {e}")
    return {"group_id": g.id, "name": g.name,
            "invite_code": getattr(g, "invite_code", None),
            "gen_time": g.gen_time.strftime("%H:%M")}


@app.post("/invite/{code}/join")
def join_group(code: str, req: JoinReq):
    """초대코드로 그룹 합류 (최대 6명, DB 트리거가 강제)."""
    g = store.get_group_by_invite_code(code)
    if g is None:
        raise HTTPException(404, "유효하지 않은 초대코드")
    try:
        store.add_member(g.id, req.user_id)
    except Exception as e:
        raise HTTPException(400, f"합류 실패(인원 초과 등): {e}")
    return {"group_id": g.id, "joined": req.user_id}


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
