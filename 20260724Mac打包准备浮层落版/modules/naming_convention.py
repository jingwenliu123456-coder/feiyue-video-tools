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
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
    ".heic", ".heif", ".avif", ".ico", ".jfif", ".psd", ".svg",
}
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS

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
# 常用标签库不再限制数量；保留常量仅供旧配置兼容读取
MAX_CUSTOM_TAGS = None

DEFAULT_TEMPLATE = "{序号}-{品牌}-video-{语言}-{类型}-{标签}-{尺寸}-{日期}-{设计师}"
INVALID_DATE = "00000000"
WIN_ILLEGAL = re.compile(r'[\\/:*?"<>|]')

DEFAULT_TAG_LIBRARY: list[str] = [
    # —— 分类（Habi 素材标签化）——
    "游戏", "付费引导", "产品功能", "口播类型", "AI生成", "AI模特",
    "实拍类型", "混剪", "语音房", "礼物元素", "3秒开头", "模特类型", "语聊", "运营活动",
    # 游戏
    "Cat", "Luckyslot", "Box", "其他游戏", "Ludo游戏", "混合游戏", "Gate", "Fortune",
    "Pyramid", "Sphinx", "Chicken", "Deepsea", "Sinbad", "Plinko", "World Cup Slots", "Football",
    # 付费引导
    "首充优惠", "存钱罐", "游戏金币", "礼物打赏", "语音房对话", "等级提升", "召回活动", "开宝箱",
    "端内礼包", "炫富", "实物礼包", "红包", "复购礼包", "游戏召回", "游戏钻石", "主页展示", "特权展示",
    # 产品功能
    "新人奖励", "1V1 视频",
    # 口播类型
    "local口播", "AI口播",
    # AI 生成
    "AI西装男", "AI头巾男", "AI礼物", "AI音频", "AI采访", "AI搭讪",
    # 实拍类型
    "KOL", "短剧", "美女", "真人实拍",
    # 混剪
    "混剪游戏", "混剪语音房",
    # 语音房
    "PK", "原生",
    # 礼物元素
    "金色清真寺", "狮子", "远航", "黄金玫瑰", "国旗元素", "其他礼物", "老虎", "情侣", "动物",
    "火箭", "跑车", "老鹰", "金手表", "龙", "荣誉圣殿", "金库", "金奖杯", "极昼之城", "神龙权杖", "小羊驼",
    # 3 秒开头
    "口播", "跳舞", "视频", "社交", "猫咪", "企鹅舞", "美食制作", "骑马",
    # 模特类型
    "穆斯林", "欧美", "网络表情包", "热梗", "土豪",
    # 语聊
    "hot语聊", "local语聊", "hot bgm",
    # 运营活动
    "年度活动", "斋月活动", "幸运日活动", "宰牲节活动", "世界杯活动",
    # 历史常用（保留兼容）
    "美女诱导", "爆元素", "金色玫瑰", "黑暗房间实拍", "美女前贴", "情侣礼物", "1刀首充", "爆金币",
    "luckshot", "语音房", "实拍", "原生（纯录屏）", "TT热点", "特权", "文案引导",
]

TAG_LIBRARY_VERSION = 2


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
    short_kol: bool = False
    kol_note: str = ""


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


def source_ext_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext else ".mp4"


def strip_template_extension(template: str) -> str:
    t = (template or "").strip()
    for ext in sorted(MEDIA_EXTS, key=len, reverse=True):
        if t.lower().endswith(ext):
            return t[: -len(ext)]
    return t


def validate_template(template: str) -> Optional[str]:
    t = strip_template_extension((template or "").strip())
    if "{序号}" not in t:
        return "模板必须包含 {序号}，否则文件会重名"
    if WIN_ILLEGAL.search(t):
        return '模板不能包含非法字符 \\ / : * ? " < > |'
    return None


def _cleanup_segments(name: str, *, ext: str = ".mp4") -> str:
    name = strip_template_extension(name)
    name = name.replace(EMPTY_TAG, "")
    name = re.sub(r"-{2,}", "-", name)
    name = re.sub(r"-\.", ".", name)
    name = re.sub(r"^-+", "", name)
    name = re.sub(r"-+$", "", name)
    target = ext if ext.startswith(".") else f".{ext}"
    return name.rstrip(".") + target


