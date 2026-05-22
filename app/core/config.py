from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OptiProcess API"
    app_version: str = "1.1.0"
    app_description: str = "API dedicada para processamento de imagens, OCR, IA visual e exportacao SVG."
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    openai_api_key: str | None = None
    api_key: str | None = None
    webhook_signing_secret: str | None = None
    webhook_timeout_seconds: float = 5.0
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "OPEMAI_MODEL"),
    )
    ocr_min_confidence: float = 0.75
    ocr_min_text_length: int = 15
    max_upload_mb: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | List[str]) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
