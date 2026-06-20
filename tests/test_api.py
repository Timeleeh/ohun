"""프론트(화면)용 API 레이어 테스트: /view 조인(이름·오행) + /users/{id}/groups + 미생성 404.

httpx(TestClient) 의존을 피하기 위해 엔드포인트 함수를 직접 호출한다.
모듈 전역 store를 격리된 InMemoryStore로 교체해 Supabase/.env 영향 없이 검증.
"""
from datetime import date

import pytest
from fastapi import HTTPException

import app.main as main_mod
from app.store import InMemoryStore
from app import fortune
from app.llm.client import MockClient


def _seed():
    st = InMemoryStore()
    st.upsert_user("u_jihoon", "지훈", date(1993, 5, 1))
    st.upsert_user("u_minjun", "민준", date(1990, 11, 23))
    st.upsert_user("u_seoyeon", "서연", date(1996, 2, 14))
    g = st.create_group("우리팀", "u_jihoon", "ABCD1234")
    st.add_member(g.id, "u_minjun")
    st.add_member(g.id, "u_seoyeon")
    gf = fortune.generate(g.id, st.get_group(g.id).members,
                          date(2026, 6, 19), client=MockClient())
    st.save_fortune(gf)
    return st, g


def test_view_joins_names_and_elements():
    st, g = _seed()
    main_mod.store = st
    v = main_mod.get_fortune_view(g.id, date(2026, 6, 19))
    assert v.group_name == "우리팀"
    assert v.date_label.endswith("(금)")          # 2026-06-19 = 금요일
    names = {m.name for m in v.members}
    assert {"지훈", "민준", "서연"} <= names         # member_id가 이름으로 조인됨
    assert all(m.element in ("목", "화", "토", "금", "수") for m in v.members)
    assert v.chemistry, "케미가 비어있으면 안 됨"
    # 케미 a/b는 멤버 id 집합에 포함
    ids = {m.id for m in v.members}
    assert all(c.a in ids and c.b in ids for c in v.chemistry)


def test_my_groups_lists_user_groups():
    st, g = _seed()
    main_mod.store = st
    rows = main_mod.my_groups("u_jihoon")
    assert any(r.id == g.id and r.name == "우리팀" for r in rows)
    # 가입 안 한 사용자는 빈 목록
    assert main_mod.my_groups("nobody") == []


def test_view_404_before_batch():
    st = InMemoryStore()
    st.upsert_user("u1", "A", date(1990, 1, 1))
    g = st.create_group("빈그룹", "u1", "ZZZZ9999")
    main_mod.store = st
    with pytest.raises(HTTPException) as ei:
        main_mod.get_fortune_view(g.id, date(2026, 6, 19))
    assert ei.value.status_code == 404
