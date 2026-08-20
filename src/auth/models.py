from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ProjectRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class AuthUser(BaseModel):
    id: str
    github_id: str
    login: str
    email: str | None = None
    avatar_url: str | None = None
    created_at: str


class AuthStatus(BaseModel):
    authenticated: bool
    user: AuthUser | None = None
    github_configured: bool


class GitHubProfile(BaseModel):
    github_id: str
    login: str
    email: str | None = None
    avatar_url: str | None = None
