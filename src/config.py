from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:8000"
    openrouter_app_name: str = "AI Agent Platform"
    default_model: str = "qwen/qwen-2-7b-instruct:free"
    request_timeout_s: float = 60.0
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
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

@lru_cache
def get_settings() -> Settings:
    return Settings()
