"""LLM 출력 후처리: 40자 트렁케이션 백업 + 경량 금지어 필터(03 문서 체크포인트)."""
from __future__ import annotations

MAX_LEN = 40

# 경량 금지어(예시). 운영 시 외부 리스트로 분리/확장.
_BANNED = ["죽", "사고", "암", "이혼", "파산", "병원", "장례"]


def truncate(text: str, max_len: int = MAX_LEN) -> str:
    """공백 포함 40자 초과 시 …로 자르는 백업 로직."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def has_banned(text: str) -> bool:
    return any(w in text for w in _BANNED)


def sanitize_line(text: str) -> tuple[str, bool]:
    """(정리된 문장, 금지어검출여부). 검출 시 호출측에서 재생성/대체 처리."""
    flagged = has_banned(text)
    return truncate(text), flagged
