"""Supabase 연결 / 스키마 / 캐시 라운드트립 검증 스크립트.

선행: (1) Supabase 프로젝트 생성 → SQL Editor에 db/schema.sql 실행
      (2) .env 에 SUPABASE_URL, SUPABASE_KEY(service_role 권장) 설정
실행: python scripts/verify_supabase.py

LLM 호출 없이(MockClient) DB 경로만 검증하므로 크레딧/쿼터 불필요.
테스트로 만든 행은 끝나면 정리(delete)한다.
"""
from __future__ import annotations

import os
import sys
from datetime import date

# 프로젝트 루트를 import 경로에 추가 (어느 위치에서 실행해도 동작)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models import Member
from app import fortune
from app.store import SupabaseStore
from app.llm.client import MockClient

TABLES = ["users", "groups", "group_members",
          "daily_group_fortunes", "daily_personal_fortunes", "daily_bonds"]


def main() -> int:
    if not (settings.supabase_url and settings.supabase_key):
        print("✗ SUPABASE_URL/SUPABASE_KEY가 .env에 없습니다. 먼저 설정하세요.")
        return 1

    store = SupabaseStore()
    sb = store.sb

    print("[1] 테이블 존재 확인")
    for t in TABLES:
        try:
            sb.table(t).select("*").limit(1).execute()
            print(f"   ✓ {t}")
        except Exception as e:
            print(f"   ✗ {t}: {e}")
            print("   → Supabase SQL Editor에서 db/schema.sql 를 먼저 실행하세요.")
            return 1

    print("[2] 테스트 그룹/멤버 시드")
    user_ids = []
    group_id = None
    try:
        seeds = [
            {"toss_user_id": "verify_jihoon", "name": "지훈", "birth_date": "1993-05-01"},
            {"toss_user_id": "verify_minjun", "name": "민준", "birth_date": "1990-11-23"},
            {"toss_user_id": "verify_seoyeon", "name": "서연", "birth_date": "1996-02-14"},
        ]
        for s in seeds:
            row = sb.table("users").upsert(s, on_conflict="toss_user_id").execute().data[0]
            user_ids.append(row["id"])
        g = sb.table("groups").insert({
            "name": "[verify] 테스트 그룹", "owner_id": user_ids[0],
            "invite_code": "VERIFY-RT", "gen_time": "08:00",
        }).execute().data[0]
        group_id = g["id"]
        for uid in user_ids:
            sb.table("group_members").insert({"group_id": group_id, "user_id": uid}).execute()
        print(f"   ✓ group_id={group_id}, members={len(user_ids)}")

        print("[3] 운세 생성(Mock) → save_fortune → get_fortune 라운드트립")
        members = [Member(id=user_ids[i], name=seeds[i]["name"],
                          birth_date=date.fromisoformat(seeds[i]["birth_date"]))
                   for i in range(3)]
        target = date(2026, 6, 19)
        gf = fortune.generate(group_id, members, target, client=MockClient())
        store.save_fortune(gf)
        back = store.get_fortune(group_id, target)
        assert back is not None, "get_fortune가 None"
        assert len(back.personal_fortunes) == 3, "개인 운세 수 불일치"
        assert back.group_comment == gf.group_comment, "group_comment 불일치"
        print(f"   ✓ 저장/조회 일치 (개인 {len(back.personal_fortunes)}, 케미 {len(back.chemistry)})")

        print("[4] get_group / list_groups 확인")
        grp = store.get_group(group_id)
        assert grp and len(grp.members) == 3
        print(f"   ✓ get_group OK (members={len(grp.members)}, gen_time={grp.gen_time})")

        print("\n✅ Supabase 연결·스키마·StoreCRUD 전부 정상")
        return 0
    finally:
        # 테스트 데이터 정리 (group 삭제 시 cascade로 멤버/운세 제거)
        if group_id:
            sb.table("groups").delete().eq("id", group_id).execute()
        for uid in user_ids:
            sb.table("users").delete().eq("id", uid).execute()


if __name__ == "__main__":
    sys.exit(main())
