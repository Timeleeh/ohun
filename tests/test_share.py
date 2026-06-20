"""카카오 공유: SSR 카드(PNG) + OG 랜딩 + config 엔드포인트 테스트."""
from datetime import date

from fastapi.testclient import TestClient

import app.main as main_mod
from app.store import InMemoryStore
from app import fortune
from app.share import render_card_png, SAMPLE_CARD
from app.llm.client import MockClient

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _seed():
    st = InMemoryStore()
    st.upsert_user("u_a", "지훈", date(1993, 5, 1))
    st.upsert_user("u_b", "민준", date(1990, 11, 23))
    g = st.create_group("우리팀 단톡방", "u_a", "ABCD1234")
    st.add_member(g.id, "u_b")
    gf = fortune.generate(g.id, st.get_group(g.id).members,
                          date(2026, 6, 19), client=MockClient())
    st.save_fortune(gf)
    return st, g


def test_render_card_returns_png():
    png = render_card_png(SAMPLE_CARD)
    assert png[:8] == PNG_MAGIC and len(png) > 1000


def test_card_endpoint_from_fortune():
    st, g = _seed()
    main_mod.store = st
    c = TestClient(main_mod.app)
    r = c.get(f"/share/{g.id}/card.png", params={"d": "2026-06-19"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == PNG_MAGIC


def test_card_endpoint_falls_back_to_sample():
    # 운세 없는(미생성) 그룹도 PoC 이미지가 항상 나와야 함
    main_mod.store = InMemoryStore()
    c = TestClient(main_mod.app)
    r = c.get("/share/UNKNOWN/card.png")
    assert r.status_code == 200 and r.content[:8] == PNG_MAGIC


def test_share_landing_has_og_tags():
    st, g = _seed()
    main_mod.store = st
    c = TestClient(main_mod.app)
    r = c.get(f"/share/{g.id}")
    assert r.status_code == 200
    assert 'property="og:image"' in r.text
    assert f"/share/{g.id}/card.png" in r.text
    assert "케미사주" in r.text


def test_share_config_shape():
    main_mod.store = InMemoryStore()
    c = TestClient(main_mod.app)
    r = c.get("/share/config")
    assert r.status_code == 200
    body = r.json()
    assert "kakao_js_key" in body and "app_url" in body
