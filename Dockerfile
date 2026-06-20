# 케미사주 API — 공개 호스팅용(Render/Railway/Fly 등 Docker 지원 호스트 공통)
FROM python:3.12-slim

# 공유 카드 SSR(PNG)에 한글 글리프 필요 → 서버에 한글 폰트 설치(fonts-nanum).
# app/share.py 가 /usr/share/fonts/truetype/nanum/ 경로를 자동 탐색한다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저(레이어 캐시)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드
COPY app ./app
COPY db ./db

# 기본값(호스트 콘솔의 환경변수로 덮어씀)
ENV OHN_PROVIDER=mock \
    OHN_CARD_FONT=/usr/share/fonts/truetype/nanum/NanumGothic.ttf \
    OHN_CARD_FONT_BOLD=/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf \
    PORT=8000

EXPOSE 8000
# 호스트가 주입하는 $PORT 에 바인딩(Render/Railway 등). 없으면 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
