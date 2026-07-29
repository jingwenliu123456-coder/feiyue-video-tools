"""高级搜索替换：按出现次数范围替换"""

from __future__ import annotations

import re


def explain_scope(scope_str: str, total: int = 0) -> str:
    s = (scope_str or "").strip()
    if not s:
        return "替换所有出现"
    if not re.fullmatch(r"[0-9\-~|]+", s):
        return "❌ 格式错误，只能包含数字 0-9、-、~、|"
    parts = [p.strip() for p in s.split("|") if p.strip()]
    hints: list[str] = []
    for part in parts:
        if "~" in part:
            hints.append(f"范围 {part}")
        elif part.startswith("-"):
            hints.append(f"倒数第 {part[1:]} 次")
        else:
            hints.append(f"第 {part} 次")
    return "；".join(hints) if hints else "替换所有出现"


def parse_scope(scope_str: str, total_occurrences: int) -> set[int]:
    if not (scope_str or "").strip():
        return set(range(1, total_occurrences + 1))

    s = scope_str.strip()
    if not re.fullmatch(r"[0-9\-~|]+", s):
        raise ValueError("范围设置格式错误，只能包含数字 0-9、-、~、|")

    total = max(0, int(total_occurrences))
    if total == 0:
        return set()

    def _resolve_num(raw: str) -> int:
        n = int(raw)
        if n < 0:
            return total + n + 1
        return n

    indices: set[int] = set()
    for part in [p.strip() for p in s.split("|") if p.strip()]:
        if "~" in part:
            left_s, right_s = part.split("~", 1)
            left = _resolve_num(left_s)
            right = _resolve_num(right_s)
            start, end = min(left, right), max(left, right)
            for i in range(start, end + 1):
                if 1 <= i <= total:
                    indices.add(i)
        else:
            num = _resolve_num(part)
            if 1 <= num <= total:
                indices.add(num)
    return indices


def advanced_replace(text: str, old: str, new: str, scope: str) -> str:
    if not old:
        return text

    occurrences: list[int] = []
    start = 0
    while True:
        idx = text.find(old, start)
        if idx == -1:
            break
        occurrences.append(idx)
        start = idx + len(old)

    total = len(occurrences)
    if total == 0:
        return text

    indices = parse_scope(scope, total)
    result = text
    for i in range(total - 1, -1, -1):
        if (i + 1) in indices:
            pos = occurrences[i]
            result = result[:pos] + new + result[pos + len(old):]
    return result
