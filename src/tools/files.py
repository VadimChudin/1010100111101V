from __future__ import annotations
from pathlib import Path
from src.config import get_settings

def safe_path(relative: str) -> Path:
    root = Path(get_settings().workspace_root).resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise PermissionError("path escapes workspace")
    return target

def read_file(relative: str) -> str:
    return safe_path(relative).read_text(encoding="utf-8")

def write_file(relative: str, content: str) -> None:
    target = safe_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
