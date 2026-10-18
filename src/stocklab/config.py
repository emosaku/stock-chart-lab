"""Runtime configuration.

Two sources, kept separate on purpose:

- **Environment** (``.env`` locally, env vars on Cloud Run): *where* things live -- DB path,
  storage backend, GCP project. Changes between laptop and cloud.
- **settings.yaml**: *what* to analyse -- tickers, date ranges, indicator/model parameters.
  The same file is used everywhere, so a local run and a cloud run analyse the same thing.
"""

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GCP_REGION = os.getenv("GCP_REGION", "us-west1")
STOCKLAB_DB_PATH = os.getenv("STOCKLAB_DB_PATH", "data/stocklab.duckdb")
STOCKLAB_SETTINGS = os.getenv("STOCKLAB_SETTINGS", "config/settings.yaml")
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "duckdb")  # "duckdb" now, "bigquery" later
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "stocklab")


class DataSettings(BaseModel):
    tickers: list[str]
    start_date: date
    end_date: date | None = None

    @field_validator("tickers")
    @classmethod
    def _normalise_tickers(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip().upper() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("at least one ticker is required")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("duplicate tickers in config")
        return cleaned


class Settings(BaseModel):
    data: DataSettings
    # Typed properly when each phase lands; plain dicts until then.
    indicators: dict[str, Any] = {}
    signals: dict[str, Any] = {}
    backtest: dict[str, Any] = {}
    models: dict[str, Any] = {}


def resolve_path(path: str) -> Path:
    """Relative paths in config are relative to the project root, not the CWD."""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def load_settings(path: str | Path | None = None) -> Settings:
    """Parse and validate a settings file (defaults to ``STOCKLAB_SETTINGS``)."""
    settings_path = Path(path) if path else resolve_path(STOCKLAB_SETTINGS)
    with settings_path.open() as f:
        return Settings.model_validate(yaml.safe_load(f))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached project settings for normal runs; tests call ``load_settings`` directly."""
    return load_settings()
