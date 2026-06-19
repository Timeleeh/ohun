"""하루 한 번, 그룹별 지정 시각에 운세를 미리 생성하는 배치 스케줄러.

설계 의도(사용자 요구): 실시간 생성 금지. 사용자가 지정한 시각에 맞춰
하루 1회만 생성하고, 트래픽/자원을 관리하며 돌린다.

자원 효율 장치:
  1) 캐시 dedup        : (group_id, date) 이미 있으면 생성 스킵
  2) 비활성 그룹 제외   : last_active 가 inactive_days 이전이면 배치 대상에서 제외
  3) 동시성 상한       : Semaphore 로 동시 LLM 호출 수 제한
  4) 분당 레이트리밋    : 같은 시각에 몰린 그룹을 분당 N건으로 평탄화(쪼개 실행)
  5) 지터(jitter)      : 동일 시각 그룹들의 시작을 윈도우 내로 흩뿌려 스파이크 완화
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .store import Store, Group
from .fortune import generate


@dataclass
class BatchConfig:
    concurrency: int = 3          # 동시 LLM 호출 상한
    rate_per_min: int = 30        # 분당 최대 생성 건수(레이트리밋)
    jitter_seconds: float = 0.0   # 동일 시각 그룹 시작 분산 윈도우(테스트는 0)
    inactive_days: int = 7        # N일 미접속 그룹은 배치 제외


def due_groups(groups: list[Group], now: datetime, store: Store,
               inactive_days: int) -> list[Group]:
    """now(KST) 기준 '이번 분'에 생성해야 하는 활성 그룹 목록.

    - gen_time 의 시:분이 now 와 일치
    - 오늘자 캐시가 아직 없음
    - 최근 inactive_days 내 활동 있음
    """
    today = now.date()
    cutoff = today - timedelta(days=inactive_days)
    due = []
    for g in groups:
        if (g.gen_time.hour, g.gen_time.minute) != (now.hour, now.minute):
            continue
        if g.last_active is not None and g.last_active < cutoff:
            continue
        if store.get_fortune(g.id, today) is not None:
            continue
        due.append(g)
    return due


async def run_batch(groups: list[Group], target: date, store: Store,
                    cfg: BatchConfig, client=None, sleep=asyncio.sleep) -> dict:
    """주어진 그룹들을 트래픽 관리하며 생성. 결과 요약 dict 반환.

    레이트리밋: rate_per_min 건마다 60초 대기(테스트에서는 sleep 주입으로 즉시화).
    """
    sem = asyncio.Semaphore(cfg.concurrency)
    loop = asyncio.get_event_loop()
    done, skipped, failed = 0, 0, 0

    async def one(g: Group, slot: int):
        nonlocal done, failed
        if cfg.jitter_seconds:
            await sleep((slot % cfg.rate_per_min) / max(1, cfg.rate_per_min) * cfg.jitter_seconds)
        async with sem:
            try:
                # 동기 anthropic 호출을 스레드로 오프로딩(이벤트루프 블로킹 방지)
                gf = await loop.run_in_executor(
                    None, lambda: generate(g.id, g.members, target, client)
                )
                store.save_fortune(gf)
                done += 1
            except Exception:
                failed += 1

    tasks = []
    for i, g in enumerate(groups):
        if store.get_fortune(g.id, target) is not None:
            skipped += 1
            continue
        # 분당 rate_per_min 건씩 끊어서 평탄화
        if i and i % cfg.rate_per_min == 0:
            await asyncio.gather(*tasks)
            tasks = []
            await sleep(60)
        tasks.append(asyncio.create_task(one(g, i)))
    if tasks:
        await asyncio.gather(*tasks)

    return {"target": target.isoformat(), "due": len(groups),
            "generated": done, "skipped": skipped, "failed": failed}


async def tick(store: Store, cfg: BatchConfig, now: datetime, client=None,
               sleep=asyncio.sleep) -> dict:
    """스케줄러 1분 틱: 이번 분에 due 인 그룹만 골라 배치 실행."""
    groups = due_groups(store.list_groups(), now, store, cfg.inactive_days)
    if not groups:
        return {"target": now.date().isoformat(), "due": 0,
                "generated": 0, "skipped": 0, "failed": 0}
    return await run_batch(groups, now.date(), store, cfg, client, sleep)
