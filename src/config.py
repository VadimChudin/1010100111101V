from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:8000"
    openrouter_app_name: str = "AI Agent Platform"
    default_model: str = "qwen/qwen-2-7b-instruct:free"
    request_timeout_s: float = 60.0
    openrouter_attempt_timeout_s: float = 20.0
    openrouter_max_fallback_models: int = 3
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "neo4j://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agent"
    state_database_path: str = "./data/agent-state.db"
    workspace_root: str = "/workspace"
    max_tool_output_chars: int = 12000
    enable_unsafe_shell: bool = False
    sentry_dsn: str = ""
    observability_enabled: bool = True
    auth_required: bool = False
    session_secret: str = ""
    session_cookie_name: str = "agent_platform_session"
    frontend_origins: str = "http://localhost:5173,https://frontend-swart-alpha-20.vercel.app"
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    github_oauth_redirect_uri: str = "https://app-production-cc16.up.railway.app/v1/auth/github/callback"
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 15
    worker_max_attempts: int = 3
    worker_shutdown_grace_seconds: int = 30
    worker_recovery_batch_size: int = 50
    worker_recovery_interval_seconds: int = 30
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

@lru_cache
def get_settings() -> Settings:
    return Settings()
