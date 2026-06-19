"""캐시/그룹 저장소 추상화.

운영은 Supabase(daily_fortunes/daily_bonds)지만, 여기서는 인터페이스 + 인메모리 구현만 둔다.
핵심 계약: (group_id, date) 1회 생성 후 캐시 -> 같은 날 재호출 금지(요구사항 NFR).
"""
from __future__ import annotations

from datetime import date, time
from dataclasses import dataclass, field

from .models import GroupFortune, Member


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


store = InMemoryStore()
