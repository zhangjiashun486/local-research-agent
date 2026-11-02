"""Repository-local model configuration, with explicit environment overrides."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def load_model_settings() -> dict[str, str]:
    configured_path = os.environ.get("LOCAL_RESEARCH_CONFIG")
    path = Path(configured_path).expanduser() if configured_path else ROOT / "local-model-connection.json"
    if configured_path and not path.is_file():
        raise ValueError("LOCAL_RESEARCH_CONFIG points to a missing file")
    data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    if not isinstance(data, dict):
        raise ValueError("Model configuration must be a JSON object")
    base_url = os.environ.get("LOCAL_RESEARCH_BASE_URL", data.get("base_url", "http://127.0.0.1:1235/v1"))
    model = os.environ.get("LOCAL_RESEARCH_MODEL", data.get("model", ""))
    if not isinstance(model, str) or not model.strip() or model == "YOUR_LOADED_MODEL_ID":
        raise ValueError("Set LOCAL_RESEARCH_MODEL or copy local-model-connection.example.json to local-model-connection.json and set model")
    if not isinstance(base_url, str):
        raise ValueError("Model base_url must be an HTTP(S) URL")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Model base_url must be an HTTP(S) URL")
    return {"base_url": base_url.rstrip("/"), "model": model.strip()}
