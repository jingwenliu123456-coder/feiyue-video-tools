"""叠加编辑器安全启动：配置校验、异常隔离"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from core.overlay_engine import describe_overlay_layers

logger = logging.getLogger(__name__)

DEFAULT_OVERLAY_STATE: dict[str, Any] = {
    "layers": {
        "bg": {"enabled": False, "path": "", "position": {"x": 0, "y": 0, "w": 480, "h": 270}},
        "video": {"enabled": True, "folder": "", "position": {"x": 0, "y": 0, "w": 480, "h": 270}},
        "logo": {"enabled": False, "path": "", "position": {"x": 0, "y": 0, "w": 100, "h": 100}},
    },
    "adapt_duration": True,
}


def sanitize_overlay_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return copy.deepcopy(DEFAULT_OVERLAY_STATE)
    out = copy.deepcopy(DEFAULT_OVERLAY_STATE)
    layers = state.get("layers")
    if isinstance(layers, dict):
        for key in ("bg", "video", "logo"):
            if isinstance(layers.get(key), dict):
                out["layers"][key].update(layers[key])
    if "adapt_duration" in state:
        out["adapt_duration"] = bool(state["adapt_duration"])
    return out


def backup_corrupt_config(path: Path) -> None:
    if path.is_file():
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            path.replace(bak)
        except OSError:
            pass


def load_overlay_state_safe(raw: Any) -> dict[str, Any]:
    try:
        return sanitize_overlay_state(raw)
    except Exception as e:
        logger.warning("overlay state sanitize failed: %s", e)
        return copy.deepcopy(DEFAULT_OVERLAY_STATE)


def safe_open_overlay_editor(
    parent,
    opener: Callable[..., Any],
    *,
    ffmpeg: str,
    ffprobe: str,
    initial_state: Any = None,
    output_dir: str = "",
    log_fn: Optional[Callable[[str], None]] = None,
    on_close: Optional[Callable[[dict], None]] = None,
    safe_mode: bool = False,
):
    """
    分阶段启动叠加编辑器，失败时给出中文操作建议。
    safe_mode=True 时使用默认空配置。
    """
    from tkinter import messagebox

    def _log_user(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    try:
        logger.info("overlay editor open start safe_mode=%s", safe_mode)
        _log_user("正在打开可视化叠加编辑器…")
        state = copy.deepcopy(DEFAULT_OVERLAY_STATE) if safe_mode else load_overlay_state_safe(initial_state)
        layer_desc = describe_overlay_layers(state)
        logger.info("overlay editor state ready layers=%s", list(state.get("layers", {}).keys()))
        if safe_mode:
            _log_user("已使用安全模式（空白方案）")
        else:
            _log_user(f"已加载叠加方案：{layer_desc}")
        win = opener(
            parent, ffmpeg, ffprobe,
            initial_state=state,
            output_dir=output_dir or "",
            log_fn=log_fn,
            on_close=on_close,
        )
        _log_user("可视化叠加编辑器已打开")
        logger.info("overlay editor window opened")
        return win
    except Exception as e:
        logger.exception("OverlayEditor startup failed")
        messagebox.showerror(
            "叠加编辑器启动失败",
            f"错误：{e}\n\n建议：\n"
            "1. 重启软件后再试\n"
            "2. 按住 Shift 再点「打开叠加编辑器」以安全模式启动\n"
            "3. 若仍失败，请把处理日志截图发给技术支持",
            parent=parent,
        )
        raise
