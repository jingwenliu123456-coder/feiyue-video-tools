"""命名规范：模板、解析、配置持久化"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from modules.platform_utils import habi_tool_config_path

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v", ".webm"}

BRAND_PRESETS = ("habi", "sami")
LANG_PRESETS = ("ar", "tr", "en", "id")
TYPE_PRESETS = ("chat", "game")
SIZE_PRESETS = ("9x16", "916", "16x9", "169", "4x5", "45", "1x1", "11")
SIZE_SHORTHAND = {"916": "9x16", "169": "16x9", "11": "1x1", "45": "4x5"}
DESIGNER_PRESETS = ("zsa", "zzy", "ljw")
CUSTOM_OPTION = "自定义..."
COMBO_SEP = "──────────"
FIXED_VIDEO = "video"
EMPTY_TAG = "___EMPTY_TAG___"
MAX_CUSTOM_TAGS = 10

DEFAULT_TEMPLATE = "{序号}-{品牌}-video-{语言}-{类型}-{标签}-{尺寸}-{日期}-{设计师}.mp4"
INVALID_DATE = "00000000"
WIN_ILLEGAL = re.compile(r'[\\/:*?"<>|]')

DEFAULT_TAG_LIBRARY: list[str] = [
    "首充优惠", "金色玫瑰", "美女诱导", "爆元素", "Luckyslot",
    "真人实拍", "情侣", "KOL", "火箭", "荣誉圣殿",
    "黑暗房间实拍", "美女前贴", "情侣礼物", "1刀首充", "爆金币",
    "luckshot", "游戏", "语音房", "实拍",
]


@dataclass
class NamingFields:
    brand: str = "habi"
    lang: str = "ar"
    type_: str = "chat"
    tags: list[str] = field(default_factory=lambda: ["", "", ""])
    size: str = "9x16"
    date: str = ""
    designer: str = "ljw"
    template: str = DEFAULT_TEMPLATE

    def normalized_tags(self) -> list[str]:
        out: list[str] = []
        for t in self.tags:
            t = (t or "").strip()
            if t and t not in out:
                out.append(t)
        return out[:3]


@dataclass
class ParsedLegacy:
    original: str
    index: Optional[int] = None
    brand: str = ""
    lang: str = ""
    type_: str = ""
    tags: list[str] = field(default_factory=list)
    size: str = ""
    date: str = ""
    designer: str = ""
    non_standard_tags: list[str] = field(default_factory=list)
    date_valid: bool = True
    parse_ok: bool = False


def today_date_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def sanitize_no_dash(value: str) -> str:
    return (value or "").strip().replace("-", "_")


def normalize_brand(value: str) -> str:
    v = sanitize_no_dash(value).lower()
    return v or "habi"


def normalize_date(value: str) -> tuple[str, bool]:
    v = re.sub(r"\D", "", (value or "").strip())
    if len(v) >= 8:
        v = v[:8]
        if v.isdigit():
            return v, True
    if len(v) == 4 and v.isdigit():
        year = datetime.now().strftime("%Y")
        return f"{year}{v}", True
    if not v:
        return today_date_str(), True
    return INVALID_DATE, False


def date_display_4(value: str) -> str:
    v, ok = normalize_date(value)
    if not ok:
        return "0000"
    return v[-4:] if len(v) >= 4 else v


def format_index(index: int, width: int = 3) -> str:
    w = max(1, min(4, int(width or 3)))
    return f"{index:0{w}d}"


def normalize_size(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        return "9x16"
    compact = re.sub(r"[^0-9x]", "", v.replace("_", "x"))
    if v in SIZE_SHORTHAND:
        return v
    if compact in SIZE_PRESETS:
        return compact
    if re.fullmatch(r"\d+x\d+", compact):
        return compact
    if compact in SIZE_SHORTHAND:
        return compact
    return v


def validate_template(template: str) -> Optional[str]:
    t = (template or "").strip()
    if "{序号}" not in t:
        return "模板必须包含 {序号}，否则文件会重名"
    if not t.lower().endswith(".mp4"):
        return "模板必须以 .mp4 结尾"
    if WIN_ILLEGAL.search(t):
        return '模板不能包含非法字符 \\ / : * ? " < > |'
    return None


def _cleanup_segments(name: str) -> str:
    name = name.replace(EMPTY_TAG, "")
    name = re.sub(r"-{2,}", "-", name)
    name = re.sub(r"-\.", ".", name)
    name = re.sub(r"^-+", "", name)
    name = re.sub(r"-+$", "", name)
    if not name.lower().endswith(".mp4"):
        name = name.rstrip(".") + ".mp4"
    return name


def build_filename_from_template(
    template: str,
    fields: NamingFields,
    index: int,
    *,
    force_tags: Optional[list[str]] = None,
    index_width: int = 3,
    date_format: str = "8",
) -> tuple[str, bool]:
    err = validate_template(template)
    if err:
        raise ValueError(err)

    brand = normalize_brand(fields.brand)
    lang = sanitize_no_dash(fields.lang) or "ar"
    type_ = sanitize_no_dash(fields.type_) or "chat"
    size = normalize_size(fields.size)
    designer = sanitize_no_dash(fields.designer) or "ljw"
    date_full, date_ok = normalize_date(fields.date or today_date_str())
    if str(date_format) == "4":
        date_out = date_display_4(fields.date or today_date_str()) if date_ok else "0000"
    else:
        date_out = date_full if date_ok else INVALID_DATE

    tags = force_tags if force_tags is not None else fields.normalized_tags()
    tag_joined = "-".join(tags) if tags else EMPTY_TAG

    repl = {
        "{序号}": format_index(index, index_width),
        "{品牌}": brand,
        "{语言}": lang,
        "{类型}": type_,
        "{标签}": tag_joined,
        "{尺寸}": size,
        "{日期}": date_out,
        "{设计师}": designer,
    }
    for i in range(1, 4):
        val = tags[i - 1] if i - 1 < len(tags) else ""
        repl[f"{{标签{i}}}"] = val.strip() if val.strip() else EMPTY_TAG

    result = template
    for k, v in repl.items():
        result = result.replace(k, v)
    result = _cleanup_segments(result)
    return result, date_ok


def build_filename(
    fields: NamingFields,
    index: int,
    *,
    force_tags: Optional[list[str]] = None,
    index_width: int = 3,
    date_format: str = "8",
    # 兼容 naming_tool 旧调用：build_filename(..., strip_tags=...)
    strip_tags: Optional[set[str] | list[str]] = None,  # noqa: ARG001
) -> tuple[str, bool]:
    tpl = fields.template or DEFAULT_TEMPLATE
    return build_filename_from_template(
        tpl, fields, index, force_tags=force_tags,
        index_width=index_width, date_format=date_format,
    )


def list_videos(folder: str | Path, *, recursive: bool = False) -> list[str]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    try:
        if not recursive:
            entries = folder.iterdir()
            return sorted(
                f.name for f in entries
                if f.is_file() and f.suffix.lower() in VIDEO_EXTS
            )
        out: list[str] = []
        for f in folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
                out.append(f.relative_to(folder).as_posix())
        return sorted(out)
    except OSError:
        return []


def count_videos(folder: str | Path, *, recursive: bool = False) -> tuple[int, Optional[str]]:
    """返回 (数量, 错误说明)。错误说明非空时数量为 0。"""
    folder = Path(folder)
    if not folder.is_dir():
        return 0, "文件夹不存在或无法访问"
    try:
        return len(list_videos(folder, recursive=recursive)), None
    except OSError as e:
        return 0, f"无法读取文件夹（权限或网盘未同步）: {e}"


def parse_legacy_filename(
    filename: str,
    tag_library: Optional[set[str]] = None,
) -> ParsedLegacy:
    lib = {t.lower() for t in (tag_library or DEFAULT_TAG_LIBRARY)}
    result = ParsedLegacy(original=filename)
    stem, ext = Path(filename).stem, Path(filename).suffix.lower()
    if ext not in VIDEO_EXTS and ext:
        return result

    parts = stem.split("-")
    if len(parts) < 8:
        return result

    result.designer = parts[-1]
    date_part = parts[-2]
    size_part = parts[-3]

    if re.fullmatch(r"\d{8}", date_part):
        result.date = date_part
        result.date_valid = True
    elif re.fullmatch(r"\d{4}", date_part):
        result.date = date_part
        result.date_valid = True
    else:
        cleaned = re.sub(r"\D", "", date_part)[:8]
        if len(cleaned) >= 4 and cleaned.isdigit():
            result.date = cleaned
            result.date_valid = len(cleaned) == 8
        else:
            result.date = INVALID_DATE
            result.date_valid = False

    result.size = size_part if size_part in SIZE_PRESETS else "9x16"
    if parts[0].isdigit():
        result.index = int(parts[0])

    idx = 1
    if idx < len(parts) - 3 and parts[idx].lower() in BRAND_PRESETS:
        result.brand = parts[idx].lower()
        idx += 1
    if idx < len(parts) - 3 and parts[idx].lower() == FIXED_VIDEO:
        idx += 1
    if idx < len(parts) - 3:
        result.lang = parts[idx].lower()
        idx += 1
    if idx < len(parts) - 3:
        result.type_ = parts[idx].lower()
        idx += 1

    tag_parts = parts[idx:-3]
    result.tags = tag_parts
    for t in tag_parts:
        if t.lower() not in lib:
            result.non_standard_tags.append(t)
    result.parse_ok = bool(result.lang and result.type_)
    return result


def merge_legacy_with_fields(
    parsed: ParsedLegacy,
    fields: NamingFields,
    index: int,
    tag_library: set[str],
    *,
    index_width: int = 3,
    date_format: str = "8",
) -> tuple[str, list[str], bool]:
    warnings: list[str] = []
    brand = parsed.brand if parsed.brand in BRAND_PRESETS else normalize_brand(fields.brand)
    lang = parsed.lang or fields.lang
    type_ = parsed.type_ or fields.type_
    size = normalize_size(parsed.size if parsed.size else fields.size)
    designer = parsed.designer or fields.designer
    date_val = parsed.date if parsed.date_valid else (fields.date or today_date_str())

    user_tags = fields.normalized_tags()
    if user_tags:
        tags = user_tags
    else:
        tags = [t for t in parsed.tags if t.lower() in {x.lower() for x in tag_library}]
        for t in parsed.non_standard_tags:
            warnings.append(f"非标准标签「{t}」")
        if not tags and parsed.tags:
            warnings.append("请填写标准标签替换非标准内容")

    merged = NamingFields(
        brand=brand, lang=lang, type_=type_, tags=tags + ["", "", ""],
        size=size, date=date_val, designer=designer, template=fields.template,
    )
    name, date_ok = build_filename(
        merged, index, force_tags=tags,
        index_width=index_width, date_format=date_format,
    )
    if not date_ok or not parsed.date_valid:
        warnings.append("日期异常")
    return name, warnings, date_ok and parsed.date_valid


def validate_tags_for_execute(tags: list[str]) -> Optional[str]:
    n = len([t for t in tags if (t or "").strip()])
    if n == 0:
        return "当前未填写任何标签（0 个）。是否仍要执行重命名？"
    if n > 3:
        return f"当前标签数为 {n}（超过 3 个）。是否仍要执行重命名？"
    return None


def add_tags_to_library(library: list[str], tags: list[str], max_size: int = MAX_CUSTOM_TAGS) -> list[str]:
    out = list(library)
    for t in tags:
        t = (t or "").strip()
        if not t or t in out:
            continue
        out.insert(0, t)
    return out[:max_size]


def default_naming_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "template": DEFAULT_TEMPLATE,
        "folder": "",
        "start_index": 1,
        "brand_preset": "habi",
        "brand_custom": "",
        "lang": "ar",
        "type": "chat",
        "size": "9x16",
        "date": today_date_str(),
        "designer_preset": "ljw",
        "designer_custom": "",
        "tags": ["", "", ""],
        "legacy_mode": False,
        "custom_tags": list(DEFAULT_TAG_LIBRARY[:MAX_CUSTOM_TAGS]),
        "designer_history": list(DESIGNER_PRESETS),
    }


def _sanitize_naming_config(raw: dict[str, Any]) -> dict[str, Any]:
    """校验并修正命名配置字段，损坏项回退默认值"""
    base = default_naming_config()
    out = dict(base)
    for key in base:
        if key not in raw:
            continue
        val = raw[key]
        if key == "enabled" or key == "legacy_mode":
            out[key] = bool(val)
        elif key == "start_index":
            try:
                out[key] = max(1, int(val))
            except (TypeError, ValueError):
                pass
        elif key == "tags":
            if isinstance(val, list):
                tags = [str(t) for t in val[:3]]
                while len(tags) < 3:
                    tags.append("")
                out[key] = tags
        elif key == "custom_tags":
            if isinstance(val, list):
                out[key] = [str(t) for t in val if str(t).strip()][:MAX_CUSTOM_TAGS]
        elif key == "designer_history":
            if isinstance(val, list):
                out[key] = [str(d) for d in val if str(d).strip()]
        elif isinstance(val, str) or key in ("brand_preset", "brand_custom", "lang", "type", "size",
                                              "date", "designer_preset", "designer_custom",
                                              "template", "folder"):
            out[key] = str(val) if val is not None else base.get(key, "")
        else:
            out[key] = val
    if out.get("brand_preset") not in BRAND_PRESETS:
        out["brand_preset"] = "habi"
    if out.get("lang") not in LANG_PRESETS:
        out["lang"] = "ar"
    if out.get("type") not in TYPE_PRESETS:
        out["type"] = "chat"
    if out.get("size") not in SIZE_PRESETS:
        out["size"] = "9x16"
    tpl = out.get("template", DEFAULT_TEMPLATE)
    if validate_template(str(tpl)):
        out["template"] = DEFAULT_TEMPLATE
    return out


def load_naming_config() -> dict[str, Any]:
    path = habi_tool_config_path()
    if not path.is_file():
        return default_naming_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("config.json 根节点必须是对象")
        cfg = default_naming_config()
        naming = data.get("naming", data)
        if isinstance(naming, dict):
            cfg = _sanitize_naming_config({**cfg, **naming})
        return cfg
    except Exception:
        try:
            from datetime import datetime
            import shutil
            backup = path.with_name(
                f"{path.stem}.corrupt.{datetime.now().strftime('%Y%m%d%H%M%S')}{path.suffix}"
            )
            shutil.copy2(path, backup)
        except Exception:
            pass
        return default_naming_config()


def save_naming_config(naming: dict[str, Any]) -> None:
    path = habi_tool_config_path()
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            payload = {}
    payload["naming"] = naming
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
