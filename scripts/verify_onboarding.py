"""온보딩(FR-01/02/03) 흐름 검증: 로그인 upsert → 그룹 생성 → 합류 → 6명 cap.

MockAuth 사용(토스 호출 없음) + 실제 Supabase store.
실행: python scripts/verify_onboarding.py   (.env에 SUPABASE_URL/KEY 필요)
"""
from __future__ import annotations

import os
import sys
from datetime import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.store import get_store, SupabaseStore
from app.auth import MockAuth


def main() -> int:
    if not (settings.supabase_url and settings.supabase_key):
        print("✗ SUPABASE_URL/KEY 없음"); return 1

    auth = MockAuth()
    store = get_store()
    assert isinstance(store, SupabaseStore), "Supabase store가 아님(.env 확인)"
    sb = store.sb
    toss_ids, group_id = [], None
    try:
        print("[1] 로그인 → 사용자 upsert (7명)")
        users = []
        for i in range(7):
            a = auth.login(f"onb{i}")
            m = store.upsert_user(a.toss_user_id, a.name, a.birth_date)
            users.append(m); toss_ids.append(a.toss_user_id)
        print(f"   ✓ {len(users)}명 (예: {users[0].name} {users[0].birth_date})")

        print("[2] 그룹 생성 + 방장 자동 합류")
        g = store.create_group("[verify] 온보딩", users[0].id, "ONB-VERIFY", time(9, 0))
        group_id = g.id
        print(f"   ✓ group_id={group_id}, invite=ONB-VERIFY, members={len(g.members)}")

        print("[3] 초대코드로 합류 (총 6명까지)")
        for m in users[1:6]:
            store.add_member(g.id, m.id)
        g6 = store.get_group_by_invite_code("ONB-VERIFY")
        assert len(g6.members) == 6, f"6명이어야 하는데 {len(g6.members)}"
        print(f"   ✓ 현재 {len(g6.members)}명")

        print("[4] 7번째 합류 시도 → 6명 cap 트리거가 막아야 함")
        blocked = False
        try:
            store.add_member(g.id, users[6].id)
        except Exception:
            blocked = True
        assert blocked, "7번째가 막히지 않음(트리거 미동작)"
        print("   ✓ 7번째 차단됨 (enforce_group_size 동작)")

        print("\n✅ 온보딩 전체 정상 (upsert/그룹생성/합류/6명 cap)")
        return 0
    finally:
        if group_id:
            sb.table("groups").delete().eq("id", group_id).execute()
        for tid in toss_ids:
            sb.table("users").delete().eq("toss_user_id", tid).execute()


if __name__ == "__main__":
    sys.exit(main())
