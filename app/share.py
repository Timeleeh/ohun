"""카카오 공유용 카드 이미지 SSR (Pillow).

카카오 피드 템플릿의 imageUrl 은 공개 URL의 '래스터 이미지'여야 한다(SVG 불가).
그래서 서버에서 PNG(800x400, 권장 2:1)를 즉석 렌더한다. 디자인 톤은 목업과 통일:
다크 배경 + 네온 라임(케미), 오행색 노드.

폰트: 한글 글리프가 있는 TTF가 필요(카카오 서버가 아니라 '우리 서버'가 글자를 그린다).
기본 Windows malgun, 없으면 Noto/대체 경로 탐색, 최후엔 PIL 기본폰트(한글 깨짐 경고).
"""
from __future__ import annotations

import io
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

# 오행색 (목업 PALETTE와 동일)
_COLOR_KO = {"목": "#34e3a0", "화": "#ff7a8a", "토": "#ffc24b", "금": "#aab2c0", "수": "#54a0ff"}
_HANJA_KO = {"木": "목", "火": "화", "土": "토", "金": "금", "水": "수"}

BG = "#0d0e12"
CARD = "#181a20"
LINE = "#2a2e38"
INK = "#f4f5f7"
SUB = "#8d93a1"
ACC = "#c6ff3d"  # 네온 라임

# 한글 TTF 후보(개발: Windows / 배포: Linux Noto). 환경변수 OHN_CARD_FONT 로 강제 가능.
_FONT_CANDIDATES = [
    os.environ.get("OHN_CARD_FONT", ""),
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]
_FONT_BOLD_CANDIDATES = [
    os.environ.get("OHN_CARD_FONT_BOLD", ""),
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]


def _first_existing(paths: list[str]) -> str | None:
    return next((p for p in paths if p and os.path.exists(p)), None)


@lru_cache(maxsize=64)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _first_existing(_FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES)
    if path is None:  # 한글 폰트 없음 → 기본폰트(한글 깨짐). 배포 전 폰트 설치/지정 필요.
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def korean_font_available() -> bool:
    return _first_existing(_FONT_CANDIDATES) is not None


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, max_lines: int = 2) -> list[str]:
    """글자 단위 줄바꿈(한글은 단어 경계가 약해 글자 단위가 안전). 넘치면 …처리."""
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = ch
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and cur:
        lines.append(cur)
    # 마지막 줄이 잘렸으면 말줄임
    if cur and len(lines) == max_lines and draw.textlength(text, font=font) > max_w * max_lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def element_color(el: str) -> str:
    """오행(한글/한자) → 색. 모르면 라임."""
    ko = _HANJA_KO.get(el, el)
    return _COLOR_KO.get(ko, ACC)


def render_card_png(card: dict) -> bytes:
    """card: {group_name, date_label, day_element(한자), group_comment, members:[{name, element, score}]}"""
    W, H = 800, 400
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    PAD = 44

    # 상단: 그룹명 + 날짜 (좌) / 브랜드 (우)
    d.text((PAD, 36), card.get("group_name", "우리 그룹"), font=_font(30, bold=True), fill=INK)
    d.text((PAD, 78), card.get("date_label", ""), font=_font(19), fill=SUB)
    brand = "케미사주"
    bf = _font(24, bold=True)
    d.text((W - PAD - d.textlength(brand, font=bf), 40), brand, font=bf, fill=ACC)

    # 오늘의 기운 · 오행
    el = card.get("day_element", "")
    label_f = _font(34, bold=True)
    d.text((PAD, 128), "오늘의 기운 · ", font=label_f, fill=INK)
    off = PAD + d.textlength("오늘의 기운 · ", font=label_f)
    d.text((off, 128), el, font=label_f, fill=element_color(el))

    # 그룹 한줄평 패널
    panel_y, panel_h = 184, 86
    d.rounded_rectangle((PAD, panel_y, W - PAD, panel_y + panel_h), radius=18, fill=CARD, outline=LINE, width=1)
    cf = _font(22)
    comment = card.get("group_comment", "")
    lines = _wrap(d, comment, cf, W - PAD * 2 - 36, max_lines=2)
    ty = panel_y + (panel_h - len(lines) * 30) / 2
    for ln in lines:
        d.text((PAD + 18, ty), ln, font=cf, fill=INK)
        ty += 30

    # 멤버 노드 행(최대 5명, 초과 시 +N)
    members = card.get("members", [])[:6]
    extra = len(card.get("members", [])) - len(members)
    nx = PAD
    ny = 312
    r = 26
    nf = _font(20, bold=True)
    name_f = _font(15)
    star_f = _font(13, bold=True)
    gap = (W - PAD * 2 - len(members) * (r * 2)) / max(1, len(members) - 1) if len(members) > 1 else 0
    gap = min(gap, 46)
    for m in members[:5]:
        col = element_color(m.get("element", ""))
        cxp = nx + r
        cyp = ny + r
        d.ellipse((nx, ny, nx + r * 2, ny + r * 2), fill=col)
        nm = m.get("name", "")
        ch = nm[0] if nm else "?"
        chw = d.textlength(ch, font=nf)
        d.text((cxp - chw / 2, cyp - 14), ch, font=nf, fill="#0d0e12")
        # 이름
        nw = d.textlength(nm, font=name_f)
        d.text((cxp - nw / 2, ny + r * 2 + 6), nm, font=name_f, fill=SUB)
        # 점수(별)
        sc = int(m.get("score", 0) or 0)
        stars = "★" * sc + "☆" * (5 - sc)
        sw = d.textlength(stars, font=star_f)
        d.text((cxp - sw / 2, ny + r * 2 + 28), stars, font=star_f, fill=ACC)
        nx += r * 2 + gap
    if extra > 0 or len(members) > 5:
        rest = extra + max(0, len(members) - 5)
        d.text((nx, ny + r - 10), f"+{rest}", font=nf, fill=SUB)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# 운세 미생성/그룹 없음일 때도 PoC 이미지가 항상 나오도록 샘플 카드
SAMPLE_CARD = {
    "group_name": "우리팀 단톡방",
    "date_label": "2026년 6월 20일 (토)",
    "day_element": "水",
    "group_comment": "오늘은 각자 페이스대로, 무리한 합의는 잠시 미루세요.",
    "members": [
        {"name": "지훈", "element": "금", "score": 3},
        {"name": "민준", "element": "화", "score": 4},
        {"name": "서연", "element": "토", "score": 3},
        {"name": "하늘", "element": "수", "score": 5},
        {"name": "도윤", "element": "목", "score": 4},
    ],
}
