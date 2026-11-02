"""Config loading and arm lookup."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    return yaml.safe_load(path.read_text())


def get_arm(cfg: dict, name: str) -> dict:
    for arm in cfg["arms"]:
        if arm["name"] == name:
            return arm
    names = ", ".join(a["name"] for a in cfg["arms"])
    raise SystemExit(f"Unknown arm {name!r}. Arms in config.yaml: {names}")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p
