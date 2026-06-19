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
