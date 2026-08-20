from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlencode

import httpx

from src.config import get_settings

from .models import GitHubProfile
from .store import AuthStore


class GitHubOAuthError(RuntimeError):
    pass


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class GitHubOAuth:
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    user_url = "https://api.github.com/user"
    emails_url = "https://api.github.com/user/emails"

    def __init__(self, store: AuthStore) -> None:
        self.store = store
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.github_oauth_client_id and self.settings.github_oauth_client_secret)

    async def authorization_url(self) -> str:
        if not self.configured:
            raise GitHubOAuthError("GitHub OAuth is not configured")
        state, verifier = await self.store.create_oauth_state()
        query = urlencode(
            {
                "client_id": self.settings.github_oauth_client_id,
                "redirect_uri": self.settings.github_oauth_redirect_uri,
                "scope": "read:user user:email offline_access",
                "state": state,
                "code_challenge": pkce_challenge(verifier),
                "code_challenge_method": "S256",
                "allow_signup": "true",
            }
        )
        return f"{self.authorize_url}?{query}"

    async def callback(self, code: str, state: str) -> GitHubProfile:
        if not self.configured:
            raise GitHubOAuthError("GitHub OAuth is not configured")
        verifier = await self.store.consume_oauth_state(state)
        if verifier is None:
            raise GitHubOAuthError("Invalid or expired OAuth state")
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                self.token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.settings.github_oauth_client_id,
                    "client_secret": self.settings.github_oauth_client_secret,
                    "code": code,
                    "redirect_uri": self.settings.github_oauth_redirect_uri,
                    "code_verifier": verifier,
                },
            )
            token_response.raise_for_status()
            token = token_response.json().get("access_token")
            if not token:
                raise GitHubOAuthError("GitHub did not return an access token")
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
            user_response = await client.get(self.user_url, headers=headers)
            user_response.raise_for_status()
            user = user_response.json()
            email = user.get("email")
            if not email:
                emails_response = await client.get(self.emails_url, headers=headers)
                emails_response.raise_for_status()
                emails = emails_response.json()
                primary = next((item["email"] for item in emails if item.get("primary") and item.get("verified")), None)
                email = primary or next((item["email"] for item in emails if item.get("verified")), None)
        return GitHubProfile(github_id=str(user["id"]), login=str(user["login"]), email=email, avatar_url=user.get("avatar_url"))
