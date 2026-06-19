"""오행 상생·상극 관계 및 케미 페어 선정 로직 (룰 기반, 결정론적).

LLM에 넘기기 전 단계에서:
  1) '그날 오행' vs '개인 오행' 관계 -> 개인 베이스 운세 라벨 산출
  2) 멤버 간 오행 관계 -> 드라마(상생/상극) 강한 페어 상위 k개 선정
N명 전원 조합(N*(N-1)/2)을 다 넘기지 않고 상위 k개만 추려 LLM 호출 비용/품질을 관리한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .elements import ELEMENT_HANJA

# 상생: 목생화 화생토 토생금 금생수 수생목  (generates[X] = X가 생하는 오행)
GENERATES = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}
# 상극: 목극토 토극수 수극화 화극금 금극목  (controls[X] = X가 극하는 오행)
CONTROLS = {"목": "토", "토": "수", "수": "화", "화": "금", "금": "목"}


def relation(src: str, dst: str) -> str:
    """src 오행이 dst 오행에 미치는 관계 종류.

    반환: 비화 / 상생(생) / 설기(생을 당함) / 상극(극) / 피극(극을 당함)
    """
    if src == dst:
        return "비화"
    if GENERATES[src] == dst:
        return "상생"      # src가 dst를 생함 (도움)
    if GENERATES[dst] == src:
        return "설기"      # dst가 src를 생함 -> src 기운이 빠짐
    if CONTROLS[src] == dst:
        return "상극"      # src가 dst를 극함
    if CONTROLS[dst] == src:
        return "피극"      # dst가 src를 극함 (눌림)
    return "비화"


def personal_base_text(day_el: str, my_el: str) -> str:
    """그날 오행 -> 개인 오행 관계를 기획문서(03) 예시 톤의 한 줄 라벨로."""
    rel = relation(day_el, my_el)  # 그날(src)이 나(dst)에게
    d, m = ELEMENT_HANJA[day_el], ELEMENT_HANJA[my_el]
    if rel == "비화":
        return f"{m} 기운 강함 (비화로 추진력 상승)"
    if rel == "상생":
        return f"{m} 기운 충만 ({d}생{m}으로 운 받쳐줌)"
    if rel == "설기":
        return f"{m} 기운 분산 ({m}생{d}으로 에너지 소모)"
    if rel == "상극":
        return f"{m} 기운 과열 ({d}극{m} 자극으로 변동성 큼)"
    if rel == "피극":
        return f"{m} 기운 위축 ({d}극{m}으로 충돌 가능)"
    return f"{m} 기운 평이"


# 페어 드라마 점수: 상극이 콘텐츠(케미)로 가장 재밌고, 상생이 그다음. 비화/무관계는 낮음.
_PAIR_DRAMA = {"상극": 3, "피극": 3, "상생": 2, "설기": 2, "비화": 1}


@dataclass
class PairCandidate:
    a_id: str
    b_id: str
    a_name: str
    b_name: str
    a_element: str
    b_element: str
    relation: str       # a -> b 관계
    kind: str           # "good" | "caution"
    drama: int

    @property
    def relation_phrase(self) -> str:
        """프롬프트용 관계 설명 (예: '상극-금극목', '상생-목생화', '비화-동일오행')."""
        a, b = ELEMENT_HANJA[self.a_element], ELEMENT_HANJA[self.b_element]
        rel = self.relation
        if rel == "비화":
            return "비화-동일오행"
        if rel in ("상생", "설기"):
            # 누가 누구를 생하는지 표기
            if rel == "상생":
                return f"상생-{a}생{b}"
            return f"상생-{b}생{a}"
        # 상극/피극
        if rel == "상극":
            return f"상극-{a}극{b}"
        return f"상극-{b}극{a}"


def _kind(rel: str) -> str:
    """good(상생/비화) vs caution(상극류)."""
    return "caution" if rel in ("상극", "피극") else "good"


def select_pairs(members: list[dict], max_pairs: int) -> list[PairCandidate]:
    """members: [{id, name, element}] -> 드라마 강한 상위 페어.

    동점 시 입력 순서로 안정 정렬되어 같은 입력은 항상 같은 페어 집합을 만든다.
    """
    cands: list[PairCandidate] = []
    for a, b in combinations(members, 2):
        rel = relation(a["element"], b["element"])
        cands.append(
            PairCandidate(
                a_id=a["id"], b_id=b["id"],
                a_name=a["name"], b_name=b["name"],
                a_element=a["element"], b_element=b["element"],
                relation=rel, kind=_kind(rel), drama=_PAIR_DRAMA[rel],
            )
        )
    # drama 내림차순, 동점은 입력 등장 순서 유지(enumerate index)
    indexed = list(enumerate(cands))
    indexed.sort(key=lambda t: (-t[1].drama, t[0]))
    return [c for _, c in indexed[:max_pairs]]
