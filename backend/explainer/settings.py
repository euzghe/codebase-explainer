"""Pydantic settings — single source of truth for env config."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    github_token: str = ""

    max_repo_files: int = 300
    max_file_bytes: int = 100_000
    allowed_extensions: str = "py,ts,tsx,js,jsx,mjs"

    frontend_origin: str = "http://localhost:3000"

    @property
    def extensions(self) -> set[str]:
        return {e.strip().lstrip(".") for e in self.allowed_extensions.split(",")}


settings = Settings()
