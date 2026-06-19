"""양력 날짜 -> 일주(日柱) -> 오행(五行) 결정론적 계산.

기획 결정: 토스 연동으로 받은 '양력 생년월일'만 사용한다(음력 변환·만세력 DB 불필요).
일주(천간/지지)는 율리우스적일수(JDN) 기반 60갑자 연속 순환으로 계산되므로,
같은 날짜는 언제 계산해도 항상 같은 결과가 나온다(요구사항 NFR: 결정론 보장).

천간은 본인을 상징하는 '일간(日干)'으로 쓰며, 그 오행을 개인 오행으로 본다.
"""
from __future__ import annotations

from datetime import date
from dataclasses import dataclass

# 10천간 / 12지지
HEAVENLY_STEMS = ["갑", "을", "병", "정", "무", "기", "경", "신", "임", "계"]
EARTHLY_BRANCHES = ["자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해"]

# 천간 -> 오행 (갑을:목 / 병정:화 / 무기:토 / 경신:금 / 임계:수)
STEM_ELEMENT = {
    "갑": "목", "을": "목",
    "병": "화", "정": "화",
    "무": "토", "기": "토",
    "경": "금", "신": "금",
    "임": "수", "계": "수",
}

# 오행 한자 표기 (프롬프트/카드 표시는 한자 기운으로 노출: 木火土金水)
ELEMENT_HANJA = {"목": "木", "화": "火", "토": "土", "금": "金", "수": "水"}

# 기준일(앵커): 1984-02-02 = 갑자일(甲子日). 한국 만세력 구현에서 널리 쓰이는 갑자 기준일.
# 앵커가 틀려도 '결정론(같은 날=같은 결과)'은 보장되며, 앵커는 라벨 매핑에만 영향.
# -> 운영 전 권위 있는 만세력으로 1회 검증할 것(README 체크포인트 참조).
_ANCHOR_JDN = None  # lazy 계산


def _gregorian_to_jdn(y: int, m: int, d: int) -> int:
    """그레고리력 -> 율리우스적일수(정오 기준 정수)."""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def _anchor() -> int:
    global _ANCHOR_JDN
    if _ANCHOR_JDN is None:
        _ANCHOR_JDN = _gregorian_to_jdn(1984, 2, 2)  # 갑자
    return _ANCHOR_JDN


@dataclass(frozen=True)
class DayPillar:
    stem: str        # 천간 (예: "갑")
    branch: str      # 지지 (예: "자")
    element: str     # 일간 오행 (예: "목")

    @property
    def label(self) -> str:
        return f"{self.stem}{self.branch}"

    @property
    def element_hanja(self) -> str:
        return ELEMENT_HANJA[self.element]


def day_pillar(d: date) -> DayPillar:
    """해당 양력 날짜의 일주를 반환한다."""
    offset = _gregorian_to_jdn(d.year, d.month, d.day) - _anchor()
    stem = HEAVENLY_STEMS[offset % 10]
    branch = EARTHLY_BRANCHES[offset % 12]
    return DayPillar(stem=stem, branch=branch, element=STEM_ELEMENT[stem])


def personal_element(birth: date) -> str:
    """본인 오행 = 출생일 일간 오행."""
    return day_pillar(birth).element


def day_element(target: date) -> str:
    """그날의 오행 = 그날 일간 오행."""
    return day_pillar(target).element
