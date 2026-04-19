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

"""OIDC provider configuration and token exchange."""

import base64
import hashlib
import secrets
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import urllib.request
import json


@dataclass
class OIDCConfig:
    """Configuration for a single OIDC provider."""

    provider_name: str
    client_id: str
    client_secret: str
    authorization_url: str
    token_url: str
    userinfo_url: str
    scope: str = "openid email profile"


@dataclass
class OIDCTokenResponse:
    """Parsed token response from an OIDC provider."""

    access_token: str
    token_type: str
    expires_in: int = 0
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


@dataclass
class OIDCUserInfo:
    """User profile from OIDC userinfo endpoint."""

    user_id: str
    display_name: str
    email: str
    provider: str
    avatar_url: Optional[str] = None


@dataclass
class AuthState:
    """Transient state stored during the OAuth redirect flow."""

    state_token: str
    code_verifier: str
    provider: str
    redirect_url: str


class OIDCProvider(ABC):
    """Abstract base class for OIDC providers."""

    @abstractmethod
    def get_config(self) -> OIDCConfig: ...

    @abstractmethod
    def build_authorization_url(self, redirect_uri: str, state: str, code_challenge: Optional[str] = None) -> str: ...

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str, code_verifier: Optional[str] = None) -> OIDCTokenResponse: ...

    @abstractmethod
    def fetch_userinfo(self, access_token: str) -> OIDCUserInfo: ...


class GitHubProvider(OIDCProvider):
    """GitHub OAuth2 provider (OAuth2, not strict OIDC)."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._config = OIDCConfig(
            provider_name="github",
            client_id=client_id,
            client_secret=client_secret,
            authorization_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
            scope="read:user user:email",
        )

    def get_config(self) -> OIDCConfig:
        return self._config

    def build_authorization_url(self, redirect_uri: str, state: str, code_challenge: Optional[str] = None) -> str:
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": redirect_uri,
            "scope": self._config.scope,
            "state": state,
        }
        return f"{self._config.authorization_url}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: Optional[str] = None) -> OIDCTokenResponse:
        payload = json.dumps({
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }).encode()
        req = urllib.request.Request(
            self._config.token_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return OIDCTokenResponse(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            scope=data.get("scope"),
        )

    def fetch_userinfo(self, access_token: str) -> OIDCUserInfo:
        req = urllib.request.Request(
            self._config.userinfo_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        user_id = str(data.get("id", ""))
        display_name = data.get("name") or data.get("login", "")
        email = data.get("email", "")

        if not email:
            emails_req = urllib.request.Request(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(emails_req) as emails_resp:
                emails = json.loads(emails_resp.read())
            primary = next((e for e in emails if e.get("primary")), None)
            if primary:
                email = primary.get("email", "")

        return OIDCUserInfo(
            user_id=f"github:{user_id}",
            display_name=display_name,
            email=email,
            provider="github",
            avatar_url=data.get("avatar_url"),
        )


class GitLabProvider(OIDCProvider):
    """GitLab OIDC provider."""

    def __init__(self, client_id: str, client_secret: str, base_url: str = "https://gitlab.com") -> None:
        self._base_url = base_url.rstrip("/")
        self._config = OIDCConfig(
            provider_name="gitlab",
            client_id=client_id,
            client_secret=client_secret,
            authorization_url=f"{self._base_url}/oauth/authorize",
            token_url=f"{self._base_url}/oauth/token",
            userinfo_url=f"{self._base_url}/api/v4/user",
            scope="read_user",
        )

    def get_config(self) -> OIDCConfig:
        return self._config

    def build_authorization_url(self, redirect_uri: str, state: str, code_challenge: Optional[str] = None) -> str:
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._config.scope,
            "state": state,
        }
        return f"{self._config.authorization_url}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: Optional[str] = None) -> OIDCTokenResponse:
        payload = urllib.parse.urlencode({
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request(
            self._config.token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return OIDCTokenResponse(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            expires_in=data.get("expires_in", 0),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
        )

    def fetch_userinfo(self, access_token: str) -> OIDCUserInfo:
        req = urllib.request.Request(
            self._config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return OIDCUserInfo(
            user_id=f"gitlab:{data.get('id', '')}",
            display_name=data.get("name") or data.get("username", ""),
            email=data.get("email", ""),
            provider="gitlab",
            avatar_url=data.get("avatar_url"),
        )


class LinkedInProvider(OIDCProvider):
    """LinkedIn OIDC provider."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._config = OIDCConfig(
            provider_name="linkedin",
            client_id=client_id,
            client_secret=client_secret,
            authorization_url="https://www.linkedin.com/oauth/v2/authorization",
            token_url="https://www.linkedin.com/oauth/v2/accessToken",
            userinfo_url="https://api.linkedin.com/v2/userinfo",
            scope="openid profile email",
        )

    def get_config(self) -> OIDCConfig:
        return self._config

    def build_authorization_url(self, redirect_uri: str, state: str, code_challenge: Optional[str] = None) -> str:
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._config.scope,
            "state": state,
        }
        return f"{self._config.authorization_url}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: Optional[str] = None) -> OIDCTokenResponse:
        payload = urllib.parse.urlencode({
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request(
            self._config.token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return OIDCTokenResponse(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            expires_in=data.get("expires_in", 0),
        )

    def fetch_userinfo(self, access_token: str) -> OIDCUserInfo:
        req = urllib.request.Request(
            self._config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        name = data.get("name", "")
        given = data.get("given_name", "")
        family = data.get("family_name", "")
        display_name = name or f"{given} {family}".strip()
        email = data.get("email", "")
        sub = data.get("sub", "")
        return OIDCUserInfo(
            user_id=f"linkedin:{sub}",
            display_name=display_name,
            email=email,
            provider="linkedin",
        )


def create_provider(provider_name: str, client_id: str, client_secret: str, **kwargs) -> Optional[OIDCProvider]:
    """Factory function to create an OIDC provider by name."""
    if provider_name == "github":
        return GitHubProvider(client_id, client_secret)
    elif provider_name == "gitlab":
        base_url = kwargs.get("base_url", "https://gitlab.com")
        return GitLabProvider(client_id, client_secret, base_url)
    elif provider_name == "linkedin":
        return LinkedInProvider(client_id, client_secret)
    return None


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge (S256 method).

    Returns:
        Tuple of (code_verifier, code_challenge).
    """
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge
