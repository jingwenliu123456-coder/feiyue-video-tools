# -*- coding: utf-8 -*-
"""菲菲更名宝贝式规则链：添加与补齐 / 替换 / 删除与保留 / 自动编号 / 移动 / 字母大小写。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


def split_stem_ext(filename: str) -> tuple[str, str]:
    name = (filename or "").strip()
    if not name:
        return "", ""
    stem, ext = __import__("os").path.splitext(name)
    return stem, ext


def join_stem_ext(stem: str, ext: str) -> str:
    s = stem or ""
    e = ext or ""
    return s + e if s or e else ""


def _pos_insert(stem: str, text: str, position: str, *, index: int = 0, anchor: str = "") -> str:
    pos = (position or "suffix").strip()
    if pos in ("suffix", "名称后", "后"):
        return stem + text
    if pos in ("prefix", "名称前", "前"):
        return text + stem
    if pos in ("at_index", "第N位"):
        i = max(0, min(len(stem), int(index or 0)))
        return stem[:i] + text + stem[i:]
    if pos in ("before_text", "在文本前"):
        a = anchor or ""
        if not a:
            return stem + text
        idx = stem.find(a)
        return stem[:idx] + text + stem[idx:] if idx >= 0 else stem
    if pos in ("after_text", "在文本后"):
        a = anchor or ""
        if not a:
            return stem + text
        idx = stem.find(a)
        return stem[: idx + len(a)] + text + stem[idx + len(a) :] if idx >= 0 else stem
    return stem + text


# ── 1. 添加与补齐 ─────────────────────────────────────────────

def apply_add_block(
    stem: str,
    *,
    mode: str = "keep",
    text: str = "",
    position: str = "suffix",
    index: int = 0,
    anchor: str = "",
    pad_len: int = 0,
    pad_char: str = "0",
) -> str:
    m = (mode or "keep").strip()
    if m in ("keep", "保持不变", ""):
        return stem
    t = text or ""
    if m in ("direct", "直接添加"):
        if not t:
            return stem
        return _pos_insert(stem, t, position, index=index, anchor=anchor)
    if m in ("pad", "补齐添加"):
        n = max(0, int(pad_len or 0))
        ch = (pad_char or "0")[:1] or "0"
        if n <= len(stem):
            return stem
        return ch * (n - len(stem)) + stem
    return stem


# ── 2. 替换 ─────────────────────────────────────────────────

def _replace_nth(hay: str, needle: str, repl: str, n: int, *, case_sensitive: bool) -> str:
    if not needle or n <= 0:
        return hay
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pat = re.compile(re.escape(needle), flags)
    except re.error:
        return hay
    count = 0
    def _sub(m: re.Match) -> str:
        nonlocal count
        count += 1
        return repl if count == n else m.group(0)
    return pat.sub(_sub, hay, count=0)


def apply_replace_block(
    stem: str,
    *,
    mode: str = "keep",
    find: str = "",
    replace: str = "",
    case_sensitive: bool = False,
    scope: str = "all",
    nth: int = 1,
    delimiter: str = "",
    delim_side: str = "left",
) -> str:
    m = (mode or "keep").strip()
    if m in ("keep", "保持不变", ""):
        return stem
    finds = [p for p in (find or "").split("|") if p != ""]
    repls = (replace or "").split("|")
    if not finds:
        return stem
    out = stem
    sc = (scope or "all").strip()
    for i, f in enumerate(finds):
        r = repls[i] if i < len(repls) else (repls[-1] if repls else "")
        if sc in ("nth", "第N次"):
            out = _replace_nth(out, f, r, max(1, int(nth or 1)), case_sensitive=case_sensitive)
        elif sc in ("delim_left", "分隔符左") and delimiter:
            parts = out.split(delimiter, 1)
            if len(parts) == 2:
                left = parts[0]
                if case_sensitive:
                    left = left.replace(f, r)
                else:
                    left = re.sub(re.escape(f), r, left, flags=re.IGNORECASE)
                out = left + delimiter + parts[1]
        elif sc in ("delim_right", "分隔符右") and delimiter:
            parts = out.rsplit(delimiter, 1)
            if len(parts) == 2:
                right = parts[1]
                if case_sensitive:
                    right = right.replace(f, r)
                else:
                    right = re.sub(re.escape(f), r, right, flags=re.IGNORECASE)
                out = parts[0] + delimiter + right
        else:
            if case_sensitive:
                out = out.replace(f, r)
            else:
                import re as _re
                out = _re.sub(_re.escape(f), r, out, flags=_re.IGNORECASE)
    return out


# ── 3. 删除与保留 ─────────────────────────────────────────────

def apply_delete_block(
    stem: str,
    *,
    mode: str = "keep",
    text: str = "",
    index: int = 0,
    count: int = 0,
    delimiter: str = "",
    delim_part: str = "before",
) -> str:
    m = (mode or "keep").strip()
    if m in ("keep", "保持不变", ""):
        return stem
    if m in ("clear", "清空文件名"):
        return ""
    if m in ("trim_space", "删除空格"):
        return stem.replace(" ", "").replace("\u3000", "")
    if m in ("delete_range", "删除字符"):
        i = max(0, int(index or 0))
        n = max(0, int(count or 0))
        if n <= 0:
            return stem
        return stem[:i] + stem[i + n :]
    if m in ("crop_delim", "按分隔符剪裁") and delimiter:
        parts = stem.split(delimiter)
        if len(parts) < 2:
            return stem
        if (delim_part or "before") in ("before", "之前"):
            return delimiter.join(parts[:-1])
        return parts[-1]
    if m in ("delete_text", "删除以下内容"):
        for part in [p for p in (text or "").split("|") if p]:
            stem = stem.replace(part, "")
        return stem
    if m in ("keep_text", "只保留以下内容"):
        for part in [p for p in (text or "").split("|") if p]:
            if part in stem:
                idx = stem.find(part)
                return stem[idx : idx + len(part)]
        return ""
    if m in ("keep_before", "保留之前") and text:
        idx = stem.find(text)
        return stem[:idx] if idx >= 0 else stem
    if m in ("keep_after", "保留之后") and text:
        idx = stem.find(text)
        return stem[idx + len(text) :] if idx >= 0 else stem
    return stem


# ── 4. 自动编号 ─────────────────────────────────────────────

def format_serial(value: int, digits: int) -> str:
    d = max(1, int(digits or 1))
    return str(int(value)).zfill(d)


def apply_number_block(
    stem: str,
    *,
    mode: str = "keep",
    start: int = 1,
    step: int = 1,
    digits: int = 2,
    group_size: int = 0,
    file_index: int = 0,
    position: str = "suffix",
    index: int = 0,
    anchor: str = "",
    sep: str = "",
) -> str:
    m = (mode or "keep").strip()
    if m in ("keep", "保持不变", ""):
        return stem
    if m not in ("insert", "插入编号"):
        return stem
    gs = max(0, int(group_size or 0))
    fi = max(0, int(file_index or 0))
    if gs > 0:
        serial = int(start) + (fi // gs) * int(step or 1)
    else:
        serial = int(start) + fi * int(step or 1)
    num = format_serial(serial, digits)
    if sep:
        num = num + sep
    return _pos_insert(stem, num, position, index=index, anchor=anchor)


# ── 5. 移动 ─────────────────────────────────────────────────

def apply_move_block(
    stem: str,
    *,
    mode: str = "keep",
    from_index: int = 0,
    length: int = 0,
    to_index: int = 0,
    delimiter: str = "",
    move_part: str = "first_to_end",
) -> str:
    m = (mode or "keep").strip()
    if m in ("keep", "保持不变", ""):
        return stem
    if m in ("chars", "按位置移动"):
        i = max(0, int(from_index or 0))
        ln = max(0, int(length or 0))
        j = max(0, int(to_index or 0))
        if ln <= 0 or i >= len(stem):
            return stem
        chunk = stem[i : i + ln]
        rest = stem[:i] + stem[i + ln :]
        j = min(j, len(rest))
        return rest[:j] + chunk + rest[j:]
    if m in ("delim", "按分隔符移动") and delimiter:
        parts = stem.split(delimiter)
        if len(parts) < 2:
            return stem
        mp = (move_part or "first_to_end").strip()
        if mp in ("first_to_end", "首段移到末尾"):
            return delimiter.join(parts[1:] + [parts[0]])
        if mp in ("last_to_start", "末段移到开头"):
            return delimiter.join([parts[-1]] + parts[:-1])
    return stem


# ── 6. 字母大小写 ─────────────────────────────────────────────

def apply_case_block(stem: str, *, mode: str = "keep") -> str:
    m = (mode or "keep").strip()
    if m in ("keep", "保持不变", ""):
        return stem
    if m in ("upper", "全部大写"):
        return stem.upper()
    if m in ("lower", "全部小写"):
        return stem.lower()
    if m in ("title", "首字母大写"):
        return stem.title()
    if m in ("invert", "反转大小写"):
        return "".join(c.lower() if c.isupper() else c.upper() if c.islower() else c for c in stem)
    return stem


@dataclass
class RenameRuleChain:
    """六块规则配置（与菲菲更名宝贝顺序一致）。"""

    add: dict[str, Any] = field(default_factory=dict)
    replace: dict[str, Any] = field(default_factory=dict)
    delete: dict[str, Any] = field(default_factory=dict)
    number: dict[str, Any] = field(default_factory=dict)
    move: dict[str, Any] = field(default_factory=dict)
    case: dict[str, Any] = field(default_factory=dict)

    def _block_params(self, block: dict[str, Any], meta_ctx: Any | None) -> dict[str, Any]:
        if meta_ctx is None:
            return dict(block)
        try:
            from modules.rename_meta import expand_meta_in_dict
            return expand_meta_in_dict(block, meta_ctx)
        except Exception:
            return dict(block)

    def apply_to_stem(
        self,
        stem: str,
        *,
        file_index: int = 0,
        meta_ctx: Any | None = None,
    ) -> str:
        s = stem or ""
        s = apply_add_block(s, **self._block_params(self.add, meta_ctx))
        s = apply_replace_block(s, **self._block_params(self.replace, meta_ctx))
        s = apply_delete_block(s, **self._block_params(self.delete, meta_ctx))
        num = self._block_params(self.number, meta_ctx)
        s = apply_number_block(s, file_index=file_index, **num)
        s = apply_move_block(s, **self._block_params(self.move, meta_ctx))
        s = apply_case_block(s, **self._block_params(self.case, meta_ctx))
        return s

    def apply_to_filename(
        self,
        filename: str,
        *,
        file_index: int = 0,
        meta_ctx: Any | None = None,
    ) -> str:
        stem, ext = split_stem_ext(filename)
        return join_stem_ext(
            self.apply_to_stem(stem, file_index=file_index, meta_ctx=meta_ctx),
            ext,
        )

    def any_active(self) -> bool:
        for block in (self.add, self.replace, self.delete, self.number, self.move, self.case):
            m = str(block.get("mode") or "keep").strip()
            if m not in ("keep", "保持不变", ""):
                return True
        return False


def chain_from_ui_dict(data: dict[str, Any]) -> RenameRuleChain:
    return RenameRuleChain(
        add=dict(data.get("add") or {}),
        replace=dict(data.get("replace") or {}),
        delete=dict(data.get("delete") or {}),
        number=dict(data.get("number") or {}),
        move=dict(data.get("move") or {}),
        case=dict(data.get("case") or {}),
    )


def batch_apply_chain(
    filenames: Iterable[str],
    chain: RenameRuleChain,
    *,
    start_index: int = 0,
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i, name in enumerate(filenames):
        new_name = chain.apply_to_filename(name, file_index=start_index + i)
        out.append((name, new_name))
    return out


# ── 兼容旧 API ────────────────────────────────────────────────

def apply_rule_to_filename(filename: str, *, rule_kind: str, **kwargs) -> str:
    chain = RenameRuleChain()
    kind = (rule_kind or "").strip().lower()
    if kind in ("add", "添加", "添加与补齐"):
        chain.add = {"mode": "direct", "text": kwargs.get("text"), "position": kwargs.get("position", "suffix")}
    elif kind in ("replace", "替换"):
        chain.replace = {
            "mode": "replace",
            "find": kwargs.get("find"),
            "replace": kwargs.get("replace"),
            "case_sensitive": kwargs.get("use_regex", False),
        }
    elif kind in ("delete", "删除", "删除与保留"):
        chain.delete = {
            "mode": kwargs.get("mode", "delete_text"),
            "text": kwargs.get("text"),
            "index": kwargs.get("n_chars", 0),
        }
    return chain.apply_to_filename(filename)
