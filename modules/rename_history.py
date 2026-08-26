# -*- coding: utf-8 -*-
"""规范命名预览 — 操作记录与撤销/重做（菲菲式）。"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Optional

_ROW_KEYS = (
    "old", "new", "computed_new", "selected", "manual_edit", "note",
    "overrides", "legacy_priority", "parsed", "full_path",
)


def snapshot_preview_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        item = {k: copy.deepcopy(r.get(k)) for k in _ROW_KEYS if k in r}
        out.append(item)
    return out


def restore_preview_rows(
    current: list[dict[str, Any]],
    snap: list[dict[str, Any]],
) -> None:
    current.clear()
    for item in snap:
        row = {k: copy.deepcopy(v) for k, v in item.items()}
        current.append(row)


@dataclass
class HistoryEntry:
    label: str
    rows: list[dict[str, Any]] = field(default_factory=list)


class RenameHistory:
    """撤销/重做栈；关闭软件前可无限撤销（有上限防内存）。"""

    def __init__(self, *, max_depth: int = 80) -> None:
        self._undo: list[HistoryEntry] = []
        self._redo: list[HistoryEntry] = []
        self._max = max(10, int(max_depth or 80))

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, rows: list[dict[str, Any]], label: str) -> None:
        """在修改预览表之前调用，保存当前快照。"""
        label = (label or "操作").strip() or "操作"
        self._undo.append(HistoryEntry(label=label, rows=snapshot_preview_rows(rows)))
        self._redo.clear()
        while len(self._undo) > self._max:
            self._undo.pop(0)

    def undo(self, current_rows: list[dict[str, Any]]) -> Optional[HistoryEntry]:
        if not self._undo:
            return None
        target = self._undo.pop()
        self._redo.append(HistoryEntry(label="重做前", rows=snapshot_preview_rows(current_rows)))
        return target

    def redo(self, current_rows: list[dict[str, Any]]) -> Optional[HistoryEntry]:
        if not self._redo:
            return None
        target = self._redo.pop()
        self._undo.append(HistoryEntry(label="撤销前", rows=snapshot_preview_rows(current_rows)))
        return target

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        return len(self._redo) > 0

    def labels(self) -> list[str]:
        return [e.label for e in self._undo]

    def peek_undo_label(self) -> str:
        if not self._undo:
            return ""
        return self._undo[-1].label
