"""FastAPI 진입점. 운세는 배치로 미리 생성되며, 앱은 캐시를 읽어 보여준다(실시간 생성 X)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone, timedelta

import html

import base64
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import settings
from .models import (GenerateRequest, GroupFortune, GroupFortuneView,
                     MemberView, ChemistryView, GroupSummary)
from .store import get_store
from .scheduler import BatchConfig, tick
from .auth import get_auth
from .saju.elements import personal_element, ELEMENT_HANJA
from .llm.prompts import WEEKDAY_KO
from .share import render_card_png, SAMPLE_CARD
from . import fortune

_HANJA_KO = {v: k for k, v in ELEMENT_HANJA.items()}  # 木→목 ...

KST = timezone(timedelta(hours=9))
app = FastAPI(title="케미사주 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
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


@app.post("/auth/toss/disconnect")
async def toss_disconnect(request: Request):
    """토스 연결 끊기 콜백. 사용자가 토스앱에서 서비스 연결 해제 시 호출됨."""
    auth_header = request.headers.get("Authorization", "")
    expected = "Basic " + base64.b64encode(
        f"chemisaju:{settings.toss_disconnect_secret}".encode()
    ).decode()
    if auth_header != expected:
        raise HTTPException(401, "Unauthorized")
    return {"ok": True}


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
    """앱 화면용(원시): 배치로 미리 생성·캐시된 그룹 운세를 읽는다."""
    target = d or _today_kst()
    gf = store.get_fortune(group_id, target)
    if gf is None:
        raise HTTPException(404, "아직 생성되지 않았습니다(배치 대기 또는 비활성 그룹).")
    return gf


def _date_label(d: date) -> str:
    return f"{d.year}년 {d.month}월 {d.day}일 ({WEEKDAY_KO[d.weekday()][0]})"


def _compose_view(group_id: str, target: date) -> GroupFortuneView | None:
    """캐시된 운세 + 그룹 멤버(이름·오행)를 조인해 화면용 뷰로 합성. 없으면 None."""
    gf = store.get_fortune(group_id, target)
    if gf is None:
        return None
    group = store.get_group(group_id)
    by_id = {m.id: m for m in (group.members if group else [])}

    def _element_of(p) -> str:
        # 오행색은 운세 행의 base 라벨(예: "金 기운 …")을 단일 출처로 사용 → base와 항상 일치.
        if p.base_element and p.base_element[0] in _HANJA_KO:
            return _HANJA_KO[p.base_element[0]]
        m = by_id.get(p.member_id)
        return personal_element(m.birth_date) if m else ""

    members = [
        MemberView(
            id=p.member_id,
            name=(by_id[p.member_id].name if p.member_id in by_id else p.member_id),
            element=_element_of(p),
            base=p.base_element,
            score=p.score,
            line=p.line,
        )
        for p in gf.personal_fortunes
    ]
    chemistry = [
        ChemistryView(a=c.a_id, b=c.b_id, type=c.type, line=c.line)
        for c in gf.chemistry
    ]
    return GroupFortuneView(
        group_id=group_id,
        group_name=(group.name if group else group_id),
        date=target,
        date_label=_date_label(target),
        day_element=gf.day_element,
        group_comment=gf.group_comment,
        members=members,
        chemistry=chemistry,
    )


@app.get("/groups/{group_id}/view", response_model=GroupFortuneView)
def get_fortune_view(group_id: str, d: date | None = None):
    """프론트(화면) 전용: 캐시된 운세 + 그룹 멤버(이름·오행)를 조인해 바로 그릴 수 있는 형태로 반환."""
    view = _compose_view(group_id, d or _today_kst())
    if view is None:
        raise HTTPException(404, "아직 생성되지 않았습니다(배치 대기 또는 비활성 그룹).")
    return view


@app.get("/users/{user_id}/groups", response_model=list[GroupSummary])
def my_groups(user_id: str):
    """그룹 전환 스위처용: 사용자가 속한 그룹 목록."""
    return [
        GroupSummary(id=g.id, name=g.name, gen_time=g.gen_time.strftime("%H:%M"))
        for g in store.list_groups_for_user(user_id)
    ]


# ===== 카카오 공유 (SSR 카드 + OG 랜딩) =====
def _card_from_view(v: GroupFortuneView) -> dict:
    return {
        "group_name": v.group_name,
        "date_label": v.date_label,
        "day_element": v.day_element,
        "group_comment": v.group_comment,
        "members": [{"name": m.name, "element": m.element, "score": m.score} for m in v.members],
    }


@app.get("/share/config")
def share_config():
    """프론트가 카카오 키/앱URL을 코드에 박지 않고 받아가도록(키는 .env에서만 관리)."""
    return {"kakao_js_key": settings.kakao_js_key, "app_url": settings.app_url}


@app.get("/share/{group_id}/card.png")
def share_card(group_id: str, d: date | None = None):
    """카카오 피드 imageUrl 용 공유 카드(PNG, 800x400). 운세 없으면 샘플 카드로 폴백."""
    view = _compose_view(group_id, d or _today_kst())
    card = _card_from_view(view) if view else SAMPLE_CARD
    png = render_card_png(card)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=300"})


@app.get("/share/{group_id}", response_class=HTMLResponse)
def share_landing(group_id: str, request: Request, d: date | None = None):
    """공유 링크가 향하는 OG 랜딩(카카오/단톡방 미리보기 + '앱에서 열기')."""
    view = _compose_view(group_id, d or _today_kst())
    card = _card_from_view(view) if view else SAMPLE_CARD
    base = str(request.base_url).rstrip("/")
    img = f"{base}/share/{group_id}/card.png" + (f"?d={d.isoformat()}" if d else "")
    page = f"{base}/share/{group_id}"
    app_link = settings.app_url + (("&" if "?" in settings.app_url else "?") + f"group={group_id}")
    title = f"{card['group_name']} · 오늘의 그룹 케미"
    desc = card.get("group_comment") or card.get("date_label", "")
    e = html.escape
    body = f"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{e(title)}</title>
<meta property="og:type" content="website"/>
<meta property="og:title" content="{e(title)}"/>
<meta property="og:description" content="{e(desc)}"/>
<meta property="og:image" content="{e(img)}"/>
<meta property="og:url" content="{e(page)}"/>
<meta name="twitter:card" content="summary_large_image"/>
<style>
  body{{margin:0;background:#0d0e12;color:#f4f5f7;font-family:-apple-system,"Malgun Gothic",sans-serif;
    display:flex;flex-direction:column;align-items:center;gap:18px;padding:28px;text-align:center}}
  img{{width:min(440px,92vw);border-radius:18px;border:1px solid #2a2e38}}
  h1{{font-size:19px;margin:6px 0 0}}
  p{{color:#8d93a1;font-size:14px;margin:0 18px;line-height:1.5}}
  a.btn{{margin-top:6px;background:#c6ff3d;color:#0d0e12;font-weight:800;text-decoration:none;
    padding:15px 26px;border-radius:16px;font-size:16px}}
  .brand{{color:#c6ff3d;font-weight:800;font-size:13px;letter-spacing:.3px}}
</style></head><body>
<div class="brand">케미사주</div>
<img src="{e(img)}" alt="{e(title)} 공유 카드"/>
<h1>{e(card['group_name'])}</h1>
<p>{e(desc)}</p>
<a class="btn" href="{e(app_link)}">앱에서 우리 그룹 운세 보기 →</a>
</body></html>"""
    return HTMLResponse(body)


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
