"""운세 생성 오케스트레이션: 멤버 -> 룰기반 베이스 -> LLM -> 후처리 -> GroupFortune.

그룹·날짜당 LLM 1회 호출(요구사항). 동일 날짜 캐시는 store.py에서 관리.
"""
from __future__ import annotations

from datetime import date

from .config import settings
from .models import Member, GroupFortune, PersonalFortune, Chemistry
from .saju.elements import day_pillar, personal_element, ELEMENT_HANJA
from .saju.relations import personal_base_text, select_pairs
from .llm.prompts import build_user_prompt, WEEKDAY_KO
from .llm.postprocess import sanitize_line


def _member_base(members: list[Member], target: date):
    """각 멤버의 개인 오행 + 그날 관계 베이스 라벨 산출."""
    day_el = day_pillar(target).element
    out = []
    for m in members:
        my_el = personal_element(m.birth_date)
        out.append({
            "id": m.id,
            "name": m.name,
            "element": my_el,
            "base_text": personal_base_text(day_el, my_el),
        })
    return day_el, out


def build_prompt(members: list[Member], target: date) -> tuple[str, dict]:
    """LLM user prompt + 베이스 메타(후처리에 필요한 정보) 반환."""
    if len(members) > settings.max_group_size:
        raise ValueError(f"그룹 최대 인원({settings.max_group_size})을 초과했습니다: {len(members)}명")

    day_el, bases = _member_base(members, target)
    pairs = select_pairs(bases, settings.max_pairs)

    member_lines = [
        f"- id: {b['id']}, 이름: {b['name']}, 오늘의 개인 오행 결과: {b['base_text']}"
        for b in bases
    ]
    pair_lines = [
        f"- pair_id: {p.a_id}__{p.b_id}, A: {p.a_name}({ELEMENT_HANJA[p.a_element]}), "
        f"B: {p.b_name}({ELEMENT_HANJA[p.b_element]}), 두 사람의 오행 관계: {p.relation_phrase}"
        for p in pairs
    ]

    date_str = f"{target.year}년 {target.month}월 {target.day}일"
    weekday = WEEKDAY_KO[target.weekday()]
    prompt = build_user_prompt(date_str, weekday, ELEMENT_HANJA[day_el], member_lines, pair_lines)

    meta = {
        "day_element": ELEMENT_HANJA[day_el],
        "bases": {b["id"]: b["base_text"] for b in bases},
        "pairs": {f"{p.a_id}__{p.b_id}": (p.a_id, p.b_id) for p in pairs},
    }
    return prompt, meta


def assemble(group_id: str, target: date, raw: dict, meta: dict) -> GroupFortune:
    """LLM 원시 출력 + 베이스 메타 -> 검증/후처리된 GroupFortune."""
    pf = []
    for item in raw.get("personal_fortunes", []):
        line, _ = sanitize_line(item["line"])
        mid = item["member_id"]
        pf.append(PersonalFortune(
            member_id=mid,
            line=line,
            score=max(1, min(5, int(item["score"]))),
            base_element=meta["bases"].get(mid, ""),
        ))

    chem = []
    for item in raw.get("chemistry", []):
        pid = item["pair_id"]
        if pid not in meta["pairs"]:
            continue  # 입력에 없던 임의 페어는 폐기
        a_id, b_id = meta["pairs"][pid]
        line, _ = sanitize_line(item["line"])
        kind = item.get("type", "good")
        chem.append(Chemistry(pair_id=pid, a_id=a_id, b_id=b_id,
                              type=kind if kind in ("good", "caution") else "good",
                              line=line))

    gc, _ = sanitize_line(raw.get("group_comment", ""))
    return GroupFortune(
        group_id=group_id, date=target, day_element=meta["day_element"],
        group_comment=gc, personal_fortunes=pf, chemistry=chem,
    )


def generate(group_id: str, members: list[Member], target: date, client=None) -> GroupFortune:
    """엔드투엔드 단발 생성(캐시 미사용 경로)."""
    from .llm.client import get_client
    client = client or get_client()
    prompt, meta = build_prompt(members, target)
    raw = client.generate(prompt)
    return assemble(group_id, target, raw, meta)
