"""tool use 기반 JSON 강제 스키마.

Claude API에는 OpenAI식 response_format이 없으므로(리스크 #2),
출력 구조는 '도구 입력 스키마 + tool_choice 강제'로 보장한다.
"""

EMIT_TOOL_NAME = "emit_fortunes"

EMIT_FORTUNES_TOOL = {
    "name": EMIT_TOOL_NAME,
    "description": "생성한 그룹 운세/케미 결과를 구조화해 전달한다. 반드시 이 도구로만 결과를 반환한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "group_comment": {
                "type": "string",
                "description": "그룹 전체 한줄평, 공백 포함 40자 이내",
            },
            "personal_fortunes": {
                "type": "array",
                "description": "입력된 멤버 전원에 대한 개인 운세",
                "items": {
                    "type": "object",
                    "properties": {
                        "member_id": {"type": "string", "description": "입력받은 id 그대로"},
                        "line": {"type": "string", "description": "개인 한줄 운세, 40자 이내, 이름 호명"},
                        "score": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "required": ["member_id", "line", "score"],
                },
            },
            "chemistry": {
                "type": "array",
                "description": "입력으로 주어진 pair 목록에 대해서만 생성",
                "items": {
                    "type": "object",
                    "properties": {
                        "pair_id": {"type": "string", "description": "입력받은 pair_id 그대로"},
                        "type": {"type": "string", "enum": ["good", "caution"]},
                        "line": {"type": "string", "description": "관계 한줄 코멘트, 40자 이내, 두 사람 이름 모두 포함"},
                    },
                    "required": ["pair_id", "type", "line"],
                },
            },
        },
        "required": ["group_comment", "personal_fortunes", "chemistry"],
    },
}
