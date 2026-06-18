from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SETTINGS_PATH = Path("data/settings.json")

DEFAULT_SETTINGS: dict[str, Any] = {
    "image_preprocessing_enabled": True,
    "theme": "light",
}


def get_settings() -> dict[str, Any]:
    settings = DEFAULT_SETTINGS.copy()
    if SETTINGS_PATH.exists():
        try:
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(_normalize_settings(loaded))
        except (OSError, json.JSONDecodeError):
            pass
    return settings


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_settings()
    current.update(_normalize_settings(payload))
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def _normalize_settings(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if "image_preprocessing_enabled" in payload:
        normalized["image_preprocessing_enabled"] = bool(payload["image_preprocessing_enabled"])
    if "theme" in payload:
        theme = str(payload["theme"]).strip().lower()
        normalized["theme"] = "dark" if theme == "dark" else "light"
    return normalized