def build_filename_from_template(
    template: str,
    fields: NamingFields,
    index: int,
    *,
    force_tags: Optional[list[str]] = None,
    index_width: int = 3,
    date_format: str = "8",
    source_ext: Optional[str] = None,
) -> tuple[str, bool]:
    tpl = strip_template_extension(template)
    err = validate_template(tpl)
    if err:
        raise ValueError(err)
    ext = source_ext if source_ext else ".mp4"
    if not ext.startswith("."):
        ext = f".{ext}"

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

    result = tpl
    for k, v in repl.items():
        result = result.replace(k, v)
    result = _cleanup_segments(result, ext=ext)
    return result, date_ok


def build_filename(
    fields: NamingFields,
    index: int,
    *,
    force_tags: Optional[list[str]] = None,
    index_width: int = 3,
    date_format: str = "8",
    source_ext: Optional[str] = None,
    # 兼容 naming_tool 旧调用：build_filename(..., strip_tags=..., keep_tags=...)
    # build_filename 本身不处理 legacy 清理逻辑（在 merge_legacy_with_fields 内处理）
    strip_tags: Optional[set[str] | list[str]] = None,  # noqa: ARG001
    keep_tags: Optional[set[str] | list[str]] = None,  # noqa: ARG001
) -> tuple[str, bool]:
    tpl = fields.template or DEFAULT_TEMPLATE
    return build_filename_from_template(
        tpl, fields, index, force_tags=force_tags,
        index_width=index_width, date_format=date_format,
        source_ext=source_ext,
    )


def list_media_files(folder: str | Path, *, recursive: bool = False) -> list[str]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    try:
        if not recursive:
            entries = folder.iterdir()
            return sorted(
                f.name for f in entries
                if f.is_file() and f.suffix.lower() in MEDIA_EXTS
            )
        out: list[str] = []
        for f in folder.rglob("*"):
            if f.is_file() and f.suffix.lower() in MEDIA_EXTS:
                out.append(f.relative_to(folder).as_posix())
        return sorted(out)
    except OSError:
        return []


def list_videos(folder: str | Path, *, recursive: bool = False) -> list[str]:
    """兼容旧名：实际扫描视频与图片。"""
    return list_media_files(folder, recursive=recursive)


def count_videos(folder: str | Path, *, recursive: bool = False) -> tuple[int, Optional[str]]:
    """返回 (数量, 错误说明)。错误说明非空时数量为 0。"""
    folder = Path(folder)
    if not folder.is_dir():
        return 0, "文件夹不存在或无法访问"
    try:
        return len(list_videos(folder, recursive=recursive)), None
    except OSError as e:
        return 0, f"无法读取文件夹（权限或网盘未同步）: {e}"


def _is_legacy_lang_code(part: str) -> bool:
    return (part or "").strip().lower() in {x.lower() for x in LANG_PRESETS}


def _is_kol_name(part: str) -> bool:
    p = (part or "").strip()
    if not p:
        return False
    return not WIN_ILLEGAL.search(p)


_LEGACY_TYPE_TOKENS = {x.lower() for x in TYPE_PRESETS} | {"kol"}
_LANG_LOWER = {x.lower() for x in LANG_PRESETS}
_BRAND_LOWER = {x.lower() for x in BRAND_PRESETS}


def _extract_type_lang_from_tag_parts(
    parts: list[str],
) -> tuple[str, str, str, list[str]]:
    """从「第 N 个-之后」的段落里拆出品牌/语言/类型，其余才是标签（避免 chat 进标签又被滤掉）。"""
    brand = lang = type_ = ""
    rest = [p.strip() for p in parts if (p or "").strip()]
    while rest:
        p = rest[0]
        pl = p.lower()
        if not brand and pl in _BRAND_LOWER:
            brand = pl
            rest.pop(0)
            continue
        if pl == FIXED_VIDEO:
            rest.pop(0)
            continue
        if not lang and pl in _LANG_LOWER:
            lang = pl
            rest.pop(0)
            continue
        if not type_ and pl in _LEGACY_TYPE_TOKENS:
            type_ = "KOL" if pl == "kol" else pl
            rest.pop(0)
            continue
        break
    return brand, lang, type_, rest


