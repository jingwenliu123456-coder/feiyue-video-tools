# -*- coding: utf-8 -*-
"""HabiVideoTool 全局记忆空间（用户偏好，跨会话）。"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from modules.platform_utils import habi_tool_config_path

MEMORY_VERSION = 1

_DEFAULTS: dict[str, Any] = {
    "version": MEMORY_VERSION,
    "user_preferences": {
        "default_tab": "视频批处理",  # 视频批处理 | 规范命名 | 批量裂变
        "default_view": "思维导图",  # 思维导图 | 地铁线路 | 列表
        "default_theme": "奶油可爱",
        # 快速启动：不自动加载 | 上次使用的方案 | 具体方案模板名（templates/*.json）
        "batch_autoload": "不自动加载",
        "fission_autoload": "不自动加载",
        "last_used_scheme": "",
        "default_output_path": "",
        "naming_template": "{scheme}_{date}_{index}",
        "pipeline_order": [],
        "auto_open_naming_after_fission": False,
        "preview_panel_open": False,
        "show_tips": True,
        # 批处理前整夹备份到 .backup/（默认关，避免输出一多就极慢）
        "batch_backup_enable": False,
        # 裂变页：单源多分支 | 多源多分支（分开界面）
        "fission_io_mode": "单源",

        # 裂变「通用预处理」：先跑一次模板，再并行裂变
        "fission_preprocess_enable": False,
        "fission_preprocess_template": "",
        "fission_preprocess_temp_mode": "自动清理",  # 自动清理 | 保留 | 指定路径
        "fission_preprocess_temp_path": "",
    },
    "window_state": {
        "width": 1400,
        "height": 900,
        "maximized": False,
    },
}

_TAB_INDEX = {
    "视频批处理": 0,
    "规范命名": 1,
    "批量裂变": 2,
}


def memory_path() -> Path:
    """与 habi_tool_config_path 同目录，单独文件避免冲掉旧命名配置。"""
    return habi_tool_config_path().parent / "preferences.json"


def default_memory() -> dict[str, Any]:
    return deepcopy(_DEFAULTS)


def load_memory() -> dict[str, Any]:
    path = memory_path()
    data = default_memory()
    if not path.is_file():
        # 兼容旧版本地 v24_ui_prefs
        return _merge_legacy_local(data)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return data
        return _merge(data, raw)
    except (OSError, json.JSONDecodeError, TypeError):
        return data


def save_memory(data: dict[str, Any]) -> None:
    path = memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out = _merge(default_memory(), data if isinstance(data, dict) else {})
    out["version"] = MEMORY_VERSION
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def prefs(data: dict[str, Any] | None = None) -> dict[str, Any]:
    mem = data if isinstance(data, dict) else load_memory()
    p = mem.get("user_preferences")
    return p if isinstance(p, dict) else dict(_DEFAULTS["user_preferences"])


def tab_index(name: str) -> int:
    return int(_TAB_INDEX.get((name or "").strip(), 0))


def update_prefs(**kwargs: Any) -> dict[str, Any]:
    mem = load_memory()
    up = prefs(mem)
    for k, v in kwargs.items():
        if v is not None:
            up[k] = v
    mem["user_preferences"] = up
    save_memory(mem)
    return mem


AUTOLOAD_NONE = "不自动加载"
AUTOLOAD_LAST = "上次使用的方案"


def resolve_autoload_scheme(
    pref: dict[str, Any] | None = None,
    *,
    key: str = "fission_autoload",
) -> str:
    """返回应自动加载的方案模板名；空字符串表示不加载。

    key: batch_autoload | fission_autoload
    """
    p = pref if isinstance(pref, dict) else prefs()
    mode = str(p.get(key) or AUTOLOAD_NONE).strip()
    if not mode or mode == AUTOLOAD_NONE:
        return ""
    if mode == AUTOLOAD_LAST:
        return str(p.get("last_used_scheme") or "").strip()
    return mode


def remember_scheme(name: str) -> None:
    """记住上次使用的方案模板名（供「上次使用的方案」）。"""
    n = (name or "").strip()
    if not n or n in (AUTOLOAD_NONE, AUTOLOAD_LAST):
        return
    update_prefs(last_used_scheme=n)


def update_window_state(*, width: int, height: int, maximized: bool = False) -> None:
    mem = load_memory()
    mem["window_state"] = {
        "width": max(800, int(width)),
        "height": max(600, int(height)),
        "maximized": bool(maximized),
    }
    save_memory(mem)


def _merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


def _merge_legacy_local(data: dict[str, Any]) -> dict[str, Any]:
    """把旧的 app 目录 v24_ui_prefs 迁进全局记忆（只读一次）。"""
    try:
        from modules.platform_utils import config_path

        p = Path(config_path("v24_ui_prefs.json"))
        if not p.is_file():
            return data
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "preview_panel_open" in raw:
            data["user_preferences"]["preview_panel_open"] = bool(raw.get("preview_panel_open"))
    except Exception:
        pass
    return data
