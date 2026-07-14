"""工具使用统计：埋点、年报数据、防打扰触发逻辑"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from modules.platform_utils import config_path

DB_PATH = config_path("tool_stats.db")
REPORT_CONFIG_PATH = config_path("annual_report_config.json")

# 操作类型
class OpType:
    VIDEO_CUT = "cut"
    RATIO = "ratio"
    AUDIO_REPLACE = "audio_replace"
    MOV_WM = "mov_wm"
    PNG_WM = "png_wm"
    LAYER = "layer"
    ADD_ENDING = "add_ending"
    OVERLAY = "overlay"
    RENAME = "rename"
    AUDIO_TOOLBOX = "audio_toolbox"
    BATCH = "batch"  # 综合批处理（兜底）


OP_LABELS: dict[str, str] = {
    OpType.VIDEO_CUT: "视频裁切",
    OpType.RATIO: "比例适配",
    OpType.AUDIO_REPLACE: "音频替换",
    OpType.MOV_WM: "MOV水印",
    OpType.PNG_WM: "PNG水印",
    OpType.LAYER: "浮层落版",
    OpType.ADD_ENDING: "拼接落版",
    OpType.OVERLAY: "叠加合成",
    OpType.RENAME: "规范命名",
    OpType.AUDIO_TOOLBOX: "音频工具箱",
    OpType.BATCH: "批量处理",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            op_type TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 1,
            details TEXT DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_ts ON operations(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_type ON operations(op_type)")
    return conn


def log_operation(op_type: str, count: int = 1, details: str = "") -> None:
    """记录一次成功操作（静默失败，不影响主流程）。"""
    try:
        n = int(count)
        if n <= 0:
            return
        conn = _connect()
        conn.execute(
            "INSERT INTO operations (timestamp, op_type, count, details) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), str(op_type), n, str(details or "")),
        )
        conn.commit()
        conn.close()
        _prune_old_records()
    except Exception:
        pass


def _prune_old_records() -> None:
    """只保留最近 2 年数据。"""
    try:
        cutoff = (datetime.now() - timedelta(days=730)).isoformat()
        conn = _connect()
        conn.execute("DELETE FROM operations WHERE timestamp < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------- 年报配置 ----------
def load_report_config() -> dict[str, Any]:
    try:
        if REPORT_CONFIG_PATH.is_file():
            with open(REPORT_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return {}


def save_report_config(cfg: dict[str, Any]) -> None:
    try:
        with open(REPORT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def has_data_for_year(year: int) -> bool:
    try:
        conn = _connect()
        start = f"{year}-01-01T00:00:00"
        end = f"{year + 1}-01-01T00:00:00"
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) FROM operations WHERE timestamp >= ? AND timestamp < ?",
            (start, end),
        ).fetchone()
        conn.close()
        return int(row[0] or 0) > 0
    except Exception:
        return False


def list_years_with_data() -> list[int]:
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT DISTINCT substr(timestamp, 1, 4) AS y FROM operations ORDER BY y DESC"
        ).fetchall()
        conn.close()
        return [int(r[0]) for r in rows if r and r[0] and str(r[0]).isdigit()]
    except Exception:
        return []


def get_unseen_years(last_seen: int) -> list[int]:
    return [y for y in list_years_with_data() if y > last_seen]


def _target_report_year(today: datetime | None = None) -> int:
    today = today or datetime.now()
    if today.month == 12 and today.day == 31:
        return today.year
    return today.year - 1


def _in_auto_window(today: datetime) -> bool:
    return (today.month == 12 and today.day == 31) or (today.month == 1 and today.day <= 7)


def should_show_report(today: datetime | None = None) -> tuple[bool, int]:
    """
    是否自动弹年报（防打扰版）。
    返回 (是否弹窗, 报告年份)
    """
    today = today or datetime.now()
    target_year = _target_report_year(today)
    cfg = load_report_config()

    if cfg.get("never_auto_popup", False):
        return False, target_year
    if not has_data_for_year(target_year):
        return False, target_year
    if int(cfg.get("last_seen_year", 0)) >= target_year:
        return False, target_year
    if int(cfg.get("auto_popup_shown_for_year", 0)) == target_year:
        return False, target_year
    if target_year in cfg.get("dismissed_years", []):
        return False, target_year
    if not _in_auto_window(today):
        return False, target_year

    cfg["auto_popup_shown_for_year"] = target_year
    save_report_config(cfg)
    return True, target_year


def mark_report_seen(year: int) -> None:
    cfg = load_report_config()
    cfg["last_seen_year"] = max(int(year), int(cfg.get("last_seen_year", 0)))
    save_report_config(cfg)


def dismiss_report(year: int, *, never_again: bool = False) -> None:
    cfg = load_report_config()
    if never_again:
        cfg["never_auto_popup"] = True
    else:
        dismissed = list(cfg.get("dismissed_years", []))
        if year not in dismissed:
            dismissed.append(year)
        cfg["dismissed_years"] = dismissed
    save_report_config(cfg)


def menu_report_label() -> str:
    cfg = load_report_config()
    last_seen = int(cfg.get("last_seen_year", 0))
    unseen = get_unseen_years(last_seen)
    label = "📊 年度工具年报"
    if unseen:
        label += f" · 未读{len(unseen)}"
    return label


def pick_manual_report_year() -> int | None:
    cfg = load_report_config()
    last_seen = int(cfg.get("last_seen_year", 0))
    for y in get_unseen_years(last_seen):
        return y
    years = list_years_with_data()
    if years:
        return years[0]
    return _target_report_year()


# ---------- 年报统计 ----------
@dataclass
class AnnualReportData:
    year: int
    total_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    busiest_month: tuple[int, int] = (0, 0)  # (month, count)
    busiest_day: tuple[str, int] = ("", 0)  # (iso date, count)
    latest_night: str = ""
    night_ops: int = 0
    streak_days: int = 0
    first_use: str = ""
    titles: list[str] = field(default_factory=list)


def _query_year(year: int) -> list[tuple[str, str, int, str]]:
    conn = _connect()
    start = f"{year}-01-01T00:00:00"
    end = f"{year + 1}-01-01T00:00:00"
    rows = conn.execute(
        "SELECT timestamp, op_type, count, details FROM operations WHERE timestamp >= ? AND timestamp < ?",
        (start, end),
    ).fetchall()
    conn.close()
    return [(str(a), str(b), int(c), str(d or "")) for a, b, c, d in rows]


def generate_annual_report_data(year: int) -> AnnualReportData:
    rows = _query_year(year)
    data = AnnualReportData(year=year)
    if not rows:
        return data

    by_type: dict[str, int] = {}
    by_month: dict[int, int] = {}
    by_day: dict[str, int] = {}
    active_days: set[str] = set()
    night_ops = 0
    latest_night = ""
    first_ts = rows[0][0]

    for ts, op_type, count, _details in rows:
        if ts < first_ts:
            first_ts = ts
        by_type[op_type] = by_type.get(op_type, 0) + count
        data.total_count += count
        try:
            dt = datetime.fromisoformat(ts)
            by_month[dt.month] = by_month.get(dt.month, 0) + count
            day_key = dt.date().isoformat()
            by_day[day_key] = by_day.get(day_key, 0) + count
            active_days.add(day_key)
            if dt.hour >= 23 or dt.hour < 5:
                night_ops += count
                if not latest_night or ts > latest_night:
                    latest_night = ts
        except ValueError:
            pass

    data.by_type = by_type
    data.first_use = first_ts[:10] if first_ts else ""
    data.night_ops = night_ops
    data.latest_night = latest_night
    if by_month:
        m, c = max(by_month.items(), key=lambda x: x[1])
        data.busiest_month = (m, c)
    if by_day:
        d, c = max(by_day.items(), key=lambda x: x[1])
        data.busiest_day = (d, c)
    data.streak_days = _max_streak(sorted(active_days))
    data.titles = _build_titles(data)
    return data


def _max_streak(sorted_days: list[str]) -> int:
    if not sorted_days:
        return 0
    best = cur = 1
    prev = datetime.fromisoformat(sorted_days[0]).date()
    for s in sorted_days[1:]:
        d = datetime.fromisoformat(s).date()
        if (d - prev).days == 1:
            cur += 1
        else:
            cur = 1
        best = max(best, cur)
        prev = d
    return best


def _build_titles(data: AnnualReportData) -> list[str]:
    titles: list[str] = []
    if data.total_count >= 500:
        titles.append("🏆 肝帝")
    elif data.total_count >= 100:
        titles.append("⚡ 高产选手")
    if data.night_ops >= 10:
        titles.append("🌙 夜猫子")
    if data.streak_days >= 7:
        titles.append("🔥 连续作战")
    rename_n = data.by_type.get(OpType.RENAME, 0)
    if rename_n > 0 and rename_n >= data.total_count * 0.4:
        titles.append("🏷️ 命名达人")
    overlay_n = data.by_type.get(OpType.OVERLAY, 0) + data.by_type.get(OpType.MOV_WM, 0)
    if overlay_n >= 50:
        titles.append("🎨 叠加大师")
    if not titles:
        titles.append("🎬 剪辑同行者")
    return titles


def log_batch_processing(app: Any, success_count: int, failed_count: int = 0) -> None:
    """根据批处理启用的模块记录埋点。"""
    if success_count <= 0:
        return
    detail = f"失败:{failed_count}"
    checks = [
        ("cut_enable", OpType.VIDEO_CUT),
        ("ratio_enable", OpType.RATIO),
        ("enable_mov_watermark", OpType.MOV_WM),
        ("png_wm_enable", OpType.PNG_WM),
        ("logo_enable", OpType.LAYER),
        ("ending_enable", OpType.ADD_ENDING),
        ("overlay_enable", OpType.OVERLAY),
    ]
    logged = False
    for attr, op in checks:
        var = getattr(app, attr, None)
        try:
            if var is not None and bool(var.get()):
                log_operation(op, success_count, detail)
                logged = True
        except Exception:
            pass
    if not logged:
        log_operation(OpType.BATCH, success_count, detail)
