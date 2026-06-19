"""로컬 데모: 03 문서 예시 그룹으로 운세 한 세트 생성해 출력.

ANTHROPIC_API_KEY 있으면 실제 Claude, 없으면 MockClient 자동 사용.
실행: python demo.py
"""
from datetime import date
import json

from app.models import Member
from app.saju.elements import day_pillar
from app import fortune
from app.llm.client import get_client


def main():
    target = date(2026, 6, 19)
    dp = day_pillar(target)
    print(f"== {target} 일주: {dp.label} (그날 오행: {dp.element_hanja}) ==\n")

    members = [
        Member(id="jihoon", name="지훈", birth_date=date(1993, 5, 1)),
        Member(id="minjun", name="민준", birth_date=date(1990, 11, 23)),
        Member(id="seoyeon", name="서연", birth_date=date(1996, 2, 14)),
    ]

    prompt, meta = fortune.build_prompt(members, target)
    print("[LLM에 전달되는 user prompt]\n" + prompt + "\n")

    client = get_client()
    print(f"[client] {type(client).__name__}\n")
    gf = fortune.generate("demo", members, target, client=client)

    print("[생성 결과]")
    print(json.dumps(gf.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
