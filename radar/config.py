"""Configuration loading: config.yaml + .env, merged into one object."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"


class ConfigError(RuntimeError):
    pass


@dataclass
class Config:
    raw: dict[str, Any]
    api_key: str
    db_path: Path
    root: Path = field(default=ROOT)

    # --- convenience accessors -------------------------------------------------
    @property
    def api(self) -> dict[str, Any]:
        return self.raw.get("api", {})

    @property
    def ingest(self) -> dict[str, Any]:
        return self.raw.get("ingest", {})

    @property
    def signals(self) -> dict[str, Any]:
        return self.raw.get("signals", {})

    @property
    def report(self) -> dict[str, Any]:
        return self.raw.get("report", {})

    @property
    def watchlist_tcgplayer_ids(self) -> list[int]:
        wl = self.raw.get("watchlist") or {}
        return [int(x) for x in (wl.get("tcgplayer_ids") or [])]

    @property
    def base_url(self) -> str:
        return os.getenv("TCGAPI_BASE_URL") or self.api.get(
            "base_url", "https://api.tcgapi.dev/v1"
        )

    @property
    def game_slug(self) -> str:
        return self.api.get("game_slug", "gundam-card-game")

    def path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else self.root / p


def load_config(config_path: str | Path | None = None) -> Config:
    load_dotenv(ROOT / ".env")

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    api_key = os.getenv("TCGAPI_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "TCGAPI_KEY is not set. Copy .env.example to .env and add your "
            "tcgapi.dev key, or export TCGAPI_KEY in your shell."
        )

    db_path = Path(os.getenv("RADAR_DB", "data/radar.sqlite3"))
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(raw=raw, api_key=api_key, db_path=db_path)
