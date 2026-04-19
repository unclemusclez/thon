# Copyright 2025 Alibaba Group Holding Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Session management for authenticated dashboard users."""

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional

from app.auth.providers import OIDCUserInfo
from app.config import AuthConfig
from app.exceptions import AuthError


class SessionStore:
    """In-memory session store with optional file persistence.

    Sessions are stored as signed JSON tokens. In production, replace
    with Redis or database-backed session storage.
    """

    TOKEN_VERSION = "v1"

    def __init__(self, config: AuthConfig) -> None:
        self._config = config
        self._sessions: dict[str, dict] = {}

    def create_session(self, user: OIDCUserInfo, ttl_seconds: int = 86400) -> str:
        """Create a new session and return a session token."""
        session_id = hashlib.sha256(f"{user.user_id}:{time.time()}".encode()).hexdigest()[:32]
        expires_at = time.time() + ttl_seconds
        self._sessions[session_id] = {
            "user_id": user.user_id,
            "display_name": user.display_name,
            "email": user.email,
            "provider": user.provider,
            "avatar_url": user.avatar_url,
            "created_at": time.time(),
            "expires_at": expires_at,
        }
        return self._sign_token(session_id)

    def validate_session(self, token: str) -> Optional[dict]:
        """Validate a session token and return session data, or None."""
        session_id = self._verify_token(token)
        if not session_id:
            return None
        session = self._sessions.get(session_id)
        if not session:
            return None
        if time.time() > session.get("expires_at", 0):
            del self._sessions[session_id]
            return None
        return session

    def destroy_session(self, token: str) -> None:
        """Invalidate a session token."""
        session_id = self._verify_token(token)
        if session_id and session_id in self._sessions:
            del self._sessions[session_id]

    def _sign_token(self, session_id: str) -> str:
        secret = self._config.session_secret
        if not secret:
            secret = "insecure-default-change-me"
        payload = f"{self.TOKEN_VERSION}:{session_id}"
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        return f"{payload}:{sig}"

    def _verify_token(self, token: str) -> Optional[str]:
        secret = self._config.session_secret
        if not secret:
            secret = "insecure-default-change-me"
        parts = token.split(":")
        if len(parts) != 3:
            return None
        version, session_id, sig = parts
        if version != self.TOKEN_VERSION:
            return None
        expected_payload = f"{version}:{session_id}"
        expected_sig = hmac.new(secret.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return session_id
