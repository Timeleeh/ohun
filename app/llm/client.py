"""Claude API 호출 래퍼.

tool_choice로 emit_fortunes 도구 사용을 강제해 JSON 구조를 보장한다.
few-shot은 (user 텍스트) + (assistant tool_use) + (user tool_result) 형태로 대화에 고정한다.
키가 없는 환경(로컬 데모/CI)에서는 MockClient로 결정론적 더미 출력을 만든다.
"""
from __future__ import annotations

import json

from ..config import settings
from .prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_GEMINI, FEWSHOT_USER, FEWSHOT_TOOL_INPUT
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

    def _accepts_temperature(self) -> bool:
        # opus 4.7+ / fable / mythos는 sampling 파라미터(temperature 등)를 400으로 거부.
        # sonnet/haiku 계열만 temperature 허용.
        m = self.model.lower()
        return not any(k in m for k in ("opus-4-7", "opus-4-8", "fable", "mythos"))

    def generate(self, user_prompt: str) -> dict:
        """user_prompt -> emit_fortunes 도구 입력(dict)."""
        kwargs = dict(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[EMIT_FORTUNES_TOOL],
            tool_choice={"type": "tool", "name": EMIT_TOOL_NAME},  # JSON 강제
            messages=_fewshot_messages() + [{"role": "user", "content": user_prompt}],
        )
        if self._accepts_temperature():
            kwargs["temperature"] = self.temperature
        resp = self.client.messages.create(**kwargs)
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


class GeminiClient:
    """Google Gemini 백엔드. tool use 대신 JSON 강제(response_mime_type)로 구조 보장."""

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 temperature: float | None = None):
        from google import genai

        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self.model = model or settings.gemini_model
        self.temperature = settings.temperature if temperature is None else temperature

    def generate(self, user_prompt: str) -> dict:
        from google.genai import types

        # few-shot(예시 입력→기대 JSON)을 user/model 턴으로 고정
        contents = [
            {"role": "user", "parts": [{"text": FEWSHOT_USER}]},
            {"role": "model", "parts": [{"text": json.dumps(FEWSHOT_TOOL_INPUT, ensure_ascii=False)}]},
            {"role": "user", "parts": [{"text": user_prompt}]},
        ]
        resp = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT_GEMINI,
                temperature=self.temperature,
                response_mime_type="application/json",  # JSON 강제
            ),
        )
        return json.loads(resp.text)


def get_client():
    """provider 설정/보유 키에 따라 백엔드 선택. 기본 auto: gemini → anthropic → mock."""
    p = settings.provider
    if p == "gemini" or (p == "auto" and settings.gemini_api_key):
        return GeminiClient()
    if p == "anthropic" or (p == "auto" and settings.anthropic_api_key):
        return ClaudeClient()
    return MockClient()
