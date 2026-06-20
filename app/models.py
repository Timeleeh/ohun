"""API/도메인 공용 Pydantic 모델."""
from __future__ import annotations

from datetime import date
from pydantic import BaseModel, Field


class Member(BaseModel):
    id: str
    name: str
    birth_date: date  # 토스 연동 양력 생년월일 (음력 미사용)


class PersonalFortune(BaseModel):
    member_id: str
    line: str
    score: int = Field(ge=1, le=5)
    base_element: str  # 룰 기반 베이스(예: "木 기운 강함 (비화)")


class Chemistry(BaseModel):
    pair_id: str
    a_id: str
    b_id: str
    type: str  # good | caution
    line: str


class GroupFortune(BaseModel):
    group_id: str
    date: date
    day_element: str  # 그날 오행 한자 (예: "木")
    group_comment: str
    personal_fortunes: list[PersonalFortune]
    chemistry: list[Chemistry]


class GenerateRequest(BaseModel):
    group_id: str
    members: list[Member]
    target_date: date | None = None  # 미지정 시 오늘(KST)


# ===== 프론트(화면)용 뷰 모델 =====
# 영속 모델(GroupFortune)은 member_id만 보관하므로, API 레이어에서 그룹 멤버와
# 조인해 이름·오행색(목/화/토/금/수)·표시 라벨까지 채운 '화면 그대로 그릴 수 있는' 형태.
class MemberView(BaseModel):
    id: str
    name: str
    element: str  # 목/화/토/금/수 (프론트 색상 팔레트 키)
    base: str     # 룰 기반 베이스 라벨
    score: int = Field(ge=1, le=5)
    line: str


class ChemistryView(BaseModel):
    a: str
    b: str
    type: str  # good | caution
    line: str
    fate: bool = False  # '오늘의 운명' 강조 여부


class GroupFortuneView(BaseModel):
    group_id: str
    group_name: str
    date: date
    date_label: str  # 예: "2026년 6월 19일 (금)"
    day_element: str
    group_comment: str
    members: list[MemberView]
    chemistry: list[ChemistryView]


class GroupSummary(BaseModel):
    id: str
    name: str
    gen_time: str  # "HH:MM"
