# 배포 가이드 — 케미사주 API (공개 호스팅)

카카오 공유가 동작하려면 **카카오 서버가 카드 이미지 URL을 가져갈 수 있어야** 한다 → 백엔드를 공개 https에 올려야 한다. Docker 한 장으로 Render/Railway/Fly 어디든 동일하게 배포된다.

## 무엇이 준비돼 있나
- `Dockerfile` — python3.12-slim + **fonts-nanum**(공유 카드 한글 렌더) + uvicorn(`$PORT` 바인딩)
- `render.yaml` — Render Blueprint(깃 연결 → 원클릭)
- `.dockerignore` — `.env`/시크릿/테스트/목업 제외

## 옵션 A. Render (추천, 무료 플랜)
1. 이 레포를 GitHub에 푸시(이미 `Timeleeh/ohun`)
2. Render → **New + → Blueprint** → 레포 선택 → `render.yaml` 자동 인식
3. 환경변수(시크릿)는 콘솔에서 입력:
   - `OHN_KAKAO_JS_KEY` = 카카오 JavaScript 키
   - (선택) `SUPABASE_URL` / `SUPABASE_KEY` — 없으면 인메모리(재시작 시 데이터 초기화)
   - (선택) `GEMINI_API_KEY` + `OHN_PROVIDER=gemini` — 실제 운세 생성까지 원하면
4. 배포 후 URL 예: `https://chemisaju-api.onrender.com`
   - 확인: `/health`, `/share/<group_id>/card.png`, `/share/<group_id>`

## 옵션 B. Railway / Fly.io
- **Railway**: New Project → Deploy from GitHub repo → Dockerfile 자동 감지. Variables 탭에 위 환경변수 입력.
- **Fly.io**: `fly launch`(Dockerfile 감지) → `fly secrets set OHN_KAKAO_JS_KEY=... OHN_CORS_ORIGINS=https://timeleeh.github.io` → `fly deploy`.

## 배포 후 프론트 연결
GitHub Pages 목업에 백엔드 주소를 쿼리로 물려 사용:
```
https://timeleeh.github.io/ohun/?api=<배포URL>&group=<group_id>&user=<user_id>
https://timeleeh.github.io/ohun/kakao-poc.html?api=<배포URL>&group=<group_id>
```
- 카카오 키는 프론트에 박지 않아도 됨 → 프론트가 `<배포URL>/share/config`에서 받아감(키는 서버 `.env`에만).
- `OHN_CORS_ORIGINS`는 `https://timeleeh.github.io`로 좁혀둘 것.

## 카카오 개발자센터 설정(필수)
1. 애플리케이션 생성 → **JavaScript 키** 복사 → `OHN_KAKAO_JS_KEY`
2. 플랫폼 → Web → 사이트 도메인에 `https://timeleeh.github.io` 등록
3. 카카오 로그인 불필요(공유만 쓰면 sendDefault는 JS 키로 동작)

## 로컬에서 배포 이미지 그대로 검증
```bash
docker build -t chemisaju-api .
docker run --rm -p 8000:8000 -e OHN_KAKAO_JS_KEY=demo chemisaju-api
# http://127.0.0.1:8000/health , /share/<id>/card.png (한글 렌더 확인)
```

## 주의
- 인메모리 store는 재시작 시 그룹/운세가 사라짐 → 지속성이 필요하면 Supabase 환경변수 설정.
- 무료 플랜은 유휴 시 슬립 → 첫 요청 지연(카카오 스크랩 타임아웃 가능). 데모 시 한 번 워밍업.
- `.env_sub`(옛 키 백업)는 로컬에만 있고 이미지/깃에 안 들어가지만, 삭제 권장.
