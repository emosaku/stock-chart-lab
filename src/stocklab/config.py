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
from pydantic import BaseModel, Field, field_validator, model_validator

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
    # Exchange calendar used to know which days should have a bar (XNYS = NYSE; the
    # Nasdaq-listed tickers here trade the same sessions).
    calendar: str = "XNYS"
    # Incremental runs re-fetch this many already-stored sessions. The overlap picks up
    # late corrections to recent bars and is compared against storage to detect
    # history restatements (see ingestion.pipeline).
    overlap_days: int = Field(default=5, ge=2)
    # Relative difference in close/adj_close on overlap days that counts as a restatement.
    restatement_tolerance: float = Field(default=1e-4, gt=0)
    # A daily adjusted-close move larger than this (0.25 = 25%) is flagged for review.
    max_daily_move: float = Field(default=0.25, gt=0)

    @field_validator("tickers")
    @classmethod
    def _normalise_tickers(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip().upper() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("at least one ticker is required")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("duplicate tickers in config")
        return cleaned

    @model_validator(mode="after")
    def _check_range(self) -> "DataSettings":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        return self


class MacdSettings(BaseModel):
    fast: int = Field(default=12, gt=0)
    slow: int = Field(default=26, gt=0)
    signal: int = Field(default=9, gt=0)

    @model_validator(mode="after")
    def _fast_below_slow(self) -> "MacdSettings":
        if self.fast >= self.slow:
            raise ValueError("macd.fast must be shorter than macd.slow")
        return self


class BollingerSettings(BaseModel):
    length: int = Field(default=20, gt=1)
    std: float = Field(default=2.0, gt=0)


class IndicatorSettings(BaseModel):
    sma_windows: list[int] = [20, 50, 200]
    ema_windows: list[int] = [20, 50, 200]
    rsi_length: int = Field(default=14, gt=1)
    macd: MacdSettings = MacdSettings()
    bollinger: BollingerSettings = BollingerSettings()
    atr_length: int = Field(default=14, gt=1)
    volume_ma_window: int = Field(default=20, gt=1)

    @field_validator("sma_windows", "ema_windows")
    @classmethod
    def _windows(cls, v: list[int]) -> list[int]:
        if any(w < 2 for w in v) or len(set(v)) != len(v):
            raise ValueError("windows must be distinct integers >= 2")
        return sorted(v)


class Settings(BaseModel):
    data: DataSettings
    indicators: IndicatorSettings = IndicatorSettings()
    # Typed properly when each phase lands; plain dicts until then.
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