def _stem_fallback_parsed(
    parsed: ParsedLegacy,
    cleaned_stem: str,
    tag_library: Optional[set[str]] = None,
) -> ParsedLegacy:
    """主干清理后无法按长格式解析时，从截取结果还原标签/类型/KOL。"""
    stem = (cleaned_stem or "").strip()
    if not stem:
        return parsed

    parts = [p.strip() for p in stem.split("-") if p.strip()]

    short = _parse_short_kol_legacy(parts, ParsedLegacy(original=parsed.original))
    if short is not None and short.parse_ok:
        parsed.lang = short.lang or parsed.lang
        parsed.type_ = short.type_ or parsed.type_
        parsed.tags = list(short.tags)
        parsed.short_kol = short.short_kol
        parsed.parse_ok = True
        parsed.kol_note = short.kol_note
        return parsed

    if len(parts) == 1:
        parsed.tags = [parts[0]]
        parsed.parse_ok = True
        parsed.kol_note = parsed.kol_note or f"无「-」分隔，整段作为标签「{parts[0]}」"
        return parsed

    brand, lang, type_, tag_parts = _extract_type_lang_from_tag_parts(parts)
    if brand:
        parsed.brand = brand
    if lang:
        parsed.lang = lang
    if type_:
        parsed.type_ = type_
    parsed.tags = tag_parts[:3]
    parsed.parse_ok = bool(tag_parts or type_ or lang or brand)
    if type_ and not tag_parts:
        parsed.kol_note = parsed.kol_note or f"已从旧名识别类型「{type_}」"
    return parsed


def _parse_short_kol_legacy(parts: list[str], result: ParsedLegacy) -> Optional[ParsedLegacy]:
    """短格式：AR-KOL-3ssfoora（3~5 段）。成功则返回 result，否则带备注返回或 None 继续长格式。"""
    n = len(parts)
    if not (3 <= n <= 5):
        return None
    if parts[1].upper() != "KOL":
        return None
    if not _is_legacy_lang_code(parts[0]):
        return None

    result.short_kol = True
    kol_name = (parts[2] or "").strip()
    if not kol_name:
        result.kol_note = "短格式KOL文件，但KOL名字为空"
        return result

    result.lang = parts[0].lower()
    result.type_ = "KOL"
    result.tags = [kol_name] + [p.strip() for p in parts[3:] if p.strip()]
    result.parse_ok = True
    result.kol_note = f"短格式KOL文件，KOL名字「{kol_name}」已提取并保留"
    return result


def parse_legacy_filename(
    filename: str,
    tag_library: Optional[set[str]] = None,
) -> ParsedLegacy:
    lib = {t.lower() for t in (tag_library or DEFAULT_TAG_LIBRARY)}
    result = ParsedLegacy(original=filename)
    stem, ext = Path(filename).stem, Path(filename).suffix.lower()
    if ext not in MEDIA_EXTS and ext:
        return result

    parts = stem.split("-")

    short = _parse_short_kol_legacy(parts, result)
    if short is not None:
        return short

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


LEGACY_OVERRIDE_FIELDS: dict[str, str] = {
    "brand": "品牌",
    "lang": "语言",
    "type_": "类型",
    "tag1": "标签1",
    "tag2": "标签2",
    "tag3": "标签3",
    "size": "尺寸",
    "date": "日期",
    "designer": "设计师",
}


def _parsed_brand(parsed: ParsedLegacy) -> str:
    return parsed.brand if parsed.brand in BRAND_PRESETS else ""


def _parsed_date(parsed: ParsedLegacy) -> str:
    return parsed.date if parsed.date_valid else ""


def _normalize_override(field: str, value: str) -> str:
    v = (value or "").strip()
    if field == "brand":
        return normalize_brand(v)
    if field == "lang":
        return sanitize_no_dash(v) or "ar"
    if field == "type_":
        return sanitize_no_dash(v) or "chat"
    if field == "size":
        return normalize_size(v)
    if field == "date":
        return v
    if field == "designer":
        return sanitize_no_dash(v) or "ljw"
    return sanitize_no_dash(v)


def _clone_parsed_with_tags(
    parsed: ParsedLegacy,
    tags: list[str],
    *,
    tag_library: Optional[set[str]] = None,
) -> ParsedLegacy:
    lib = tag_library or set(DEFAULT_TAG_LIBRARY)
    lib_lower = {(x or "").strip().lower() for x in lib}
    return ParsedLegacy(
        original=parsed.original,
        index=parsed.index,
        brand=parsed.brand,
        lang=parsed.lang,
        type_=parsed.type_,
        tags=tags,
        size=parsed.size,
        date=parsed.date,
        date_valid=parsed.date_valid,
        designer=parsed.designer,
        parse_ok=parsed.parse_ok,
        short_kol=parsed.short_kol,
        kol_note=parsed.kol_note,
        non_standard_tags=[t for t in tags if (t or "").strip().lower() not in lib_lower],
    )


