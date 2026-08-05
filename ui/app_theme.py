"""全应用统一界面皮肤（与批量裂变画布同源 + 无主题经典）。"""

from __future__ import annotations

from typing import Any

from modules.ui_skin import UI_THEME_NONE, UI_THEME_NONE_LABEL

APP_SKIN_ORDER = ("none", "workbench", "cream", "blue", "green", "dark")

APP_SKIN_LABELS: list[str] = [
    UI_THEME_NONE_LABEL,
    "简约工作台",
    "奶油可爱",
    "经典蓝白",
    "绿黄养眼",
    "黑紫赛博",
]

# 兼容旧导出
FISSION_SKIN_ORDER = tuple(k for k in APP_SKIN_ORDER if k != "none")
FISSION_SKIN_LABELS = [APP_SKIN_LABELS[i] for i, k in enumerate(APP_SKIN_ORDER) if k != "none"]

_THEMES: dict[str, dict[str, Any]] = {
    "workbench": {
        "label": "简约工作台",
        "bg": "#F2F2F7",
        "card": "#FFFFFF",
        "border": "#E5E5EA",
        "text": "#1C1C1E",
        "muted": "#8E8E93",
        "center": "#007AFF",
        "check": "#34C759",
        "line": "#D1D1D6",
        "scheme_fill": True,
        "scheme": ["#5AC8FA", "#007AFF", "#5856D6", "#FF9500", "#FF2D55", "#34C759", "#AF52DE"],
        "folder": ["#007AFF", "#34C759", "#FF9500", "#5856D6", "#FF2D55", "#5AC8FA"],
    },
    "cream": {
        "label": "奶油可爱",
        "bg": "#FFF9F5",
        "card": "#FFFFFF",
        "border": "#F0D9CC",
        "text": "#5C4B51",
        "muted": "#9B8B8F",
        "center": "#E8A0AE",
        "check": "#7BAE7F",
        "line": "#E8D0C4",
        "scheme_fill": True,
        "scheme": ["#B8D4C8", "#B4C9DC", "#C9B8D0", "#E8CDB0", "#E0B4B4", "#C5D4E0", "#DCC4CE"],
        "folder": ["#E0B4B4", "#E8CDB0", "#B8D4C8", "#B4C9DC", "#C9B8D0", "#DCC4CE"],
    },
    "blue": {
        "label": "经典蓝白",
        "bg": "#F0F4F8",
        "card": "#FFFFFF",
        "border": "#D0DCEC",
        "text": "#1E3A5F",
        "muted": "#64748B",
        "center": "#5B8FC7",
        "check": "#5A9A6A",
        "line": "#B8CCE0",
        "scheme_fill": True,
        "scheme": ["#7BA3C9", "#8B9BC7", "#9B8FBF", "#C99BB0", "#C9A07A", "#7BB0C4", "#7BAE8A"],
        "folder": ["#7BA3C9", "#8B9BC7", "#C99BB0", "#C9A07A", "#7BAE8A", "#9B8FBF"],
    },
    "green": {
        "label": "绿黄养眼",
        "bg": "#F5F7F0",
        "card": "#FFFFFF",
        "border": "#D2DEC4",
        "text": "#3A4A32",
        "muted": "#6E7A62",
        "center": "#7FA86A",
        "check": "#6B9A5A",
        "line": "#C5D4B0",
        "scheme_fill": True,
        "scheme": ["#9CB88A", "#C4B67A", "#8AAD7E", "#C9B06A", "#7AAD8E", "#A8C090", "#B8A86A"],
        "folder": ["#9CB88A", "#C4B67A", "#8AAD7E", "#C9B06A", "#7AAD8E", "#A8C090"],
    },
    "dark": {
        "label": "黑紫赛博",
        "bg": "#0A0A0F",
        "card": "#12121A",
        "border": "#2D2D44",
        "text": "#E8E8F0",
        "muted": "#9CA3AF",
        "center": "#8B6BB5",
        "check": "#5A9A6A",
        "line": "#4A4A60",
        "scheme_fill": False,
        "scheme": ["#8B6BB5", "#6B7AB5", "#B56B8F", "#7A6BB5", "#5B9AAA", "#B59A5B", "#5BAAA0"],
        "folder": ["#B58A5B", "#B56B6B", "#5BAAA0", "#B5A55B", "#6B8AB5", "#8B6BB5"],
    },
}

_CLASSIC: dict[str, Any] = {
    "label": UI_THEME_NONE_LABEL,
    "bg": "#F0F0F0",
    "card": "#FFFFFF",
    "border": "#C0C0C0",
    "text": "#000000",
    "muted": "#666666",
    "center": "#0078D7",
    "check": "#4CAF50",
    "line": "#D0D0D0",
    "scheme_fill": True,
    "scheme": ["#0078D7", "#4CAF50", "#FF9800", "#9C27B0", "#E91E63", "#009688", "#795548"],
    "folder": ["#0078D7", "#4CAF50", "#FF9800", "#9C27B0", "#E91E63", "#009688"],
}


def all_theme_dicts() -> dict[str, dict[str, Any]]:
    return {"none": _CLASSIC, **_THEMES}


def label_to_key(label: str) -> str:
    s = (label or "").strip()
    if s in (UI_THEME_NONE_LABEL, "无主题", "经典", "none"):
        return "none"
    for key, th in _THEMES.items():
        if th.get("label") == s:
            return key
    return "workbench"


def key_to_label(key: str) -> str:
    if key in ("none", UI_THEME_NONE):
        return UI_THEME_NONE_LABEL
    return str(_THEMES.get(key, _THEMES["workbench"]).get("label", "简约工作台"))


def theme_for_label(label: str) -> dict[str, Any]:
    key = label_to_key(label)
    if key == "none":
        return dict(_CLASSIC)
    return dict(_THEMES.get(key, _THEMES["workbench"]))


def theme_for_key(key: str) -> dict[str, Any]:
    if key in ("none", UI_THEME_NONE):
        return dict(_CLASSIC)
    return dict(_THEMES.get(key, _THEMES["workbench"]))


def is_none_skin(label: str) -> bool:
    return label_to_key(label) == "none"


def apply_palette_to_workbench(th: dict[str, Any]) -> dict[str, str]:
    from ui.workbench_skin import apply_theme_palette

    return apply_theme_palette(th)


def checkbox_selectcolor(th: dict[str, Any] | None = None) -> str:
    if th:
        return str(th.get("check") or "#34C759")
    try:
        from ui.workbench_skin import WB_CHECK

        return WB_CHECK
    except Exception:
        return "#34C759"
