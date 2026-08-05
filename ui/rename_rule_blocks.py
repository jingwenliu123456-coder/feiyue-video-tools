# -*- coding: utf-8 -*-
"""规范命名 — 菲菲风格 2×3 规则卡片（主题自适应 · 原生单选/勾选圆点）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

from modules.rename_rules import RenameRuleChain, chain_from_ui_dict

try:
    from modules.rename_meta import RULE_META_INSERT_OPTIONS
except Exception:
    RULE_META_INSERT_OPTIONS = [("{日期}", "日期")]

KEEP = "保持不变"

# 精修版统一字体（卡片内全部 10 号，底部提示 9 号）
_FONT = ("Microsoft YaHei", 10)
_FONT_BOLD = ("Microsoft YaHei", 10, "bold")
_FONT_SMALL = ("Microsoft YaHei", 9)

_LABEL_WIDTH = 6
_ROW_PADY = 3
_CARD_PADX = 12
_CARD_PADY = 10

_META_TARGETS: dict[str, list[tuple[str, str]]] = {
    "add": [("text", "内容")],
    "replace": [("find", "查找"), ("replace", "替换为")],
    "delete": [("text", "内容")],
}


def _palette_to_colors(palette: dict[str, str] | None) -> dict[str, str]:
    p = palette or {}
    card = p.get("card", "#ffffff")
    return {
        "bg": p.get("bg", "#f5f5f5"),
        "toolbar": p.get("bg", "#f5f5f5"),
        "card": card,
        "fg": p.get("text", "#1a1a1a"),
        "muted": p.get("muted", "#666666"),
        "accent": p.get("accent", "#2e7d32"),
        "accent_fg": p.get("accent_fg", "#ffffff"),
        "border_off": p.get("border", "#e0e0e0"),
        "radio_bg": card,
        "input_bg": card,
        "check": p.get("check", "#34C759"),
    }


class RenameRuleBlocksPanel(tk.Frame):
    """2×3 卡片网格：添加 / 替换 / 删除 / 移动 / 大小写 / 旧版清理。"""

    BLOCKS = (
        ("add", "1. 添加与补齐", {
            "mode": KEEP,
            "modes": [KEEP, "直接添加", "补齐添加"],
            "fields": [
                ("text", "内容", "entry", ""),
                ("position", "位置", "combo", ["名称后", "名称前", "第N位", "在文本前", "在文本后"]),
                ("index", "N/索引", "entry", "0"),
                ("anchor", "定位文本", "entry", ""),
                ("pad_len", "补齐长度", "entry", "0"),
                ("pad_char", "补齐字符", "entry", "0"),
            ],
        }),
        ("replace", "2. 替换", {
            "mode": KEEP,
            "modes": [KEEP, "替换"],
            "fields": [
                ("find", "查找", "entry", ""),
                ("replace", "替换为", "entry", ""),
                ("case_sensitive", "区分大小写", "check", False),
                ("scope", "范围", "combo", ["全部", "第N次", "分隔符左", "分隔符右"]),
                ("nth", "第几次", "entry", "1"),
                ("delimiter", "分隔符", "entry", "-"),
            ],
        }),
        ("delete", "3. 删除与保留", {
            "mode": KEEP,
            "modes": [
                KEEP, "清空文件名", "删除空格", "删除字符", "按分隔符剪裁",
                "删除以下内容", "只保留以下内容", "保留之前", "保留之后",
            ],
            "fields": [
                ("text", "内容", "entry", ""),
                ("index", "起始位", "entry", "0"),
                ("count", "字符数", "entry", "0"),
                ("delimiter", "分隔符", "entry", "-"),
                ("delim_part", "保留", "combo", ["之前", "之后"]),
            ],
        }),
        ("move", "4. 移动", {
            "mode": KEEP,
            "modes": [KEEP, "按位置移动", "按分隔符移动"],
            "fields": [
                ("from_index", "从位", "entry", "0"),
                ("length", "长度", "entry", "0"),
                ("to_index", "到位", "entry", "0"),
                ("delimiter", "分隔符", "entry", "-"),
                ("move_part", "方式", "combo", ["首段移到末尾", "末段移到开头"]),
            ],
        }),
        ("case", "5. 字母大小写", {
            "mode": KEEP,
            "modes": [KEEP, "全部大写", "全部小写", "首字母大写", "反转大小写"],
            "fields": [],
        }),
        ("legacy", "6. 旧版清理", {"custom": "legacy"}),
    )

    _POS_MAP = {
        "名称后": "suffix", "名称前": "prefix", "第N位": "at_index",
        "在文本前": "before_text", "在文本后": "after_text",
    }
    _SCOPE_MAP = {"全部": "all", "第N次": "nth", "分隔符左": "delim_left", "分隔符右": "delim_right"}
    _DELIM_PART_MAP = {"之前": "before", "之后": "after"}
    _MOVE_PART_MAP = {"首段移到末尾": "first_to_end", "末段移到开头": "last_to_start"}

    def __init__(
        self,
        parent: tk.Misc,
        *,
        legacy_embed: Optional[Callable[[tk.Frame], None]] = None,
        colors: Optional[dict[str, str]] = None,
        refresh_callback: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> None:
        c = _palette_to_colors(colors)
        super().__init__(parent, bg=c["bg"], **kwargs)
        self._legacy_embed = legacy_embed
        self._colors = c
        self._refresh_callback = refresh_callback
        self._pending_refresh: str | None = None
        self._vars: dict[str, dict[str, Any]] = {}
        self._field_widgets: dict[str, dict[str, tk.Widget]] = {}
        self._cards: dict[str, tk.Frame] = {}
        self._mode_labels: dict[str, list[tk.Radiobutton]] = {}
        self._build()

    def _trigger_refresh(self, *_args: Any) -> None:
        """输入变化时触发，300ms 防抖。"""
        if not callable(self._refresh_callback):
            return
        if self._pending_refresh:
            try:
                self.after_cancel(self._pending_refresh)
            except tk.TclError:
                pass
        self._pending_refresh = self.after(300, self._do_refresh)

    def _do_refresh(self) -> None:
        self._pending_refresh = None
        if not callable(self._refresh_callback):
            return
        try:
            self._refresh_callback()
        except Exception as exc:
            print(f"规则预览刷新失败: {exc}")

    def _bind_refresh(self, var: tk.Variable) -> None:
        if not callable(self._refresh_callback):
            return
        try:
            var.trace_add("write", self._trigger_refresh)
        except (tk.TclError, AttributeError):
            pass

    def apply_theme(self, palette: dict[str, str]) -> None:
        self._colors = _palette_to_colors(palette)
        self.config(bg=self._colors["bg"])
        for key, card in self._cards.items():
            self._theme_card(card, key)

    def _theme_card(self, card: tk.Frame, key: str) -> None:
        c = self._colors
        hdr = getattr(card, "_header", None)
        if hdr is not None:
            hdr.config(bg=c["accent"])
            for w in hdr.winfo_children():
                if isinstance(w, tk.Label):
                    w.config(bg=c["accent"], fg=c["accent_fg"])
        body = getattr(card, "_body", None)
        if body is not None:
            body.config(bg=c["card"])
            self._theme_widget_tree(body, c)
        card.config(bg=c["border_off"], highlightbackground=c["border_off"])
        for rb in self._mode_labels.get(key, []):
            try:
                rb.config(
                    bg=c["radio_bg"],
                    fg=c["fg"],
                    activebackground=c["radio_bg"],
                    activeforeground=c["fg"],
                    selectcolor=c["radio_bg"],
                )
            except tk.TclError:
                pass

    def _theme_widget_tree(self, widget: tk.Widget, c: dict[str, str]) -> None:
        cls = widget.winfo_class()
        try:
            if cls in ("Frame", "Label"):
                widget.config(bg=c["card"], fg=c["fg"] if cls == "Label" else c["card"])
            elif cls == "Checkbutton":
                widget.config(
                    bg=c["card"],
                    fg=c["fg"],
                    activebackground=c["card"],
                    selectcolor=c["card"],
                )
            elif cls == "Radiobutton":
                widget.config(
                    bg=c["radio_bg"],
                    fg=c["fg"],
                    activebackground=c["radio_bg"],
                    selectcolor=c["radio_bg"],
                )
            elif cls == "Entry":
                widget.config(
                    bg=c["input_bg"],
                    fg=c["fg"],
                    insertbackground=c["fg"],
                    highlightbackground=c["border_off"],
                )
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._theme_widget_tree(child, c)

    def _build(self) -> None:
        c = self._colors
        grid = tk.Frame(self, bg=c["bg"])
        grid.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        for idx, (key, title, spec) in enumerate(self.BLOCKS):
            r, col = divmod(idx, 3)
            card = self._build_block_card(grid, key, title, spec)
            card.grid(row=r, column=col, sticky="nsew", padx=5, pady=5)
            self._cards[key] = card

        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="rule_col")
        for row in range(2):
            grid.grid_rowconfigure(row, weight=1)

        foot = tk.Frame(self, bg=c["bg"])
        foot.pack(fill=tk.X, pady=(2, 0))
        tk.Label(
            foot,
            text="每卡选模式后填参数 · 修改后约 0.3 秒自动更新预览（需先勾选文件）",
            bg=c["bg"], fg=c["muted"], font=_FONT_SMALL,
        ).pack(side=tk.LEFT, padx=4)

    def _build_mode_group(self, body: tk.Frame, key: str, modes: list[str], default: str) -> None:
        """垂直单选：selectcolor=卡片底，选中无黑块。"""
        c = self._colors
        mode_var = tk.StringVar(value=default)
        self._vars[key]["mode"] = mode_var
        self._bind_refresh(mode_var)
        mode_fr = tk.Frame(body, bg=c["card"])
        mode_fr.pack(fill=tk.X, pady=(0, 4))
        self._mode_labels[key] = []
        for m in modes:
            rb = tk.Radiobutton(
                mode_fr, text=m, variable=mode_var, value=m,
                bg=c["radio_bg"], fg=c["fg"], font=_FONT, anchor="w",
                activebackground=c["radio_bg"], activeforeground=c["fg"],
                selectcolor=c["radio_bg"], highlightthickness=0,
            )
            rb.pack(fill=tk.X, pady=2)
            self._mode_labels[key].append(rb)

    def _build_field_row(
        self, body: tk.Frame, key: str, fname: str, label: str, ftype: str, default: Any,
    ) -> None:
        """标签 width=6 右对齐，输入框 fill 拉伸。"""
        c = self._colors
        fr = tk.Frame(body, bg=c["card"])
        fr.pack(fill=tk.X, pady=_ROW_PADY)

        if ftype != "check":
            tk.Label(
                fr, text=label, font=_FONT, width=_LABEL_WIDTH,
                anchor="e", bg=c["card"], fg=c["muted"],
            ).pack(side=tk.LEFT, padx=(0, 8))

        if ftype == "entry":
            var = tk.StringVar(value=str(default))
            w = tk.Entry(
                fr, textvariable=var, font=_FONT, relief="solid", bd=1,
                bg=c["input_bg"], fg=c["fg"], insertbackground=c["fg"],
                highlightbackground=c["border_off"], highlightthickness=1,
            )
            w.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
            self._vars[key][fname] = var
            self._field_widgets[key][fname] = w
            self._bind_refresh(var)
        elif ftype == "combo":
            options = list(default) if isinstance(default, list) else [str(default)]
            var = tk.StringVar(value=str(options[0] if options else ""))
            w = ttk.Combobox(fr, textvariable=var, values=options, state="readonly", font=_FONT)
            w.pack(side=tk.LEFT, fill=tk.X, expand=True)
            w.bind("<<ComboboxSelected>>", lambda _e: self._trigger_refresh())
            self._vars[key][fname] = var
            self._field_widgets[key][fname] = w
            self._bind_refresh(var)
        elif ftype == "check":
            var = tk.BooleanVar(value=bool(default))
            w = tk.Checkbutton(
                fr, text=label, variable=var,
                bg=c["card"], fg=c["fg"], font=_FONT, anchor="w",
                activebackground=c["card"], activeforeground=c["fg"],
                selectcolor=c["card"], highlightthickness=0,
            )
            w.pack(side=tk.LEFT, fill=tk.X, anchor="w")
            self._vars[key][fname] = var
            self._field_widgets[key][fname] = w
            self._bind_refresh(var)

    def _build_block_card(self, parent: tk.Frame, key: str, title: str, spec: dict) -> tk.Frame:
        c = self._colors
        card = tk.Frame(
            parent, bg=c["border_off"],
            highlightthickness=1, highlightbackground=c["border_off"],
        )

        hdr = tk.Frame(card, bg=c["accent"], height=28)
        hdr.pack(fill=tk.X, side=tk.TOP)
        hdr.pack_propagate(False)
        card._header = hdr  # noqa: SLF001

        tk.Label(
            hdr, text=title, bg=c["accent"], fg=c["accent_fg"],
            font=_FONT_BOLD, anchor="w",
        ).pack(side=tk.LEFT, padx=10, pady=3)

        body = tk.Frame(card, bg=c["card"], padx=_CARD_PADX, pady=_CARD_PADY)
        body.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        card._body = body  # noqa: SLF001

        if spec.get("custom") == "legacy":
            if self._legacy_embed:
                self._legacy_embed(body)
            else:
                tk.Label(body, text="（未挂载）", font=_FONT, bg=c["card"], fg=c["muted"]).pack(anchor="w")
            return card

        self._vars[key] = {}
        self._field_widgets[key] = {}
        self._mode_labels[key] = []

        hint = spec.get("hint")
        if hint:
            tk.Label(
                body, text=str(hint), font=_FONT_SMALL, fg=c["muted"], bg=c["card"],
            ).pack(anchor="w", pady=(0, 4))

        modes = list(spec.get("modes") or [KEEP])
        self._build_mode_group(body, key, modes, spec.get("mode", KEEP))

        for fname, label, ftype, default in spec.get("fields") or []:
            self._build_field_row(body, key, fname, label, ftype, default)

        if key in _META_TARGETS:
            self._build_meta_insert_row(body, key)

        return card

    def _build_meta_insert_row(self, body: tk.Frame, block_key: str) -> None:
        c = self._colors
        fr = tk.Frame(body, bg=c["card"])
        fr.pack(fill=tk.X, pady=_ROW_PADY)
        tk.Label(
            fr, text="插入", font=_FONT, width=_LABEL_WIDTH,
            anchor="e", bg=c["card"], fg=c["muted"],
        ).pack(side=tk.LEFT, padx=(0, 8))
        targets = _META_TARGETS.get(block_key) or [("text", "内容")]
        lbl_to_field = {lbl: f for f, lbl in targets}
        target_var = tk.StringVar(value=targets[0][1])
        if len(targets) > 1:
            tcb = ttk.Combobox(
                fr, textvariable=target_var, state="readonly", font=_FONT,
                values=[lbl for _f, lbl in targets],
            )
            tcb.pack(side=tk.LEFT, padx=(0, 4))
            tcb.bind("<<ComboboxSelected>>", lambda _e: self._trigger_refresh())
        meta_labels = [tok for tok, _desc in RULE_META_INSERT_OPTIONS]
        meta_pick = tk.StringVar(value="")
        cb = ttk.Combobox(fr, textvariable=meta_pick, state="readonly", values=meta_labels, font=_FONT)
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._trigger_refresh())

        def _on_meta(_e=None, bk=block_key, tv=target_var):
            pick = (meta_pick.get() or "").strip()
            if not pick:
                return
            field = lbl_to_field.get(tv.get(), targets[0][0]) if len(targets) > 1 else targets[0][0]
            var = self._vars.get(bk, {}).get(field)
            if isinstance(var, tk.StringVar):
                var.set(f"{var.get()}{pick}")
            meta_pick.set("")

        cb.bind("<<ComboboxSelected>>", _on_meta)

    def _int(self, val: Any, default: int = 0) -> int:
        try:
            return int(str(val).strip())
        except (TypeError, ValueError):
            return default

    def _str(self, var: Any) -> str:
        if isinstance(var, tk.Variable):
            return str(var.get() or "").strip()
        return str(var or "").strip()

    def _bool(self, var: Any) -> bool:
        if isinstance(var, tk.BooleanVar):
            return bool(var.get())
        return bool(var)

    def get_chain_dict(self, *, start: int = 1, digits: int = 2) -> dict[str, dict[str, Any]]:
        v = self._vars
        add_mode = self._str(v["add"]["mode"])
        rep_mode = self._str(v["replace"]["mode"])
        del_mode = self._str(v["delete"]["mode"])
        mov_mode = self._str(v["move"]["mode"])
        case_mode = self._str(v["case"]["mode"])

        pos_add = self._POS_MAP.get(self._str(v["add"].get("position")), "suffix")

        return {
            "add": {
                "mode": {"保持不变": "keep", "直接添加": "direct", "补齐添加": "pad"}.get(add_mode, "keep"),
                "text": self._str(v["add"].get("text")),
                "position": pos_add,
                "index": self._int(v["add"].get("index")),
                "anchor": self._str(v["add"].get("anchor")),
                "pad_len": self._int(v["add"].get("pad_len")),
                "pad_char": self._str(v["add"].get("pad_char")) or "0",
            },
            "replace": {
                "mode": "replace" if rep_mode == "替换" else "keep",
                "find": self._str(v["replace"].get("find")),
                "replace": self._str(v["replace"].get("replace")),
                "case_sensitive": self._bool(v["replace"].get("case_sensitive")),
                "scope": self._SCOPE_MAP.get(self._str(v["replace"].get("scope")), "all"),
                "nth": self._int(v["replace"].get("nth"), 1),
                "delimiter": self._str(v["replace"].get("delimiter")),
            },
            "delete": {
                "mode": {
                    "保持不变": "keep", "清空文件名": "clear", "删除空格": "trim_space",
                    "删除字符": "delete_range", "按分隔符剪裁": "crop_delim",
                    "删除以下内容": "delete_text", "只保留以下内容": "keep_text",
                    "保留之前": "keep_before", "保留之后": "keep_after",
                }.get(del_mode, "keep"),
                "text": self._str(v["delete"].get("text")),
                "index": self._int(v["delete"].get("index")),
                "count": self._int(v["delete"].get("count")),
                "delimiter": self._str(v["delete"].get("delimiter")),
                "delim_part": self._DELIM_PART_MAP.get(self._str(v["delete"].get("delim_part")), "before"),
            },
            "number": {"mode": "keep"},
            "move": {
                "mode": {"保持不变": "keep", "按位置移动": "chars", "按分隔符移动": "delim"}.get(mov_mode, "keep"),
                "from_index": self._int(v["move"].get("from_index")),
                "length": self._int(v["move"].get("length")),
                "to_index": self._int(v["move"].get("to_index")),
                "delimiter": self._str(v["move"].get("delimiter")),
                "move_part": self._MOVE_PART_MAP.get(self._str(v["move"].get("move_part")), "first_to_end"),
            },
            "case": {
                "mode": {
                    "保持不变": "keep", "全部大写": "upper", "全部小写": "lower",
                    "首字母大写": "title", "反转大小写": "invert",
                }.get(case_mode, "keep"),
            },
        }

    def get_chain(self, *, start: int = 1, digits: int = 2) -> RenameRuleChain:
        return chain_from_ui_dict(self.get_chain_dict(start=start, digits=digits))