def apply_legacy_keep_tags(
    parsed: ParsedLegacy,
    keep_tags: Optional[set[str] | list[str]],
    *,
    tag_library: Optional[set[str]] = None,
) -> tuple[ParsedLegacy, list[str]]:
    """旧名标签白名单：仅保留用户指定的词，其余段落会被忽略。"""
    if not keep_tags or not parsed.tags:
        return parsed, []
    keep_lower = {(t or "").strip().lower() for t in keep_tags if (t or "").strip()}
    if not keep_lower:
        return parsed, []
    kept: list[str] = []
    removed: list[str] = []
    for t in parsed.tags:
        if (t or "").strip().lower() in keep_lower:
            kept.append(t)
        else:
            removed.append(t)
    if not removed:
        return parsed, []
    return _clone_parsed_with_tags(parsed, kept, tag_library=tag_library), removed


def apply_legacy_strip_tags(
    parsed: ParsedLegacy,
    strip_tags: Optional[set[str] | list[str]],
    *,
    tag_library: Optional[set[str]] = None,
) -> tuple[ParsedLegacy, list[str]]:
    """从旧名解析结果中剔除用户指定的补充词，返回副本与剔除记录。"""
    if not strip_tags or not parsed.tags:
        return parsed, []
    strip_lower = {(t or "").strip().lower() for t in strip_tags if (t or "").strip()}
    if not strip_lower:
        return parsed, []
    removed: list[str] = []
    kept: list[str] = []
    for t in parsed.tags:
        if (t or "").strip().lower() in strip_lower:
            removed.append(t)
        else:
            kept.append(t)
    if not removed:
        return parsed, []
    return _clone_parsed_with_tags(parsed, kept, tag_library=tag_library), removed


def validate_regex_patterns(patterns: Optional[list[str] | set[str]], *, label: str) -> Optional[str]:
    """校验正则列表；无效时返回错误说明。"""
    for i, raw in enumerate(patterns or [], 1):
        pattern = (raw or "").strip()
        if not pattern:
            continue
        try:
            re.compile(pattern)
        except re.error as e:
            return f"{label} 第 {i} 条正则表达式无效：{e}"
    return None


def preprocess_legacy_stem(
    stem: str,
    *,
    keep_tags: Optional[list[str]] = None,
    strip_tags: Optional[list[str]] = None,
    keep_regex: bool = False,
    strip_regex: bool = False,
    dash_keep_after: Optional[int] = None,
) -> tuple[str, list[str]]:
    """对文件名主干（不含扩展名）做清理：可选「第 N 个 - 之后」→ 保留词 → 剔除词。"""
    warnings: list[str] = []
    result = stem or ""
    keeps = [(t or "").strip() for t in (keep_tags or []) if (t or "").strip()]
    strips = [(t or "").strip() for t in (strip_tags or []) if (t or "").strip()]

    n = int(dash_keep_after or 0)
    if n > 0 and result:
        parts = result.split("-")
        if len(parts) > n:
            kept = "-".join(parts[n:])
            dropped = "-".join(parts[:n])
            warnings.append(f"已保留第{n}个「-」之后（去掉前缀「{dropped}」）")
            result = kept
        else:
            warnings.append(
                f"文件名无足够「-」分隔（需>{n}段），整段「{result}」将作为标签内容"
            )

    # 保留词（白名单）
    if keeps:
        if keep_regex:
            found: list[str] = []
            for pattern in keeps:
                try:
                    m = re.search(pattern, result)
                except re.error:
                    continue
                if m and m.group(0):
                    found.append(m.group(0))
            if found:
                result = "".join(found)
        else:
            collected: list[str] = []
            lower = result.lower()
            for word in keeps:
                idx = lower.find(word.lower())
                if idx >= 0:
                    collected.append(result[idx: idx + len(word)])
            if collected:
                result = "".join(collected)

    # 剔除词（黑名单）
    if strips:
        if strip_regex:
            for pattern in strips:
                try:
                    result = re.sub(pattern, "", result)
                except re.error as e:
                    warnings.append(f"剔除词正则无效：{pattern} ({e})")
        else:
            for word in strips:
                result = result.replace(word, "")

    return result, warnings


