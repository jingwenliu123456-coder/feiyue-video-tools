# -*- coding: utf-8 -*-
"""菲菲式元变量：在规则文本中插入 {序号}、{日期} 等并按行展开。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from modules.naming_convention import today_date_str

# 下拉列表（与规范命名字段对齐）
META_INSERT_OPTIONS: list[tuple[str, str]] = [
    ("{序号}", "当前序号"),
    ("{日期}", "今天日期"),
    ("{原文件名}", "原文件名含扩展名"),
    ("{原名}", "原文件名不含扩展名"),
    ("{扩展名}", "原扩展名"),
    ("{父文件夹名}", "所在文件夹名"),
    ("{品牌}", "品牌字段"),
    ("{语言}", "语言字段"),
    ("{类型}", "类型字段"),
    ("{标签}", "标签1"),
    ("{标签1}", "标签1"),
    ("{标签2}", "标签2"),
    ("{标签3}", "标签3"),
    ("{尺寸}", "尺寸字段"),
    ("{设计师}", "设计师字段"),
]

RULE_META_INSERT_OPTIONS: list[tuple[str, str]] = [
    x for x in META_INSERT_OPTIONS if x[0] != "{序号}"
]
META_TOKEN_LABELS = [t for t, _ in META_INSERT_OPTIONS]

# 兼容菲菲/常见写法
_ALIASES = {
    "{名}": "{原名}",
    "{文件名}": "{原文件名}",
    "{文件夹}": "{父文件夹名}",
    "{N}": "{序号}",
}


@dataclass
class RenameMetaContext:
    """单行重命名时的元变量上下文。"""

    index: int = 1
    index_digits: int = 2
    date: str = ""
    old_full: str = ""
    old_stem: str = ""
    ext: str = ""
    parent_name: str = ""
    brand: str = ""
    lang: str = ""
    type_: str = ""
    tag1: str = ""
    tag2: str = ""
    tag3: str = ""
    size: str = ""
    designer: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_row(
        cls,
        row: dict[str, Any],
        *,
        list_index: int,
        start_index: int = 1,
        index_digits: int = 2,
        date: str = "",
        folder: str = "",
        fields: Optional[Any] = None,
    ) -> RenameMetaContext:
        old = str(row.get("old") or "")
        stem, ext = os.path.splitext(old)
        idx = int(start_index) + int(list_index)
        parent = folder or ""
        fp = str(row.get("full_path") or "")
        if fp:
            parent = os.path.dirname(fp)
        parent_name = os.path.basename(parent.rstrip("\\/")) if parent else ""

        brand = lang = type_ = tag1 = tag2 = tag3 = size = designer = ""
        overrides = row.get("overrides") or {}
        if isinstance(overrides, dict):
            brand = str(overrides.get("brand") or "")
            lang = str(overrides.get("lang") or "")
            type_ = str(overrides.get("type_") or "")
            tag1 = str(overrides.get("tag1") or "")
            tag2 = str(overrides.get("tag2") or "")
            tag3 = str(overrides.get("tag3") or "")
            size = str(overrides.get("size") or "")
            designer = str(overrides.get("designer") or "")

        if fields is not None:
            try:
                brand = brand or str(getattr(fields, "brand", "") or "")
                lang = lang or str(getattr(fields, "lang", "") or "")
                type_ = type_ or str(getattr(fields, "type_", "") or "")
                tags = getattr(fields, "normalized_tags", lambda: [])()
                if tags:
                    tag1 = tag1 or str(tags[0] if len(tags) > 0 else "")
                    tag2 = tag2 or str(tags[1] if len(tags) > 1 else "")
                    tag3 = tag3 or str(tags[2] if len(tags) > 2 else "")
                size = size or str(getattr(fields, "size", "") or "")
                designer = designer or str(getattr(fields, "designer", "") or "")
            except Exception:
                pass

        d = (date or "").strip() or today_date_str(digits=4)

        return cls(
            index=idx,
            index_digits=max(1, int(index_digits or 2)),
            date=d,
            old_full=old,
            old_stem=stem,
            ext=ext,
            parent_name=parent_name,
            brand=brand,
            lang=lang,
            type_=type_,
            tag1=tag1,
            tag2=tag2,
            tag3=tag3,
            size=size,
            designer=designer,
        )

    def resolve_token(self, token: str) -> str:
        t = (token or "").strip()
        t = _ALIASES.get(t, t)
        if t == "{序号}":
            return str(int(self.index)).zfill(self.index_digits)
        if t == "{日期}":
            return self.date
        if t in ("{原文件名}",):
            return self.old_full
        if t in ("{原名}",):
            return self.old_stem
        if t == "{扩展名}":
            return self.ext
        if t == "{父文件夹名}":
            return self.parent_name
        if t == "{品牌}":
            return self.brand
        if t == "{语言}":
            return self.lang
        if t == "{类型}":
            return self.type_
        if t in ("{标签}", "{标签1}"):
            return self.tag1
        if t == "{标签2}":
            return self.tag2
        if t == "{标签3}":
            return self.tag3
        if t == "{尺寸}":
            return self.size
        if t == "{设计师}":
            return self.designer
        if t in self.extra:
            return self.extra[t]
        return t


_META_PATTERN = re.compile(
    r"\{(?:序号|日期|原文件名|原名|扩展名|父文件夹名|品牌|语言|类型|标签|标签1|标签2|标签3|尺寸|设计师|名|文件名|文件夹|N)\}"
)


def expand_meta(text: str, ctx: RenameMetaContext) -> str:
    if not text or "{" not in text:
        return text or ""

    def _repl(m: re.Match) -> str:
        return ctx.resolve_token(m.group(0))

    return _META_PATTERN.sub(_repl, text)


def expand_meta_in_dict(params: dict[str, Any], ctx: RenameMetaContext) -> dict[str, Any]:
    """展开规则块参数字典中的元变量（字符串字段）。"""
    out = dict(params)
    for key in ("text", "find", "replace", "anchor", "delimiter", "sep", "pad_char"):
        val = out.get(key)
        if isinstance(val, str) and val:
            out[key] = expand_meta(val, ctx)
    return out
