"""룰 기반 엔진 결정론/정확성 + 스케줄러 트래픽 관리 테스트."""
import asyncio
from datetime import date, datetime, time, timezone, timedelta

from app.saju.elements import day_pillar, personal_element, HEAVENLY_STEMS, EARTHLY_BRANCHES
from app.saju.relations import relation, select_pairs
from app.models import Member
from app import fortune
from app.llm.client import MockClient
from app.store import InMemoryStore, Group
from app.scheduler import BatchConfig, due_groups, run_batch

KST = timezone(timedelta(hours=9))


def test_anchor_is_gapja():
    # 앵커 1984-02-02 = 갑자
    dp = day_pillar(date(1984, 2, 2))
    assert dp.stem == "갑" and dp.branch == "자"
    assert dp.element == "목"


def test_day_pillar_advances_one_each_day():
    # 연속 일자는 천간+1, 지지+1 순환
    base = date(1984, 2, 2)
    for k in range(1, 70):
        d = base + timedelta(days=k)
        dp = day_pillar(d)
        assert dp.stem == HEAVENLY_STEMS[k % 10]
        assert dp.branch == EARTHLY_BRANCHES[k % 12]


def test_determinism_same_date_same_result():
    d = date(1995, 8, 17)
    assert day_pillar(d).label == day_pillar(d).label
    assert personal_element(d) == personal_element(d)


def test_relation_rules():
    assert relation("목", "화") == "상생"   # 목생화
    assert relation("화", "목") == "설기"
    assert relation("금", "목") == "상극"   # 금극목
    assert relation("목", "금") == "피극"
    assert relation("토", "토") == "비화"


def test_select_pairs_limit_and_determinism():
    members = [
        {"id": "a", "name": "A", "element": "목"},
        {"id": "b", "name": "B", "element": "금"},  # a와 상극(드라마↑)
        {"id": "c", "name": "C", "element": "화"},  # a와 상생
        {"id": "d", "name": "D", "element": "목"},  # a와 비화
    ]
    p1 = select_pairs(members, 3)
    p2 = select_pairs(members, 3)
    assert len(p1) == 3
    assert [(x.a_id, x.b_id) for x in p1] == [(x.a_id, x.b_id) for x in p2]
    # 가장 드라마 높은(상극) 페어가 1순위
    assert p1[0].kind == "caution"


def test_full_generate_with_mock():
    members = [
        Member(id="jihoon", name="지훈", birth_date=date(1993, 5, 1)),
        Member(id="minjun", name="민준", birth_date=date(1990, 11, 23)),
        Member(id="seoyeon", name="서연", birth_date=date(1996, 2, 14)),
    ]
    gf = fortune.generate("g1", members, date(2026, 6, 19), client=MockClient())
    assert len(gf.personal_fortunes) == 3
    assert all(1 <= p.score <= 5 for p in gf.personal_fortunes)
    assert all(len(p.line) <= 40 for p in gf.personal_fortunes)
    # 케미 pair_id는 입력 메타에 있는 것만
    assert gf.chemistry, "케미가 비어있으면 안 됨"


def test_max_group_size_enforced():
    members = [Member(id=str(i), name=f"m{i}", birth_date=date(1990, 1, 1 + i)) for i in range(7)]
    try:
        fortune.build_prompt(members, date(2026, 6, 19))
        assert False, "7명은 거부되어야 함"
    except ValueError:
        pass


def test_scheduler_dedup_and_due():
    store = InMemoryStore()
    members = [Member(id="a", name="A", birth_date=date(1990, 1, 1))]
    g = Group(id="g1", name="테스트", members=members, gen_time=time(6, 0))
    store.upsert_group(g)
    now = datetime(2026, 6, 19, 6, 0, tzinfo=KST)

    due = due_groups(store.list_groups(), now, store, inactive_days=7)
    assert len(due) == 1

    async def fast_sleep(_):
        return None

    cfg = BatchConfig(concurrency=2, rate_per_min=10)
    res = asyncio.run(run_batch(due, now.date(), store, cfg, client=MockClient(), sleep=fast_sleep))
    assert res["generated"] == 1

    # 두 번째 틱: 이미 캐시 -> due 0 (실시간/중복 생성 금지)
    due2 = due_groups(store.list_groups(), now, store, inactive_days=7)
    assert len(due2) == 0


def test_get_store_defaults_inmemory():
    # supabase 크리덴셜 없으면 인메모리 싱글톤 반환
    from app.store import get_store, store as default_store, InMemoryStore
    s = get_store()
    assert isinstance(s, InMemoryStore) and s is default_store


def test_scheduler_skips_inactive():
    store = InMemoryStore()
    members = [Member(id="a", name="A", birth_date=date(1990, 1, 1))]
    old = date(2026, 6, 1)  # 18일 전
    g = Group(id="g1", name="비활성", members=members, gen_time=time(6, 0), last_active=old)
    store.upsert_group(g)
    now = datetime(2026, 6, 19, 6, 0, tzinfo=KST)
    due = due_groups(store.list_groups(), now, store, inactive_days=7)
    assert len(due) == 0
