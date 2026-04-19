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

"""FastAPI dependency for authentication."""

import secrets
from typing import Optional

from fastapi import Cookie, HTTPException, Request

from app.auth.sessions import SessionStore
from app.config import AuthConfig


def get_session_store() -> Optional[SessionStore]:
    from app.main import get_app_config
    cfg = get_app_config()
    if not cfg.auth.enabled:
        return None
    return SessionStore(cfg.auth)


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias="session"),
) -> Optional[dict]:
    """FastAPI dependency that returns the current user session.

    Returns None if auth is disabled or no valid session.
    Raises HTTPException(401) if auth is enabled but session is invalid.
    """
    from app.main import get_app_config
    cfg = get_app_config()

    if not cfg.auth.enabled:
        return None

    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    store = SessionStore(cfg.auth)
    session = store.validate_session(session_token)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return session


async def optional_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias="session"),
) -> Optional[dict]:
    """FastAPI dependency that returns the user session or None."""
    from app.main import get_app_config
    cfg = get_app_config()

    if not cfg.auth.enabled:
        return None

    if not session_token:
        return None

    store = SessionStore(cfg.auth)
    return store.validate_session(session_token)
