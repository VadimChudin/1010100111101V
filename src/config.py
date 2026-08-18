"""Application configuration loaded from environment variables."""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_env: str = "development"
    log_level: str = "INFO"
    port: int = 8000
    openrouter_api_key: str = Field(default="", repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:8000"
    openrouter_app_title: str = "1010100111101V"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = Field(default="change-me", repr=False)
    neo4j_database: str = "neo4j"
    graphiti_enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_seconds: int = 86400
    database_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/agentdb"
    serena_mcp_url: str = "http://localhost:9121/mcp"
    serena_enabled: bool = False
    shell_command_timeout: int = 20
    shell_allowed_commands: str = "python,pytest,git,ls,pwd,cat,grep"

    @property
    def allowed_commands(self) -> set[str]:
        return {item.strip() for item in self.shell_allowed_commands.split(",") if item.strip()}

@lru_cache
def get_settings() -> Settings:
    return Settings()
