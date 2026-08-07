"""简易资产库：水印 / 落版 / 叠加素材索引（路径或复制到库目录）。"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

AssetType = Literal["watermark", "endcard", "overlay", "other"]

TYPE_LABELS = {
    "watermark": "水印",
    "endcard": "落版",
    "overlay": "叠加",
    "other": "其他",
}


def _default_library() -> dict[str, Any]:
    return {"version": 1, "mode": "reference", "assets": []}


def library_path(config_path_fn) -> Path:
    return Path(config_path_fn("asset_library.json"))


def assets_dir(config_path_fn) -> Path:
    d = Path(config_path_fn("assets"))
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("watermarks", "endcards", "overlays", "other"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def load_library(config_path_fn) -> dict[str, Any]:
    p = library_path(config_path_fn)
    if not p.is_file():
        return _default_library()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_library()
        data.setdefault("version", 1)
        data.setdefault("mode", "reference")
        data.setdefault("assets", [])
        return data
    except Exception:
        return _default_library()


def save_library(config_path_fn, data: dict[str, Any]) -> None:
    p = library_path(config_path_fn)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def file_hash(path: str, limit: int = 2_000_000) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            chunk = f.read(limit)
            h.update(chunk)
            h.update(str(Path(path).stat().st_size).encode())
    except OSError:
        return ""
    return h.hexdigest()[:16]


def add_asset(
    config_path_fn,
    source_path: str,
    *,
    asset_type: AssetType = "other",
    name: str = "",
    mode: str | None = None,
    apply_target: str = "",
) -> dict[str, Any] | None:
    src = Path(source_path)
    if not src.is_file():
        return None
    lib = load_library(config_path_fn)
    use_mode = mode or str(lib.get("mode") or "reference")
    digest = file_hash(str(src))
    for a in lib.get("assets") or []:
        if isinstance(a, dict) and a.get("hash") == digest and a.get("type") == asset_type:
            return a  # 去重

    stored = ""
    if use_mode == "copy":
        sub = {
            "watermark": "watermarks",
            "endcard": "endcards",
            "overlay": "overlays",
        }.get(asset_type, "other")
        dest_dir = assets_dir(config_path_fn) / sub
        dest = dest_dir / f"{int(time.time())}_{src.name}"
        shutil.copy2(src, dest)
        stored = str(dest)

    item = {
        "id": str(uuid.uuid4())[:8],
        "name": (name or src.stem).strip(),
        "type": asset_type,
        "sourcePath": str(src.resolve()),
        "storedPath": stored,
        "hash": digest,
        "valid": True,
        "addedAt": time.strftime("%Y-%m-%d %H:%M"),
    }
    if (apply_target or "").strip():
        item["applyTarget"] = str(apply_target).strip()
    lib.setdefault("assets", []).append(item)
    if mode:
        lib["mode"] = use_mode
    save_library(config_path_fn, lib)
    return item


def resolve_asset_path(asset: dict[str, Any]) -> str:
    stored = (asset.get("storedPath") or "").strip()
    if stored and Path(stored).is_file():
        return stored
    src = (asset.get("sourcePath") or "").strip()
    return src


def validate_assets(config_path_fn) -> dict[str, Any]:
    lib = load_library(config_path_fn)
    changed = False
    for a in lib.get("assets") or []:
        if not isinstance(a, dict):
            continue
        path = resolve_asset_path(a)
        ok = bool(path) and Path(path).is_file()
        if bool(a.get("valid", True)) != ok:
            a["valid"] = ok
            changed = True
    if changed:
        save_library(config_path_fn, lib)
    return lib


def remove_asset(config_path_fn, asset_id: str) -> bool:
    lib = load_library(config_path_fn)
    before = len(lib.get("assets") or [])
    lib["assets"] = [a for a in (lib.get("assets") or []) if not (isinstance(a, dict) and a.get("id") == asset_id)]
    if len(lib["assets"]) == before:
        return False
    save_library(config_path_fn, lib)
    return True


def set_mode(config_path_fn, mode: str) -> None:
    lib = load_library(config_path_fn)
    if mode in {"copy", "reference", "ask"}:
        lib["mode"] = mode
        save_library(config_path_fn, lib)
