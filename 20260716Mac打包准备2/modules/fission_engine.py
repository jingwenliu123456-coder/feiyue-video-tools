"""批量裂变引擎：分支表 = 方案模板工作流列表。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


FISSION_SCHEMA_VERSION = 1

# 裂变功能键 → 批处理流水线步骤键（与 VideoBatchToolV21._BATCH_PIPELINE_DEFAULT 对齐）
ENABLE_KEY_TO_STEP: dict[str, str] = {
    "cut_enable": "cut",
    "enhance_enable": "enhance",
    "ratio_enable": "ratio",
    "enable_mov_watermark": "mov_wm",
    "png_wm_enable": "png_wm",
    "logo_enable": "layer",
    "layer_enable": "layer",
    "ending_enable": "ending",
    "overlay_enable": "overlay",
}

_DEFAULT_PIPELINE_STEPS: tuple[str, ...] = (
    "cut", "enhance", "ratio", "mov_wm", "png_wm", "layer", "ending", "overlay",
)


def pipeline_steps_from_fission_order(
    order: Any,
    *,
    default_steps: tuple[str, ...] | list[str] | None = None,
) -> Optional[list[str]]:
    """把 `_fission_func_order`（enable 键列表）转成真实处理步骤顺序。

    未出现在 order 里的默认步骤追加到末尾，避免漏跑。
    若 order 无效则返回 None（调用方继续用默认/布局顺序）。
    """
    defaults = list(default_steps or _DEFAULT_PIPELINE_STEPS)
    if not isinstance(order, list) or not order:
        return None
    steps: list[str] = []
    for key in order:
        sk = ENABLE_KEY_TO_STEP.get(str(key))
        if sk and sk not in steps:
            steps.append(sk)
    if not steps:
        return None
    for sk in defaults:
        if sk not in steps:
            steps.append(sk)
    return steps


def sanitize_branch_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s or "branch"


@dataclass
class FissionBranch:
    """一行分支 = 一套完整方案模板（引用名或内嵌快照）。"""

    enabled: bool = True
    branch_name: str = ""
    template_name: str = ""  # 引用 templates/*.json 的文件名（无后缀）
    embedded_config: Optional[dict[str, Any]] = None  # 自建快照；优先于 template_name
    note: str = ""

    def display_source(self) -> str:
        if self.embedded_config:
            return "自建快照"
        if self.template_name:
            return f"模板:{self.template_name}"
        return "（未绑定）"


@dataclass
class FissionPlan:
    version: int = FISSION_SCHEMA_VERSION
    name: str = "未命名裂变方案"
    branches: list[FissionBranch] = field(default_factory=list)

    def enabled_branches(self) -> list[FissionBranch]:
        return [b for b in self.branches if b.enabled and sanitize_branch_name(b.branch_name)]


def branch_to_dict(b: FissionBranch) -> dict[str, Any]:
    d: dict[str, Any] = {
        "enabled": bool(b.enabled),
        "branch_name": sanitize_branch_name(b.branch_name),
        "template_name": (b.template_name or "").strip(),
        "note": b.note or "",
    }
    if b.embedded_config and isinstance(b.embedded_config, dict):
        d["embedded_config"] = b.embedded_config
    return d


def branch_from_dict(d: dict[str, Any]) -> FissionBranch:
    emb = d.get("embedded_config")
    return FissionBranch(
        enabled=bool(d.get("enabled", True)),
        branch_name=sanitize_branch_name(str(d.get("branch_name") or "")),
        template_name=str(d.get("template_name") or "").strip(),
        embedded_config=emb if isinstance(emb, dict) else None,
        note=str(d.get("note") or ""),
    )


def plan_to_dict(plan: FissionPlan) -> dict[str, Any]:
    return {
        "version": int(plan.version or FISSION_SCHEMA_VERSION),
        "name": plan.name or "未命名裂变方案",
        "branches": [branch_to_dict(b) for b in plan.branches],
    }


def plan_from_dict(data: dict[str, Any]) -> FissionPlan:
    if not isinstance(data, dict):
        return FissionPlan()
    raw = data.get("branches") or []
    branches = [branch_from_dict(x) for x in raw if isinstance(x, dict)]
    return FissionPlan(
        version=int(data.get("version") or FISSION_SCHEMA_VERSION),
        name=str(data.get("name") or "未命名裂变方案"),
        branches=branches,
    )


def save_fission_plan(path: str | Path, plan: FissionPlan) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan_to_dict(plan), ensure_ascii=False, indent=2), encoding="utf-8")


def load_fission_plan(path: str | Path) -> FissionPlan:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return plan_from_dict(data if isinstance(data, dict) else {})


def resolve_branch_config(
    branch: FissionBranch,
    *,
    templates_dir: Path,
) -> dict[str, Any]:
    """返回该分支要应用的完整配置 dict。"""
    if branch.embedded_config and isinstance(branch.embedded_config, dict):
        return dict(branch.embedded_config)
    name = (branch.template_name or "").strip()
    if not name:
        raise ValueError(f"分支「{branch.branch_name}」未绑定模板，也无自建快照")
    path = templates_dir / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"方案模板不存在: {path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"方案模板格式无效: {path.name}")
    return data


def list_template_names(templates_dir: Path) -> list[str]:
    if not templates_dir.is_dir():
        return []
    return sorted(p.stem for p in templates_dir.glob("*.json") if p.is_file())


def renumber_files_in_folder(
    folder: str | Path,
    *,
    start_index: int = 1,
    index_width: int = 3,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """
    将文件夹内媒体文件按当前排序重编号：把文件名开头的数字序号换成新序号。
    若文件名不以数字-开头，则在前面加序号前缀。
    返回 [(old_name, new_name), ...]
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(str(folder))
    exts = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".webm",
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    files = sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in exts
    )
    changes: list[tuple[str, str]] = []
    idx = max(0, int(start_index))
    width = max(1, min(8, int(index_width)))
    pending: list[tuple[Path, Path]] = []

    for f in files:
        stem, ext = f.stem, f.suffix
        m = re.match(r"^(\d+)([-_].*)$", stem)
        if m:
            new_stem = f"{idx:0{width}d}{m.group(2)}"
        else:
            new_stem = f"{idx:0{width}d}-{stem}"
        new_name = new_stem + ext
        if new_name != f.name:
            changes.append((f.name, new_name))
            pending.append((f, folder / new_name))
        idx += 1

    if dry_run:
        return changes

    # 两阶段改名，避免覆盖
    temps: list[tuple[Path, Path]] = []
    for src, dst in pending:
        tmp = src.with_name(f".__renum_{src.name}")
        src.rename(tmp)
        temps.append((tmp, dst))
    for tmp, dst in temps:
        if dst.exists():
            tmp.rename(tmp.with_name(tmp.name + ".conflict"))
            raise FileExistsError(f"目标已存在: {dst.name}")
        tmp.rename(dst)
    return changes
