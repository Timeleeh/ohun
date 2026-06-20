# 케미사주 — 그룹 운세 백엔드 (운세 생성 엔진)

기획 문서(`ObsidianVault/jh/오운행`)의 핵심인 **운세 생성 엔진**을 구현한 FastAPI 백엔드.
지적된 리스크를 보완해 설계했다.

## 확정된 결정사항 (2026-06-19)

| 항목 | 결정 |
|---|---|
| 그룹 최대 인원 | **6명** |
| 생년월일 | **토스 연동 양력만 사용** — 음력 변환/만세력 DB 불필요 |
| 생성 방식 | **실시간 생성 안 함.** 그룹별 사용자 지정 시각에 **하루 1회** 배치 생성 후 캐시 |
| JSON 강제 | Claude **tool use**(`emit_fortunes`) + `tool_choice` 강제 (response_format 미사용) |
| LLM 호출 | 그룹·날짜당 1회. 같은 날 재호출 금지(캐시 dedup) |

## 리스크 보완 내역

1. **토스 웹뷰 내 카카오 공유** — 여전히 PoC 검증 필요(플랫폼 의존). 백엔드는 공유 카드 데이터만 제공하도록 분리.
2. **JSON 강제** — `app/llm/schema.py`의 tool 정의 + `tool_choice={"type":"tool"}`로 구조 보장. temperature 0.95로 위트 확보해도 구조 안 깨짐.
3. **오행/일주 계산** — 양력만 받으므로 음력 변환 제거. 일주는 JDN 기반 60갑자 연속 순환으로 결정론 계산(`app/saju/elements.py`). 만세력 DB 불필요.
   - ⚠️ 앵커(1984-02-02=갑자)는 운영 전 권위 있는 만세력으로 1회 검증 권장. 앵커가 틀려도 '같은 날=같은 결과' 결정론은 보장됨.

## 자원 효율 배치 설계 (`app/scheduler.py`)

사용자 요구(실시간 X, 지정 시각 1회, 트래픽 관리)를 반영:
- 그룹별 `gen_time`에만 생성, 캐시 dedup
- 비활성 그룹(기본 7일 미접속) 배치 제외
- 동시성 상한(Semaphore) + 분당 레이트리밋 + 지터로 스파이크 평탄화

## 구조

```
app/
  saju/elements.py    # 양력→일주→오행 (결정론)
  saju/relations.py   # 상생상극, 케미 페어 상위 k 선정
  llm/prompts.py      # 03 문서 시스템프롬프트 + few-shot
  llm/schema.py       # tool use JSON 스키마
  llm/client.py       # Claude 호출 / 키 없으면 MockClient
  llm/postprocess.py  # 40자 트렁케이션 + 금지어 필터
  fortune.py          # 오케스트레이션 (멤버→베이스→LLM→결과)
  scheduler.py        # 하루 1회 트래픽 관리 배치
  store.py            # 캐시/그룹 저장소 (인메모리; 운영은 Supabase)
  main.py             # FastAPI
demo.py               # 로컬 데모 (키 없으면 Mock)
tests/                # 엔진 결정론 + 스케줄러 테스트
```

## 실행

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest tests/ -q     # 테스트
.venv/Scripts/python demo.py                 # 데모 (ANTHROPIC_API_KEY 있으면 실제 Claude)
.venv/Scripts/python -m uvicorn app.main:app --reload   # API 서버
```

`.env`는 `.env.example` 참고.

## LLM provider (멀티)

`OHN_PROVIDER`(auto|gemini|anthropic|mock)로 선택. `auto`는 가진 키 우선순위(gemini→anthropic→mock).
- Anthropic: `ANTHROPIC_API_KEY` (tool use로 JSON 강제)
- Gemini: `GEMINI_API_KEY`/`GOOGLE_API_KEY` (`response_mime_type=application/json`로 JSON 강제)
- 키 없으면 `MockClient`로 파이프라인 동작

## Supabase 연동

- 스키마: `db/schema.sql` (Supabase SQL Editor에 붙여넣어 실행)
- `SUPABASE_URL` + `SUPABASE_KEY` 설정 시 `get_store()`가 `SupabaseStore` 사용, 없으면 인메모리
- 운세는 `(group_id, date)` 단위 캐시: `daily_group_fortunes` + `daily_personal_fortunes` + `daily_bonds`
- 그룹 최대 6명은 DB 트리거로도 강제

### 실제 연결 방법
1. [supabase.com](https://supabase.com)에서 프로젝트 생성
2. SQL Editor에 `db/schema.sql` 전체를 붙여넣고 실행
3. Project Settings → API 에서 **Project URL**과 **service_role key**를 복사해 `.env`에 설정
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_KEY=<service_role key>
   ```
4. 연결·스키마·CRUD 한 번에 검증:
   ```bash
   .venv/Scripts/python scripts/verify_supabase.py
   ```
   (LLM 호출 없이 DB 경로만 검증, 테스트 행은 자동 정리)

## 프론트 ↔ API 연결 (`docs/index.html`)

목업 화면이 **실제 API를 호출**하도록 연결됨. 설정이 없으면 샘플 데이터로 그대로 동작(폴백).

- 화면 전용 엔드포인트:
  - `GET /groups/{group_id}/view` — 캐시된 운세 + 그룹 멤버(이름·오행색)를 조인해 **바로 그릴 수 있는** 형태로 반환
  - `GET /users/{user_id}/groups` — 그룹 전환 스위처용 목록
  - 오행색(`element`)은 운세 행의 `base` 라벨(예: "金 기운 …")을 단일 출처로 산출 → 노드 색이 항상 라벨과 일치
- 연결 방법(쿼리스트링 또는 localStorage):
  ```
  https://timeleeh.github.io/ohun/?api=<백엔드주소>&group=<group_id>&user=<user_id>
  ```
  또는 `localStorage.chemisaju_api / chemisaju_group / chemisaju_user`
- CORS: `OHN_CORS_ORIGINS`(콤마 구분, 기본 `*`). 운영은 GitHub Pages 출처로 좁힐 것.
- 로컬 e2e 예:
  ```bash
  OHN_PROVIDER=mock .venv/Scripts/python -m uvicorn app.main:app --port 8000
  # 브라우저에서 docs/index.html?api=http://127.0.0.1:8000&group=<id>&user=<id>
  ```

## 다음 단계 (미구현)

- ~~Supabase 연동~~ ✅ (스키마 + SupabaseStore)
- ~~프론트(목업) → 실제 API 연결~~ ✅ (`/view` · `/users/{id}/groups` + CORS + 폴백)
- 실제 LLM 출력 품질 확인 (Gemini/Anthropic 키 + 크레딧)
- 토스 미니앱 인증/사용자정보 연동 어댑터(MockAuth) → 실호출(사전계약·키 발급 대기)
- 카카오 공유 카드 이미지 렌더링(SSR) + 토스 웹뷰 PoC
