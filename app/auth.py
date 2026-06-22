"""인증 어댑터: 토스 로그인(앱인토스) + 개발용 Mock.

토스 흐름 (앱인토스 개발자센터 문서 기준):
  프론트 appLogin() → authorizationCode + referrer
  서버:
    1) POST .../oauth2/generate-token (mTLS) → accessToken
    2) GET  .../oauth2/login-me  (Authorization: Bearer) → userKey + 암호화 PII
  name/birthday 등 PII는 AES-256-GCM(IV prefix)로 암호화되어 옴 → 콘솔 발급 키로 복호화.
  birthday는 yyyyMMdd (양력). userKey가 앱별 고정 사용자 식별자.

실제 호출은 사전 계약 + client_id + mTLS 인증서 + 복호화 키가 필요(콘솔 발급).
이들이 .env에 없으면 get_auth()는 MockAuth를 반환(로컬/테스트).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import settings


@dataclass
class AuthedUser:
    toss_user_id: str
    name: str
    birth_date: date


class MockAuth:
    """개발/테스트용. 외부 호출 없이 결정론적 사용자 반환."""

    def login(self, authorization_code: str, referrer: str = "DEFAULT") -> AuthedUser:
        return AuthedUser(
            toss_user_id=f"mock_{authorization_code}",
            name="홍길동",
            birth_date=date(1995, 3, 17),
        )


class TossAuth:
    """앱인토스 토스 로그인 실연동."""

    TOKEN_URL = "https://apps-in-toss-api.toss.im/api-partner/v1/apps-in-toss/user/oauth2/generate-token"
    ME_URL = "https://apps-in-toss-api.toss.im/api-partner/v1/apps-in-toss/user/oauth2/login-me"

    def __init__(self):
        import base64, tempfile, os
        # 파일 경로 우선, 없으면 base64 환경변수에서 임시파일로 생성(Render 등)
        cert_path = settings.toss_cert_path
        key_path = settings.toss_key_path
        if not cert_path and settings.toss_cert_b64:
            f = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
            f.write(base64.b64decode(settings.toss_cert_b64)); f.close()
            cert_path = f.name
        if not key_path and settings.toss_key_b64:
            f = tempfile.NamedTemporaryFile(delete=False, suffix=".key")
            f.write(base64.b64decode(settings.toss_key_b64)); f.close()
            key_path = f.name
        self._cert = (cert_path, key_path)
        self._referrer = settings.toss_referrer or "DEFAULT"
        self._key = base64.b64decode(settings.toss_decrypt_key) if settings.toss_decrypt_key else None

    def login(self, authorization_code: str, referrer: str | None = None) -> AuthedUser:
        import requests

        ref = referrer or self._referrer
        tok = requests.post(
            self.TOKEN_URL,
            json={"authorizationCode": authorization_code, "referrer": ref},
            cert=self._cert, timeout=10,
        ).json()
        access_token = tok["accessToken"]

        me = requests.get(
            self.ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            cert=self._cert, timeout=10,
        ).json()

        bday = self._decrypt(me.get("birthday"))  # yyyyMMdd
        return AuthedUser(
            toss_user_id=str(me["userKey"]),
            name=self._decrypt(me.get("name")) or "",
            birth_date=date(int(bday[:4]), int(bday[4:6]), int(bday[6:8])),
        )

    def _decrypt(self, b64: str | None) -> str | None:
        """AES-256-GCM(IV 12바이트 prefix + ciphertext + tag) 복호화.
        ※ 정확한 페이로드 포맷은 실제 토스 응답으로 1회 검증 필요."""
        if not b64 or not self._key:
            return b64
        import base64
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.b64decode(b64)
        iv, ct = raw[:12], raw[12:]
        return AESGCM(self._key).decrypt(iv, ct, None).decode("utf-8")


def get_auth():
    """mTLS 인증서(파일 or base64) + 복호화 키 있으면 TossAuth, 없으면 MockAuth."""
    has_cert = (settings.toss_cert_path and settings.toss_key_path) or \
               (settings.toss_cert_b64 and settings.toss_key_b64)
    if has_cert and settings.toss_decrypt_key:
        return TossAuth()
    return MockAuth()
