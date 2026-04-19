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

"""REST API routes for authentication (login, callback, logout)."""

import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

from app.auth.providers import (
    AuthState,
    create_provider,
    generate_pkce,
)
from app.auth.sessions import SessionStore
from app.config import AuthConfig

router = APIRouter(prefix="/api/auth", tags=["auth"])

_pending_states: dict[str, AuthState] = {}


def _get_auth_config() -> AuthConfig:
    from app.main import get_app_config
    return get_app_config().auth


def _get_enabled_providers(config: AuthConfig) -> list[str]:
    providers = []
    if config.github_client_id and config.github_client_secret:
        providers.append("github")
    if config.gitlab_client_id and config.gitlab_client_secret:
        providers.append("gitlab")
    if config.linkedin_client_id and config.linkedin_client_secret:
        providers.append("linkedin")
    return providers


@router.get("/providers")
async def list_providers() -> dict:
    """List available OIDC/OAuth providers."""
    config = _get_auth_config()
    providers = _get_enabled_providers(config)
    return {
        "enabled": config.enabled,
        "providers": providers,
    }


@router.get("/login/{provider}")
async def login(provider: str, request: Request) -> dict:
    """Start OAuth flow for a provider. Returns the authorization URL."""
    config = _get_auth_config()
    if not config.enabled:
        raise HTTPException(status_code=400, detail="Authentication is disabled")

    client_id, client_secret = _get_provider_credentials(config, provider)
    if not client_id:
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' is not configured")

    prov = create_provider(provider, client_id, client_secret)
    if not prov:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    redirect_uri = str(request.base_url) + "api/auth/callback/" + provider
    state_token = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce()

    auth_url = prov.build_authorization_url(redirect_uri, state_token, code_challenge)

    _pending_states[state_token] = AuthState(
        state_token=state_token,
        code_verifier=code_verifier,
        provider=provider,
        redirect_url=redirect_uri,
    )

    return {"authorization_url": auth_url, "state": state_token}


@router.get("/callback/{provider}")
async def callback(provider: str, code: str, state: str, response: Response) -> dict:
    """Handle OAuth callback from a provider."""
    config = _get_auth_config()

    auth_state = _pending_states.pop(state, None)
    if not auth_state or auth_state.provider != provider:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    client_id, client_secret = _get_provider_credentials(config, provider)
    prov = create_provider(provider, client_id, client_secret)

    token_resp = prov.exchange_code(code, auth_state.redirect_url, auth_state.code_verifier)
    user_info = prov.fetch_userinfo(token_resp.access_token)

    store = SessionStore(config)
    session_token = store.create_session(user_info)

    response = Response(
        content=f"<script>window.opener.postMessage({{token:'{session_token}',provider:'{provider}'}}, '*');window.close();</script>",
        media_type="text/html",
    )
    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        max_age=86400,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout(session_token: Optional[str] = None, response: Response = None) -> dict:
    """Invalidate the current session."""
    if session_token:
        config = _get_auth_config()
        store = SessionStore(config)
        store.destroy_session(session_token)
    response = Response(content='{"status":"ok"}', media_type="application/json")
    response.delete_cookie("session")
    return {"status": "ok"}


@router.get("/me")
async def get_me(session_token: Optional[str] = None) -> dict:
    """Get the current authenticated user."""
    if not session_token:
        return {"authenticated": False}
    config = _get_auth_config()
    store = SessionStore(config)
    session = store.validate_session(session_token)
    if not session:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user_id": session.get("user_id"),
        "display_name": session.get("display_name"),
        "email": session.get("email"),
        "provider": session.get("provider"),
    }


def _get_provider_credentials(config: AuthConfig, provider: str) -> tuple[Optional[str], Optional[str]]:
    if provider == "github":
        return config.github_client_id, config.github_client_secret
    elif provider == "gitlab":
        return config.gitlab_client_id, config.gitlab_client_secret
    elif provider == "linkedin":
        return config.linkedin_client_id, config.linkedin_client_secret
    return None, None
