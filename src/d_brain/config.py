"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(description="Telegram Bot API token")
    deepgram_api_key: str = Field(description="Deepgram API key for transcription")
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude")
    todoist_api_key: str = Field(default="", description="Todoist API key for tasks")
    youtube_api_key: str = Field(default="", description="YouTube Data API v3 key")
    firecrawl_api_key: str = Field(default="", description="Firecrawl API key for web scraping")
    vault_path: Path = Field(
        default=Path("./vault"),
        description="Path to Obsidian vault directory",
    )
    allowed_user_ids: list[int] = Field(
        default_factory=list,
        description="List of Telegram user IDs allowed to use the bot",
    )
    allow_all_users: bool = Field(
        default=False,
        description="Whether to allow access to all users (security risk!)",
    )


    # Location (updated dynamically by /location command)
    location_city: str = Field(default="Москва", description="Current city name")
    location_lat: float = Field(default=55.75, description="Current latitude")
    location_lon: float = Field(default=37.62, description="Current longitude")
    location_tz: str = Field(default="Europe/Moscow", description="Current IANA timezone")

    @property
    def daily_path(self) -> Path:
        """Path to daily notes directory."""
        return self.vault_path / "daily"

    @property
    def attachments_path(self) -> Path:
        """Path to attachments directory."""
        return self.vault_path / "attachments"

    @property
    def thoughts_path(self) -> Path:
        """Path to thoughts directory."""
        return self.vault_path / "thoughts"


@lru_cache
def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()
