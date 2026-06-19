"""Claude API 호출 래퍼.

tool_choice로 emit_fortunes 도구 사용을 강제해 JSON 구조를 보장한다.
few-shot은 (user 텍스트) + (assistant tool_use) + (user tool_result) 형태로 대화에 고정한다.
키가 없는 환경(로컬 데모/CI)에서는 MockClient로 결정론적 더미 출력을 만든다.
"""
from __future__ import annotations

import json

from ..config import settings
from .prompts import SYSTEM_PROMPT, FEWSHOT_USER, FEWSHOT_TOOL_INPUT
from .schema import EMIT_FORTUNES_TOOL, EMIT_TOOL_NAME


def _fewshot_messages() -> list[dict]:
    """few-shot 1세트를 도구 호출 대화로 구성."""
    return [
        {"role": "user", "content": FEWSHOT_USER},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "fewshot_call_1",
                    "name": EMIT_TOOL_NAME,
                    "input": FEWSHOT_TOOL_INPUT,
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "fewshot_call_1", "content": "OK"}
            ],
        },
    ]


class ClaudeClient:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 temperature: float | None = None):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key or settings.anthropic_api_key)
        self.model = model or settings.model
        self.temperature = settings.temperature if temperature is None else temperature

    def generate(self, user_prompt: str) -> dict:
        """user_prompt -> emit_fortunes 도구 입력(dict)."""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=self.temperature,
            system=SYSTEM_PROMPT,
            tools=[EMIT_FORTUNES_TOOL],
            tool_choice={"type": "tool", "name": EMIT_TOOL_NAME},  # JSON 강제
            messages=_fewshot_messages() + [{"role": "user", "content": user_prompt}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == EMIT_TOOL_NAME:
                return block.input
        raise RuntimeError("모델이 emit_fortunes 도구를 호출하지 않았습니다.")


class MockClient:
    """API 키 없이 파이프라인 검증용. 입력 프롬프트를 파싱해 형식만 맞춘 더미 생성."""

    def generate(self, user_prompt: str) -> dict:
        members, pairs = _parse_prompt(user_prompt)
        return {
            "group_comment": "오늘은 각자 페이스대로, 무리한 합의는 잠시 미루세요",
            "personal_fortunes": [
                {"member_id": m["id"], "line": f"{m['name']}님 오늘은 컨디션 무난, 한 발씩 전진", "score": 3}
                for m in members
            ],
            "chemistry": [
                {"pair_id": p["pair_id"], "type": p["kind"],
                 "line": f"{p['a']}님과 {p['b']}님, 오늘 대화 타이밍만 잘 맞추면 OK"}
                for p in pairs
            ],
        }


def _parse_prompt(text: str):
    """MockClient 전용: 프롬프트 텍스트에서 멤버/페어 id를 추출."""
    members, pairs = [], []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- id:"):
            # "- id: jihoon, 이름: 지훈, ..."
            parts = line.split(",")
            mid = parts[0].split(":", 1)[1].strip()
            name = parts[1].split(":", 1)[1].strip()
            members.append({"id": mid, "name": name})
        elif line.startswith("- pair_id:"):
            parts = line.split(",")
            pid = parts[0].split(":", 1)[1].strip()
            a = parts[1].split(":", 1)[1].strip().split("(")[0].strip()
            b = parts[2].split(":", 1)[1].strip().split("(")[0].strip()
            rel = parts[3].split(":", 1)[1].strip() if len(parts) > 3 else ""
            kind = "caution" if "상극" in rel else "good"
            pairs.append({"pair_id": pid, "a": a, "b": b, "kind": kind})
    return members, pairs


def get_client():
    """키 있으면 실제 Claude, 없으면 Mock."""
    if settings.anthropic_api_key:
        return ClaudeClient()
    return MockClient()
