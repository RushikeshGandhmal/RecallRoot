from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CsvList = Annotated[list[str], NoDecode, BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RECALLGRAPH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RecallRoot API"
    environment: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./recallroot.db"
    cors_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    trusted_refund_threshold: float = 10_000.0
    decision_provider: Literal["deterministic", "ollama"] = "deterministic"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = Field(default=12.0, gt=0, le=60)

    telemetry_service_name: str = "recallroot-api"
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "RECALLGRAPH_OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"
        ),
    )
    otel_exporter_otlp_headers: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "RECALLGRAPH_OTEL_EXPORTER_OTLP_HEADERS", "OTEL_EXPORTER_OTLP_HEADERS"
        ),
    )
    otel_export_timeout_seconds: float = 3.0

    signoz_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RECALLGRAPH_SIGNOZ_API_URL", "SIGNOZ_API_URL", "SIGNOZ_URL"),
    )
    signoz_ui_url: str = Field(
        default="http://localhost:3301",
        validation_alias=AliasChoices("RECALLGRAPH_SIGNOZ_UI_URL", "SIGNOZ_UI_URL", "SIGNOZ_URL"),
    )
    signoz_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RECALLGRAPH_SIGNOZ_API_KEY", "SIGNOZ_API_KEY"),
    )
    signoz_query_path: str = "/api/v5/query_range"
    signoz_query_lookback_hours: int = 24
    signoz_timeout_seconds: float = 2.5
    signoz_mcp_url: str | None = Field(
        default="http://localhost:8001/mcp",
        validation_alias=AliasChoices("RECALLGRAPH_SIGNOZ_MCP_URL", "SIGNOZ_MCP_URL"),
    )
    signoz_mcp_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "RECALLGRAPH_SIGNOZ_MCP_API_KEY", "SIGNOZ_MCP_API_KEY", "SIGNOZ_API_KEY"
        ),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