def _should_preprocess_legacy_stem(
    parsed: ParsedLegacy,
    *,
    keep_tags: Optional[list[str]] = None,
    strip_tags: Optional[list[str]] = None,
    keep_regex: bool = False,
    strip_regex: bool = False,
    dash_keep_after: Optional[int] = None,
) -> bool:
    if int(dash_keep_after or 0) > 0:
        return True
    has_rules = bool(keep_tags) or bool(strip_tags)
    if not has_rules:
        return False
    return keep_regex or strip_regex or not parsed.parse_ok


def _resolve_legacy_tags(
    parsed: ParsedLegacy,
    fields: NamingFields,
    overrides: dict[str, str],
    tag_library: set[str],
    *,
    legacy_priority: bool,
    strip_tags: Optional[set[str] | list[str]] = None,
    keep_tags: Optional[set[str] | list[str]] = None,
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    parsed_tags = (list(parsed.tags) + ["", "", ""])[:3]
    user_tags = fields.normalized_tags()
    lib_lower = {(t or "").strip().lower() for t in tag_library if (t or "").strip()}
    strip_lower = {(t or "").strip().lower() for t in (strip_tags or []) if (t or "").strip()}
    # 保留词 = 用户明确允许的标签（即使不在标准库，也不再报「非标准」）
    keep_lower = {(t or "").strip().lower() for t in (keep_tags or []) if (t or "").strip()}
    allowed_lower = lib_lower | keep_lower

    if parsed.short_kol and parsed.parse_ok and parsed.tags:
        tags: list[str] = []
        for i, key in enumerate(("tag1", "tag2", "tag3")):
            if key in overrides:
                tags.append(_normalize_override(key, overrides[key]))
            elif parsed_tags[i]:
                tags.append(parsed_tags[i])
            elif user_tags and i < len(user_tags):
                tags.append(user_tags[i])
            else:
                raw = fields.tags[i] if i < len(fields.tags) else ""
                tags.append((raw or "").strip())
        return [t for t in tags if t], warnings

    if legacy_priority or overrides:
        tags: list[str] = []
        for i, key in enumerate(("tag1", "tag2", "tag3")):
            if key in overrides:
                tags.append(_normalize_override(key, overrides[key]))
            elif parsed_tags[i]:
                tags.append(parsed_tags[i])
            elif user_tags and i < len(user_tags):
                tags.append(user_tags[i])
            else:
                raw = fields.tags[i] if i < len(fields.tags) else ""
                tags.append((raw or "").strip())
        return [t for t in tags if t], warnings

    if user_tags:
        for t in parsed.tags:
            tl = (t or "").strip().lower()
            if tl in strip_lower:
                warnings.append(f"已剔除「{t}」")
            elif tl not in allowed_lower and tl not in {(u or "").lower() for u in user_tags}:
                warnings.append(f"旧名多余「{t}」已忽略")
        return user_tags, warnings

    tags = [t for t in parsed.tags if (t or "").strip().lower() in allowed_lower][:3]
    for t in parsed.tags:
        tl = (t or "").strip().lower()
        if tl in strip_lower:
            continue
        if tl not in allowed_lower:
            warnings.append(f"非标准标签「{t}」")
    if not tags and parsed.tags:
        warnings.append("请填写标准标签替换非标准内容（或把要用的词加入「保留词」）")
    return tags, warnings


def _build_legacy_remark(
    overrides: dict[str, str],
    *,
    parse_ok: bool,
    legacy_priority: bool,
) -> str:
    if overrides:
        parts = [
            f"{LEGACY_OVERRIDE_FIELDS.get(k, k)}={v}"
            for k, v in overrides.items()
            if (v or "").strip()
        ]
        return f"局部更新：{', '.join(parts)}，其余优先保留旧名"
    if legacy_priority or parse_ok:
        return "按旧名解析合并"
    return "按全局默认值生成"


def merge_legacy_with_fields(
    parsed: ParsedLegacy,
    fields: NamingFields,
    index: int,
    tag_library: set[str],
    *,
    index_width: int = 3,
    date_format: str = "8",
    overrides: Optional[dict[str, str]] = None,
    legacy_priority: bool = False,
    keep_tags: Optional[set[str] | list[str]] = None,
    strip_tags: Optional[set[str] | list[str]] = None,
    keep_regex: bool = False,
    strip_regex: bool = False,
    dash_keep_after: Optional[int] = None,
) -> tuple[str, list[str], bool]:
    warnings: list[str] = []
    ov = {k: v for k, v in (overrides or {}).items() if (v or "").strip()}
    dash_n = int(dash_keep_after or 0)
    # 启用「第 N 个-之后」时，默认优先采用旧名解析出的标签/类型，避免被界面标签盖掉
    use_legacy_first = legacy_priority or bool(ov) or dash_n > 0

    orig_full = parsed.original
    original_stem = Path(orig_full).stem
    ext = Path(orig_full).suffix
    pre_kol = parse_legacy_filename(orig_full, tag_library)
    skip_dash_for_kol = bool(
        dash_n > 0 and pre_kol.short_kol and pre_kol.parse_ok
    )

    use_stem = _should_preprocess_legacy_stem(
        parsed,
        keep_tags=list(keep_tags) if keep_tags else None,
        strip_tags=list(strip_tags) if strip_tags else None,
        keep_regex=keep_regex,
        strip_regex=strip_regex,
        dash_keep_after=0 if skip_dash_for_kol else dash_keep_after,
    )
    resolve_strip = strip_tags

    if use_stem:
        cleaned_stem, stem_warns = preprocess_legacy_stem(
            original_stem,
            keep_tags=list(keep_tags) if keep_tags else None,
            strip_tags=list(strip_tags) if strip_tags else None,
            keep_regex=keep_regex,
            strip_regex=strip_regex,
            dash_keep_after=0 if skip_dash_for_kol else dash_keep_after,
        )
        warnings.extend(stem_warns)
        if skip_dash_for_kol:
            warnings.append("短格式 KOL 文件，已保留完整文件名以提取 KOL 名")
            parsed = pre_kol
            parsed.original = orig_full
        else:
            parsed = parse_legacy_filename(f"{cleaned_stem}{ext}", tag_library)
            parsed.original = orig_full
            if cleaned_stem and not parsed.parse_ok:
                parsed = _stem_fallback_parsed(parsed, cleaned_stem, tag_library)
        resolve_strip = None
        # 第 N 个「-」之后截取到的段落，即使不在标准库也允许写进新名
        if dash_n > 0 and parsed.tags:
            extra = list(keep_tags or [])
            for t in parsed.tags:
                if t and t not in extra:
                    extra.append(t)
            keep_tags = extra
    else:
        parsed, removed_keep = apply_legacy_keep_tags(parsed, keep_tags, tag_library=tag_library)
        for t in removed_keep:
            msg = f"未在保留词内「{t}」"
            if msg not in warnings:
                warnings.append(msg)
        parsed, removed = apply_legacy_strip_tags(parsed, strip_tags, tag_library=tag_library)
        for t in removed:
            if f"已剔除「{t}」" not in warnings:
                warnings.append(f"已剔除「{t}」")

    if use_legacy_first:
        brand = (
            _normalize_override("brand", ov["brand"])
            if "brand" in ov
            else (_parsed_brand(parsed) or normalize_brand(fields.brand))
        )
        lang = (
            _normalize_override("lang", ov["lang"])
            if "lang" in ov
            else (sanitize_no_dash(parsed.lang) if parsed.lang else fields.lang)
        )
        type_ = (
            _normalize_override("type_", ov["type_"])
            if "type_" in ov
            else (sanitize_no_dash(parsed.type_) if parsed.type_ else fields.type_)
        )
        size = (
            _normalize_override("size", ov["size"])
            if "size" in ov
            else normalize_size(parsed.size if parsed.size else fields.size)
        )
        designer = (
            _normalize_override("designer", ov["designer"])
            if "designer" in ov
            else (sanitize_no_dash(parsed.designer) if parsed.designer else fields.designer)
        )
        if "date" in ov:
            date_val = _normalize_override("date", ov["date"])
            parsed_date_valid = True
        elif _parsed_date(parsed):
            date_val = parsed.date
            parsed_date_valid = parsed.date_valid
        else:
            date_val = fields.date or today_date_str()
            parsed_date_valid = False
        tags, tag_warns = _resolve_legacy_tags(
            parsed, fields, ov, tag_library,
            legacy_priority=use_legacy_first,
            strip_tags=resolve_strip,
            keep_tags=keep_tags,
        )
        warnings.extend(tag_warns)
    else:
        brand = parsed.brand if parsed.brand in BRAND_PRESETS else normalize_brand(fields.brand)
        lang = parsed.lang or fields.lang
        if parsed.short_kol and parsed.parse_ok and parsed.type_:
            type_ = parsed.type_
        else:
            type_ = parsed.type_ or fields.type_
        size = normalize_size(parsed.size if parsed.size else fields.size)
        designer = parsed.designer or fields.designer
        date_val = parsed.date if parsed.date_valid else (fields.date or today_date_str())
        parsed_date_valid = parsed.date_valid
        tags, tag_warns = _resolve_legacy_tags(
            parsed, fields, ov, tag_library,
            legacy_priority=False,
            strip_tags=resolve_strip,
            keep_tags=keep_tags,
        )
        warnings.extend(tag_warns)

    remark = _build_legacy_remark(ov, parse_ok=parsed.parse_ok, legacy_priority=use_legacy_first)
    if use_legacy_first or not parsed.kol_note:
        warnings.insert(0, remark)
    elif parsed.kol_note:
        warnings.insert(0, parsed.kol_note)

    merged = NamingFields(
        brand=brand, lang=lang, type_=type_, tags=tags + ["", "", ""],
        size=size, date=date_val, designer=designer, template=fields.template,
    )
    name, date_ok = build_filename(
        merged, index, force_tags=tags,
        index_width=index_width, date_format=date_format,
        source_ext=source_ext_from_filename(parsed.original),
    )
    if use_legacy_first:
        if not date_ok:
            warnings.append("日期异常")
        date_merge_ok = date_ok
    elif parsed.short_kol:
        if parsed.parse_ok and not date_ok:
            warnings.append("日期异常")
        date_merge_ok = date_ok
    else:
        if not date_ok or not parsed_date_valid:
            warnings.append("日期异常")
        date_merge_ok = date_ok and parsed_date_valid
    return name, warnings, date_merge_ok


def validate_tags_for_execute(tags: list[str]) -> Optional[str]:
    n = len([t for t in tags if (t or "").strip()])
    if n == 0:
        return "当前未填写任何标签（0 个）。是否仍要执行重命名？"
    if n > 3:
        return f"当前标签数为 {n}（超过 3 个）。是否仍要执行重命名？"
    return None


def merge_tag_library(user_tags: list[str], defaults: list[str]) -> list[str]:
    """合并用户标签与默认库，去重保序（用户已有项优先）。"""
    seen: set[str] = set()
    out: list[str] = []
    for t in list(user_tags) + list(defaults):
        key = (t or "").strip()
        if not key:
            continue
        lk = key.lower()
        if lk in seen:
            continue
        seen.add(lk)
        out.append(key)
    return out


def default_tags_by_type() -> dict[str, list[str]]:
    base = list(DEFAULT_TAG_LIBRARY)
    return {"game": list(base), "chat": list(base), "default": list(base)}


def upgrade_custom_tags_by_type(raw: object, *, library_version: int = 0) -> dict[str, list[str]]:
    """按版本将新版默认标签并入各类型常用库（不删用户已有项）。"""
    out = default_tags_by_type()
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, list):
                out[str(key)] = [str(t) for t in val if str(t).strip()]
    for key in ("game", "chat", "default"):
        if key not in out or not out[key]:
            out[key] = list(DEFAULT_TAG_LIBRARY)
    if library_version < TAG_LIBRARY_VERSION:
        for key in ("game", "chat", "default"):
            out[key] = merge_tag_library(out.get(key, []), DEFAULT_TAG_LIBRARY)
    return out


def add_tags_to_library(
    library: list[str],
    tags: list[str],
    max_size: int | None = None,
) -> list[str]:
    out = list(library)
    for t in tags:
        t = (t or "").strip()
        if not t or t in out:
            continue
        out.insert(0, t)
    if max_size is not None and max_size > 0:
        return out[:max_size]
    return out


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
        "custom_tags": list(DEFAULT_TAG_LIBRARY),
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
                out[key] = [str(t) for t in val if str(t).strip()]
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
