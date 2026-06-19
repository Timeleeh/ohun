"""캐시/그룹 저장소 추상화.

운영은 Supabase(daily_fortunes/daily_bonds)지만, 여기서는 인터페이스 + 인메모리 구현만 둔다.
핵심 계약: (group_id, date) 1회 생성 후 캐시 -> 같은 날 재호출 금지(요구사항 NFR).
"""
from __future__ import annotations

from datetime import date, time
from dataclasses import dataclass, field

from .models import GroupFortune, Member, PersonalFortune, Chemistry


@dataclass
class Group:
    id: str
    name: str
    members: list[Member]
    # 사용자가 지정한 '하루 한 번' 생성 시각(그룹별). 실시간 생성 안 함.
    gen_time: time = time(6, 0)  # 기본 06:00 KST
    last_active: date | None = None  # 비활성 그룹 배치 제외 판단용


class Store:
    def get_group(self, group_id: str) -> Group | None: ...
    def list_groups(self) -> list[Group]: ...
    def get_fortune(self, group_id: str, d: date) -> GroupFortune | None: ...
    def save_fortune(self, gf: GroupFortune) -> None: ...


@dataclass
class InMemoryStore(Store):
    groups: dict[str, Group] = field(default_factory=dict)
    _cache: dict[tuple[str, str], GroupFortune] = field(default_factory=dict)

    def upsert_group(self, g: Group) -> None:
        self.groups[g.id] = g

    def get_group(self, group_id: str) -> Group | None:
        return self.groups.get(group_id)

    def list_groups(self) -> list[Group]:
        return list(self.groups.values())

    def get_fortune(self, group_id: str, d: date) -> GroupFortune | None:
        return self._cache.get((group_id, d.isoformat()))

    def save_fortune(self, gf: GroupFortune) -> None:
        self._cache[(gf.group_id, gf.date.isoformat())] = gf


class SupabaseStore(Store):
    """Supabase(PostgreSQL) 백엔드. 스키마는 db/schema.sql 참고.

    운세는 (group_id, date) 단위로 3개 테이블에 저장/조회한다:
    daily_group_fortunes(헤더) + daily_personal_fortunes + daily_bonds.
    """

    def __init__(self, url: str | None = None, key: str | None = None):
        from supabase import create_client
        from .config import settings
        self.sb = create_client(url or settings.supabase_url, key or settings.supabase_key)

    # --- 그룹 ---
    def _build_group(self, g: dict) -> Group:
        rows = (self.sb.table("group_members")
                .select("user_id, users(id,name,birth_date)")
                .eq("group_id", g["id"]).execute().data or [])
        members = []
        for r in rows:
            u = r.get("users") or {}
            if u:
                members.append(Member(id=u["id"], name=u["name"],
                                      birth_date=date.fromisoformat(u["birth_date"])))
        return Group(
            id=g["id"], name=g["name"], members=members,
            gen_time=time.fromisoformat(g.get("gen_time") or "08:00:00"),
            last_active=date.fromisoformat(g["last_active"]) if g.get("last_active") else None,
        )

    def get_group(self, group_id: str) -> Group | None:
        res = self.sb.table("groups").select("*").eq("id", group_id).limit(1).execute().data
        return self._build_group(res[0]) if res else None

    def list_groups(self) -> list[Group]:
        res = self.sb.table("groups").select("*").execute().data or []
        return [self._build_group(g) for g in res]

    # --- 운세 캐시 ---
    def get_fortune(self, group_id: str, d: date) -> GroupFortune | None:
        ds = d.isoformat()
        hdr = (self.sb.table("daily_group_fortunes").select("*")
               .eq("group_id", group_id).eq("date", ds).limit(1).execute().data)
        if not hdr:
            return None
        h = hdr[0]
        pf = (self.sb.table("daily_personal_fortunes").select("*")
              .eq("group_id", group_id).eq("date", ds).execute().data or [])
        bonds = (self.sb.table("daily_bonds").select("*")
                 .eq("group_id", group_id).eq("date", ds).execute().data or [])
        return GroupFortune(
            group_id=group_id, date=d, day_element=h["day_element"],
            group_comment=h["group_comment"],
            personal_fortunes=[PersonalFortune(
                member_id=r["member_id"], line=r["line"], score=r["score"],
                base_element=r["base_element"]) for r in pf],
            chemistry=[Chemistry(pair_id=r["pair_id"], a_id=r["user_a_id"], b_id=r["user_b_id"],
                                 type=r["type"], line=r["line"]) for r in bonds],
        )

    def save_fortune(self, gf: GroupFortune) -> None:
        ds = gf.date.isoformat()
        self.sb.table("daily_group_fortunes").upsert({
            "group_id": gf.group_id, "date": ds,
            "day_element": gf.day_element, "group_comment": gf.group_comment,
        }).execute()
        if gf.personal_fortunes:
            self.sb.table("daily_personal_fortunes").upsert([{
                "group_id": gf.group_id, "date": ds, "member_id": p.member_id,
                "line": p.line, "score": p.score, "base_element": p.base_element,
            } for p in gf.personal_fortunes]).execute()
        if gf.chemistry:
            self.sb.table("daily_bonds").upsert([{
                "group_id": gf.group_id, "date": ds, "pair_id": c.pair_id,
                "user_a_id": c.a_id, "user_b_id": c.b_id, "type": c.type, "line": c.line,
            } for c in gf.chemistry]).execute()


# 기본 인메모리 싱글톤(개발/테스트). 운영은 Supabase.
store = InMemoryStore()


def get_store() -> Store:
    """Supabase 크리덴셜 있으면 SupabaseStore, 없으면 인메모리 store."""
    from .config import settings
    if settings.supabase_url and settings.supabase_key:
        return SupabaseStore()
    return store
